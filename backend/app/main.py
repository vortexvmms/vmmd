"""
VMMS Backend — Phase 7  ·  v0.7.0
Phase 4: Workers · Phase 5: Sites · Phase 6: Daily Allocation.
Phase 7 adds the Site Supervisor module + the OT hours engine
(spec FR-5, FR-6, §6 rules confirmed at review):
  GET    /api/v1/attendance?date=&site_id=   day sheet (site_sup sees own sites only)
  PATCH  /api/v1/attendance/mark             present / end time → hours computed
  POST   /api/v1/attendance/bulk_end         set one end time for the whole site
  POST   /api/v1/attendance/submit           submit & lock the site's day
"""
import os
from datetime import date as date_cls

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="VMMS API", version="0.17.0")  # + manpower requests, copy last request, dashboard any-date

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://vortexvmms.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
REST = f"{SUPABASE_URL}/rest/v1"


def supabase_headers(user_token: str | None = None) -> dict:
    headers = {"apikey": SUPABASE_ANON_KEY}
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
    elif SUPABASE_ANON_KEY.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {SUPABASE_ANON_KEY}"
    return headers


async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not signed in")
    token = auth.removeprefix("Bearer ").strip()

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=supabase_headers(token))
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Session expired — please log in again")
        auth_user = r.json()
        auth_uid = auth_user.get("id")

        r2 = await client.get(
            f"{REST}/users",
            params={"auth_uid": f"eq.{auth_uid}", "select": "id,name,role,status"},
            headers=supabase_headers(token),
        )
        rows = r2.json() if r2.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=403, detail="No VMMS profile/role linked — ask the administrator")
        profile = rows[0]
        if profile.get("status") != "active":
            raise HTTPException(status_code=403, detail="Account is deactivated")

    return {
        "token": token,
        "auth_uid": auth_uid,
        "email": auth_user.get("email"),
        "user_id": profile["id"],
        "name": profile["name"],
        "role": profile["role"],
    }


async def audit(client: httpx.AsyncClient, user: dict, action: str, entity: str,
                entity_id: str, old_value=None, new_value=None):
    await client.post(
        f"{REST}/audit_log",
        headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
        json={
            "user_id": user["user_id"],
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "old_value": old_value,
            "new_value": new_value,
        },
    )


# ---------------- basics ----------------
@app.get("/")
def root():
    return {"app": "VMMS", "phase": 12, "status": "running"}


@app.get("/api/v1/health")
async def health():
    detail = {}
    db_status = "not_configured"
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{SUPABASE_URL}/auth/v1/health", headers=supabase_headers())
                detail["status_code"] = r.status_code
                db_status = "connected" if r.status_code == 200 else "error"
        except Exception as e:
            detail["exception"] = type(e).__name__
            db_status = "unreachable"
    return {"server": "ok", "database": db_status, "diag": detail}


@app.get("/api/v1/me")
async def me(user: dict = Depends(get_current_user)):
    return {"name": user["name"], "role": user["role"], "email": user["email"],
            "user_id": user["user_id"]}


# ---------------- Worker Master (Phase 4) ----------------
class WorkerCreate(BaseModel):
    worker_code: str
    name: str


class WorkerUpdate(BaseModel):
    name: str | None = None
    status: str | None = None  # active | on_leave | inactive


VALID_STATUS = {"active", "on_leave", "inactive"}


@app.get("/api/v1/workers")
async def list_workers(search: str = "", status: str = "",
                       user: dict = Depends(get_current_user)):
    params = {"select": "id,worker_code,name,status,updated_at", "order": "name.asc"}
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        params["status"] = f"eq.{status}"
    if search:
        s = search.replace("%", "").replace(",", "").strip()
        params["or"] = f"(name.ilike.*{s}*,worker_code.ilike.*{s}*)"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{REST}/workers", params=params,
                             headers=supabase_headers(user["token"]))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load workers")
        return r.json()


@app.post("/api/v1/workers", status_code=201)
async def create_worker(body: WorkerCreate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the administrator can add workers")
    code = body.worker_code.strip().upper()
    name = body.name.strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Worker ID and name are required")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{REST}/workers",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json={"worker_code": code, "name": name, "status": "active",
                  "created_by": user["user_id"], "updated_by": user["user_id"]},
        )
        if r.status_code == 409:
            raise HTTPException(status_code=409, detail=f"Worker ID {code} already exists")
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Could not save worker")
        row = r.json()[0]
        await audit(client, user, "create", "worker", row["id"], None,
                    {"worker_code": code, "name": name, "status": "active"})
        return row


class WorkerBulk(BaseModel):
    workers: list[WorkerCreate]


@app.post("/api/v1/workers/bulk")
async def bulk_create_workers(body: WorkerBulk, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the administrator can add workers")
    clean, errors = [], []
    seen = set()
    for i, w in enumerate(body.workers, 1):
        code = w.worker_code.strip().upper()
        name = w.name.strip()
        if not code or not name:
            errors.append(f"Line {i}: missing ID or name")
            continue
        if code in seen:
            errors.append(f"Line {i}: duplicate ID {code} in your list")
            continue
        seen.add(code)
        clean.append({"worker_code": code, "name": name, "status": "active",
                      "created_by": user["user_id"], "updated_by": user["user_id"]})
    if not clean:
        raise HTTPException(status_code=400, detail="Nothing valid to import. " + "; ".join(errors[:3]))

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{REST}/workers",
            params={"on_conflict": "worker_code"},
            headers={**supabase_headers(user["token"]),
                     "Prefer": "return=representation,resolution=ignore-duplicates"},
            json=clean)
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Import failed — nothing saved")
        added = len(r.json())
        await audit(client, user, "bulk_import", "worker", f"{added} workers", None,
                    {"attempted": len(clean), "added": added})
        return {"ok": True, "added": added,
                "skipped_existing": len(clean) - added,
                "line_errors": errors}


@app.patch("/api/v1/workers/{worker_id}")
async def update_worker(worker_id: str, body: WorkerUpdate,
                        user: dict = Depends(get_current_user)):
    changes = {}
    if body.name is not None and body.name.strip():
        changes["name"] = body.name.strip()
    if body.status is not None:
        if body.status not in VALID_STATUS:
            raise HTTPException(status_code=400, detail="Invalid status")
        changes["status"] = body.status
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")

    # Role rules (spec §4): admin edits anything; main_sup may change status
    # only (leave management, Rev 3); others cannot edit.
    if user["role"] == "main_sup":
        if "name" in changes:
            raise HTTPException(status_code=403, detail="Main Supervisor can update leave status only")
    elif user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")

    changes["updated_by"] = user["user_id"]

    async with httpx.AsyncClient(timeout=10) as client:
        old = await client.get(
            f"{REST}/workers",
            params={"id": f"eq.{worker_id}", "select": "worker_code,name,status"},
            headers=supabase_headers(user["token"]),
        )
        old_rows = old.json() if old.status_code == 200 else []
        if not old_rows:
            raise HTTPException(status_code=404, detail="Worker not found")

        r = await client.patch(
            f"{REST}/workers",
            params={"id": f"eq.{worker_id}"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json=changes,
        )
        if r.status_code != 200 or not r.json():
            raise HTTPException(status_code=500, detail="Could not update worker")
        row = r.json()[0]
        await audit(client, user, "update", "worker", worker_id,
                    old_rows[0], {k: v for k, v in changes.items() if k != "updated_by"})
        return row


# ---------------- Site Master (Phase 5) ----------------
class SiteCreate(BaseModel):
    site_code: str
    site_name: str


class SiteUpdate(BaseModel):
    site_name: str | None = None
    status: str | None = None  # active | archived


class SupervisorAssign(BaseModel):
    user_ids: list[str]


@app.get("/api/v1/sites")
async def list_sites(user: dict = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{REST}/sites",
            params={"select": "id,site_code,site_name,status,site_supervisors(user_id,users(name))",
                    "order": "site_name.asc"},
            headers=supabase_headers(user["token"]),
        )
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load sites")
        out = []
        for s in r.json():
            sups = []
            for link in (s.get("site_supervisors") or []):
                u = link.get("users") or {}
                sups.append({"user_id": link["user_id"], "name": u.get("name", "?")})
            out.append({"id": s["id"], "site_code": s["site_code"],
                        "site_name": s["site_name"], "status": s["status"],
                        "supervisors": sups})
        return out


@app.post("/api/v1/sites", status_code=201)
async def create_site(body: SiteCreate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the administrator can add sites")
    code = body.site_code.strip().upper()
    name = body.site_name.strip().upper()   # site names print in CAPS in WhatsApp messages
    if not code or not name:
        raise HTTPException(status_code=400, detail="Site code and name are required")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{REST}/sites",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json={"site_code": code, "site_name": name, "status": "active"},
        )
        if r.status_code == 409:
            raise HTTPException(status_code=409, detail=f"Site code {code} already exists")
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Could not save site")
        row = r.json()[0]
        await audit(client, user, "create", "site", row["id"], None,
                    {"site_code": code, "site_name": name})
        return row


@app.patch("/api/v1/sites/{site_id}")
async def update_site(site_id: str, body: SiteUpdate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the administrator can edit sites")
    changes = {}
    if body.site_name is not None and body.site_name.strip():
        changes["site_name"] = body.site_name.strip().upper()
    if body.status is not None:
        if body.status not in ("active", "archived"):
            raise HTTPException(status_code=400, detail="Invalid status")
        changes["status"] = body.status
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")

    async with httpx.AsyncClient(timeout=10) as client:
        old = await client.get(
            f"{REST}/sites",
            params={"id": f"eq.{site_id}", "select": "site_code,site_name,status"},
            headers=supabase_headers(user["token"]),
        )
        old_rows = old.json() if old.status_code == 200 else []
        if not old_rows:
            raise HTTPException(status_code=404, detail="Site not found")

        r = await client.patch(
            f"{REST}/sites",
            params={"id": f"eq.{site_id}"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json=changes,
        )
        if r.status_code != 200 or not r.json():
            raise HTTPException(status_code=500, detail="Could not update site")
        row = r.json()[0]
        await audit(client, user, "update", "site", site_id, old_rows[0], changes)
        return row


@app.get("/api/v1/users")
async def list_users(role: str = "", user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    params = {"select": "id,name,role,status", "order": "name.asc"}
    if role:
        params["role"] = f"eq.{role}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{REST}/users", params=params,
                             headers=supabase_headers(user["token"]))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load users")
        return r.json()


@app.put("/api/v1/sites/{site_id}/supervisors")
async def assign_supervisors(site_id: str, body: SupervisorAssign,
                             user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the administrator can assign supervisors")
    async with httpx.AsyncClient(timeout=10) as client:
        old = await client.get(
            f"{REST}/site_supervisors",
            params={"site_id": f"eq.{site_id}", "select": "user_id"},
            headers=supabase_headers(user["token"]),
        )
        old_ids = [x["user_id"] for x in (old.json() if old.status_code == 200 else [])]

        d = await client.delete(
            f"{REST}/site_supervisors",
            params={"site_id": f"eq.{site_id}"},
            headers=supabase_headers(user["token"]),
        )
        if d.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not update assignments")

        if body.user_ids:
            i = await client.post(
                f"{REST}/site_supervisors",
                headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                json=[{"site_id": site_id, "user_id": uid} for uid in body.user_ids],
            )
            if i.status_code not in (200, 201):
                raise HTTPException(status_code=500, detail="Could not save assignments")

        await audit(client, user, "assign_supervisors", "site", site_id,
                    {"user_ids": old_ids}, {"user_ids": body.user_ids})
        return {"ok": True, "site_id": site_id, "user_ids": body.user_ids}


# ---------------- Daily Allocation (Phase 6) ----------------
class AllocationBulk(BaseModel):
    work_date: str          # YYYY-MM-DD
    site_id: str
    worker_ids: list[str]


class AllocationCopy(BaseModel):
    from_date: str
    to_date: str


def require_allocator(user: dict):
    if user["role"] not in ("admin", "main_sup"):
        raise HTTPException(status_code=403, detail="Only the Main Supervisor or Administrator can edit allocations")


@app.get("/api/v1/allocations")
async def list_allocations(date: str, user: dict = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{REST}/allocations",
            params={"work_date": f"eq.{date}", "status": "eq.allocated",
                    "select": "id,work_date,site_id,worker_id,sites(site_name,site_code),workers(name,worker_code,status)"},
            headers=supabase_headers(user["token"]),
        )
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load allocations")
        return [{
            "id": a["id"], "work_date": a["work_date"],
            "site_id": a["site_id"], "worker_id": a["worker_id"],
            "site_name": (a.get("sites") or {}).get("site_name", "?"),
            "worker_name": (a.get("workers") or {}).get("name", "?"),
            "worker_code": (a.get("workers") or {}).get("worker_code", ""),
            "worker_status": (a.get("workers") or {}).get("status", ""),
        } for a in r.json()]


@app.post("/api/v1/allocations/bulk")
async def save_allocation(body: AllocationBulk, user: dict = Depends(get_current_user)):
    require_allocator(user)
    requested = set(body.worker_ids)

    async with httpx.AsyncClient(timeout=10) as client:
        # everything already allocated on this date (all sites)
        r = await client.get(
            f"{REST}/allocations",
            params={"work_date": f"eq.{body.work_date}", "status": "eq.allocated",
                    "select": "id,site_id,worker_id,sites(site_name),workers(name)"},
            headers=supabase_headers(user["token"]),
        )
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not check existing allocations")
        existing = r.json()

        # hard stop: worker already on ANOTHER site that day (spec FR-4.2)
        conflicts = [
            f'{(a.get("workers") or {}).get("name", "?")} → {(a.get("sites") or {}).get("site_name", "?")}'
            for a in existing
            if a["worker_id"] in requested and a["site_id"] != body.site_id
        ]
        if conflicts:
            raise HTTPException(
                status_code=409,
                detail="Already allocated elsewhere that day: " + "; ".join(conflicts))

        this_site = {a["worker_id"]: a["id"] for a in existing if a["site_id"] == body.site_id}
        to_remove = [aid for wid, aid in this_site.items() if wid not in requested]
        to_add = [wid for wid in requested if wid not in this_site]

        if to_remove:
            d = await client.delete(
                f"{REST}/allocations",
                params={"id": f"in.({','.join(to_remove)})"},
                headers=supabase_headers(user["token"]),
            )
            if d.status_code not in (200, 204):
                raise HTTPException(status_code=500, detail="Could not remove workers")

        if to_add:
            i = await client.post(
                f"{REST}/allocations",
                headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                json=[{"work_date": body.work_date, "site_id": body.site_id,
                       "worker_id": wid, "status": "allocated",
                       "created_by": user["user_id"], "updated_by": user["user_id"]}
                      for wid in to_add],
            )
            if i.status_code not in (200, 201):
                raise HTTPException(status_code=500, detail="Could not save allocation")

        await audit(client, user, "allocate", "allocation",
                    f"{body.work_date}:{body.site_id}",
                    {"worker_ids": sorted(this_site.keys())},
                    {"worker_ids": sorted(requested)})
        return {"ok": True, "added": len(to_add), "removed": len(to_remove)}


@app.post("/api/v1/allocations/copy")
async def copy_allocation(body: AllocationCopy, user: dict = Depends(get_current_user)):
    require_allocator(user)
    async with httpx.AsyncClient(timeout=10) as client:
        src = await client.get(
            f"{REST}/allocations",
            params={"work_date": f"eq.{body.from_date}", "status": "eq.allocated",
                    "select": "site_id,worker_id,workers(status)"},
            headers=supabase_headers(user["token"]),
        )
        if src.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not read the source day")
        rows = src.json()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No allocation found on {body.from_date}")

        # copy only workers still active; skip anyone already allocated on the target date
        payload = [{"work_date": body.to_date, "site_id": a["site_id"],
                    "worker_id": a["worker_id"], "status": "allocated",
                    "created_by": user["user_id"], "updated_by": user["user_id"]}
                   for a in rows if (a.get("workers") or {}).get("status") == "active"]
        skipped_leave = len(rows) - len(payload)

        i = await client.post(
            f"{REST}/allocations",
            params={"on_conflict": "work_date,worker_id"},
            headers={**supabase_headers(user["token"]),
                     "Prefer": "return=representation,resolution=ignore-duplicates"},
            json=payload,
        )
        if i.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Could not copy the day")
        copied = len(i.json())

        await audit(client, user, "copy_day", "allocation",
                    f"{body.from_date}->{body.to_date}", None,
                    {"copied": copied, "skipped_on_leave": skipped_leave})
        return {"ok": True, "copied": copied,
                "skipped_on_leave": skipped_leave,
                "skipped_already_allocated": len(payload) - copied}


# ---------------- Manpower Requests (site supervisor → admin) ----------------
class RequestBulk(BaseModel):
    request_date: str        # YYYY-MM-DD (the date manpower is needed for)
    site_id: str
    worker_ids: list[str]
    note: str | None = None


@app.get("/api/v1/requests")
async def list_requests(date: str, user: dict = Depends(get_current_user)):
    """Requests for a date. RLS scopes site_sup to their own site(s);
    admin/main_sup/payroll see all."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{REST}/manpower_requests",
            params={"request_date": f"eq.{date}",
                    "select": "id,request_date,site_id,worker_id,note,"
                              "sites(site_name,site_code),workers(name,worker_code,status)"},
            headers=supabase_headers(user["token"]),
        )
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load requests")
        return [{
            "id": a["id"], "request_date": a["request_date"],
            "site_id": a["site_id"], "worker_id": a["worker_id"],
            "note": a.get("note"),
            "site_name": (a.get("sites") or {}).get("site_name", "?"),
            "worker_name": (a.get("workers") or {}).get("name", "?"),
            "worker_code": (a.get("workers") or {}).get("worker_code", ""),
            "worker_status": (a.get("workers") or {}).get("status", ""),
        } for a in r.json()]


@app.get("/api/v1/requests/last")
async def last_request(site_id: str, before: str, user: dict = Depends(get_current_user)):
    """Most recent request for this site strictly BEFORE `before` (YYYY-MM-DD).
    Used by the 'Copy last request' button. RLS scopes site_sup to their site."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{REST}/manpower_requests",
            params={"site_id": f"eq.{site_id}", "request_date": f"lt.{before}",
                    "select": "request_date,worker_id", "order": "request_date.desc"},
            headers=supabase_headers(user["token"]),
        )
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not read previous requests")
        rows = r.json()
        if not rows:
            return {"found": False, "request_date": None, "worker_ids": []}
        last_date = rows[0]["request_date"]
        ids = [x["worker_id"] for x in rows if x["request_date"] == last_date]
        return {"found": True, "request_date": last_date, "worker_ids": ids}


@app.post("/api/v1/requests/bulk")
async def save_request(body: RequestBulk, user: dict = Depends(get_current_user)):
    """Replace the requested-worker set for one site + date.
    Site supervisors may only touch their own site (enforced by RLS)."""
    if user["role"] not in ("admin", "main_sup", "site_sup"):
        raise HTTPException(status_code=403, detail="You cannot submit manpower requests")
    requested = set(body.worker_ids)

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{REST}/manpower_requests",
            params={"request_date": f"eq.{body.request_date}",
                    "site_id": f"eq.{body.site_id}",
                    "select": "id,worker_id"},
            headers=supabase_headers(user["token"]),
        )
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not check existing requests")
        existing = {a["worker_id"]: a["id"] for a in r.json()}

        to_remove = [aid for wid, aid in existing.items() if wid not in requested]
        to_add = [wid for wid in requested if wid not in existing]

        if to_remove:
            d = await client.delete(
                f"{REST}/manpower_requests",
                params={"id": f"in.({','.join(to_remove)})"},
                headers=supabase_headers(user["token"]),
            )
            if d.status_code not in (200, 204):
                raise HTTPException(status_code=500, detail="Could not update the request")

        if to_add:
            i = await client.post(
                f"{REST}/manpower_requests",
                headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                json=[{"request_date": body.request_date, "site_id": body.site_id,
                       "worker_id": wid, "note": body.note,
                       "created_by": user["user_id"], "updated_by": user["user_id"]}
                      for wid in to_add],
            )
            if i.status_code not in (200, 201):
                raise HTTPException(status_code=403,
                                    detail="Could not save — you can only request for your own site")

        await audit(client, user, "request_manpower", "manpower_request",
                    f"{body.request_date}:{body.site_id}",
                    {"worker_ids": sorted(existing.keys())},
                    {"worker_ids": sorted(requested)})
        return {"ok": True, "added": len(to_add), "removed": len(to_remove),
                "total": len(requested)}


# ---------------- OT Hours Engine (Phase 7 · spec §6, confirmed Rev 3) ----------------
def _to_min(t: str) -> int:
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


def compute_hours(day_type: str, start: str, end: str, end_next_day: bool) -> tuple[float, float]:
    """Returns (normal_hours, ot_hours) per the confirmed rules:
    R1 weekday 8h normal then OT · R2 1h lunch deducted ·
    R3 no lunch if finished by 12:00 noon · R4 Saturday OT after lunch ·
    R5 Sunday/PH all OT. Past-midnight credited to the start date."""
    s = _to_min(start)
    e_raw = _to_min(end)
    e = e_raw + (1440 if end_next_day else 0)
    if e <= s:
        raise ValueError("End time must be after start time")

    # R2/R3: deduct 1h lunch only when work spans the 12:00–13:00 window
    finished_by_noon = (not end_next_day) and e_raw <= 720
    lunch = 60 if (not finished_by_noon and s < 780 and e > 720) else 0
    worked = (e - s - lunch) / 60.0

    if day_type in ("SUN", "PH"):
        normal, ot = 0.0, worked                       # R5
    elif day_type == "SAT":
        morning = max(0, min(e, 720) - s) / 60.0       # R4: normal only before noon
        normal = min(4.0, morning, worked)
        ot = worked - normal
    else:  # WD
        normal = min(8.0, worked)                      # R1
        ot = max(0.0, worked - 8.0)

    # Company practice (CR 19/07/2026): OT counted in half-hour steps,
    # rounded DOWN (0.75 -> 0.5, 2.2 -> 2.0). Normal hours unchanged.
    ot = int(ot * 2) / 2
    return round(normal, 2), round(ot, 2)


def worked_hours(start: str, end: str, end_next_day: bool) -> float:
    """Hours actually worked in one segment, lunch rules R2/R3 applied."""
    s = _to_min(start)
    e_raw = _to_min(end)
    e = e_raw + (1440 if end_next_day else 0)
    if e <= s:
        raise ValueError("End time must be after start time")
    finished_by_noon = (not end_next_day) and e_raw <= 720
    lunch = 60 if (not finished_by_noon and s < 780 and e > 720) else 0
    return (e - s - lunch) / 60.0


def compute_day(day_type: str, segments: list[dict]) -> list[tuple[float, float]]:
    """Split-day support (site request 22/07/2026): a worker may work at more
    than one site in a day. Normal-hour quota is applied ONCE across his whole
    day, chronologically — so he is never paid two 'normal days'. Each site
    still keeps its own share of the hours.
    segments: [{'start','end','end_next_day'}, …]  ->  [(normal, ot), …]"""
    order = sorted(range(len(segments)),
                   key=lambda i: _to_min(segments[i]["start"]))
    out = [(0.0, 0.0)] * len(segments)

    if day_type in ("SUN", "PH"):
        for i in order:
            out[i] = (0.0, worked_hours(**segments[i]))
    elif day_type == "SAT":
        # R4: hours before 12:00 are normal (max 4 for the day), rest is OT
        remaining_normal = 4.0
        for i in order:
            g = segments[i]
            w = worked_hours(**g)
            s, e = _to_min(g["start"]), _to_min(g["end"]) + (1440 if g["end_next_day"] else 0)
            morning = max(0, min(e, 720) - s) / 60.0
            n = min(remaining_normal, morning, w)
            remaining_normal -= n
            out[i] = (n, w - n)
    else:  # weekday: 8 normal hours for the day, then OT (R1)
        remaining_normal = 8.0
        for i in order:
            w = worked_hours(**segments[i])
            n = min(remaining_normal, w)
            remaining_normal -= n
            out[i] = (n, w - n)

    # company practice: OT counted in half-hour steps, rounded down
    return [(round(n, 2), round(int(o * 2) / 2, 2)) for n, o in out]


async def get_day_type(client: httpx.AsyncClient, token: str, work_date: str) -> str:
    ph = await client.get(
        f"{REST}/public_holidays",
        params={"holiday_date": f"eq.{work_date}", "select": "holiday_date"},
        headers=supabase_headers(token),
    )
    if ph.status_code == 200 and ph.json():
        return "PH"
    wd = date_cls.fromisoformat(work_date).weekday()   # Mon=0 … Sun=6
    return "SAT" if wd == 5 else ("SUN" if wd == 6 else "WD")


# ---------------- Site Supervisor Module (Phase 7) ----------------
class AttendanceMark(BaseModel):
    allocation_id: str
    present: bool | None = None
    start_time: str | None = None      # admin/main_sup only (rain/permit delays)
    end_time: str | None = None        # "HH:MM"
    end_next_day: bool | None = None
    absence_type: str | None = None    # 'absent' | 'mc' (only when present=false)
    edit_reason: str | None = None


class BulkEnd(BaseModel):
    work_date: str
    site_id: str
    end_time: str


class SubmitDay(BaseModel):
    work_date: str
    site_id: str


async def _load_day(client, token, work_date: str, site_id: str | None):
    params = {"work_date": f"eq.{work_date}", "status": "eq.allocated",
              "select": "id,site_id,worker_id,sites(site_name),workers(name,worker_code),"
                        "attendance(id,present,start_time,end_time,end_next_day,"
                        "normal_hours,ot_hours,day_type,submitted_at,absence_type)"}
    if site_id:
        params["site_id"] = f"eq.{site_id}"
    r = await client.get(f"{REST}/allocations", params=params,
                         headers=supabase_headers(token))
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Could not load the day sheet")
    return r.json()


@app.get("/api/v1/attendance")
async def day_sheet(date: str, site_id: str = "",
                    user: dict = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=10) as client:
        rows = await _load_day(client, user["token"], date, site_id or None)
        out = []
        for a in rows:
            att = a.get("attendance") or None
            out.append({
                "allocation_id": a["id"], "site_id": a["site_id"],
                "site_name": (a.get("sites") or {}).get("site_name", "?"),
                "worker_name": (a.get("workers") or {}).get("name", "?"),
                "worker_code": (a.get("workers") or {}).get("worker_code", ""),
                "present": att["present"] if att else True,
                "start_time": (att["start_time"][:5] if att and att["start_time"] else "08:00"),
                "end_time": (att["end_time"][:5] if att and att["end_time"] else None),
                "end_next_day": att["end_next_day"] if att else False,
                "normal_hours": float(att["normal_hours"]) if att else 0,
                "ot_hours": float(att["ot_hours"]) if att else 0,
                "submitted": bool(att and att["submitted_at"]),
                "absence_type": (att.get("absence_type") if att else None) or "absent",
            })
        return sorted(out, key=lambda x: (x["site_name"], x["worker_name"]))


@app.patch("/api/v1/attendance/mark")
async def mark_attendance(body: AttendanceMark, user: dict = Depends(get_current_user)):
    if user["role"] not in ("admin", "main_sup", "site_sup"):
        raise HTTPException(status_code=403, detail="Not allowed")
    if body.start_time and user["role"] == "site_sup":
        raise HTTPException(status_code=403, detail="Start time can only be changed by the Main Supervisor or Administrator")

    async with httpx.AsyncClient(timeout=10) as client:
        # the allocation (RLS scopes site_sup to own sites automatically)
        ra = await client.get(
            f"{REST}/allocations",
            params={"id": f"eq.{body.allocation_id}",
                    "select": "id,work_date,site_id,attendance(id,present,start_time,end_time,end_next_day,submitted_at)"},
            headers=supabase_headers(user["token"]),
        )
        arows = ra.json() if ra.status_code == 200 else []
        if not arows:
            raise HTTPException(status_code=404, detail="Allocation not found (or not your site)")
        alloc = arows[0]
        att = alloc.get("attendance")

        # Submitted days remain correctable by the site's own supervisor until
        # payroll closes the month (decision 22/07/2026). Reason is mandatory
        # and the change is audit-logged.
        if att and att["submitted_at"] and not body.edit_reason:
            raise HTTPException(status_code=400, detail="A reason is required when changing a submitted day")

        start = body.start_time or (att["start_time"][:5] if att and att["start_time"] else "08:00")
        end = body.end_time if body.end_time is not None else (att["end_time"][:5] if att and att["end_time"] else None)
        end_nd = body.end_next_day if body.end_next_day is not None else (att["end_next_day"] if att else False)
        present = body.present if body.present is not None else (att["present"] if att else True)

        if user["role"] != "admin" and await month_locked(client, user["token"], alloc["work_date"]):
            raise HTTPException(status_code=403, detail="Month closed by payroll — administrator only")

        day_type = await get_day_type(client, user["token"], alloc["work_date"])
        normal, ot = (0.0, 0.0)
        if present and end:
            try:
                normal, ot = compute_hours(day_type, start, end, end_nd)
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))
        # (recomputed at day level below if the worker has more than one site today)

        if body.absence_type and body.absence_type not in ("absent", "mc"):
            raise HTTPException(status_code=400, detail="Invalid absence type")
        absence = None if present else (
            body.absence_type or (att.get("absence_type") if att else None) or "absent")

        payload = {"present": present, "start_time": start, "end_time": end,
                   "end_next_day": end_nd, "normal_hours": normal, "ot_hours": ot,
                   "day_type": day_type, "absence_type": absence,
                   "edit_reason": body.edit_reason}
        if att:
            ru = await client.patch(
                f"{REST}/attendance", params={"id": f"eq.{att['id']}"},
                headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
                json=payload)
        else:
            ru = await client.post(
                f"{REST}/attendance",
                headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
                json={**payload, "allocation_id": body.allocation_id})
        if ru.status_code not in (200, 201) or not ru.json():
            raise HTTPException(status_code=500, detail="Could not save attendance")

        # split-day: if this worker worked at more than one site today,
        # recalculate the whole day so the 8-hour normal quota is applied once
        res = await recompute_worker_day(client, user["token"],
                                         alloc["work_date"], alloc["worker_id"], day_type)
        if res:
            normal, ot = res.get(body.allocation_id, (normal, ot))

        await audit(client, user, "mark_attendance", "attendance", body.allocation_id,
                    {k: att.get(k) for k in ("present", "end_time")} if att else None,
                    {"present": present, "end_time": end, "normal": normal, "ot": ot})
        return {"ok": True, "normal_hours": normal, "ot_hours": ot, "day_type": day_type}


async def recompute_worker_day(client, token, work_date: str, worker_id: str,
                               day_type: str) -> dict:
    """When a worker has 2+ sites on the same date, recompute all his segments
    together so normal hours are counted once for the day (site request 22/07/2026).
    Returns {allocation_id: (normal, ot)} or {} if he only has one site."""
    r = await client.get(
        f"{REST}/allocations",
        params={"work_date": f"eq.{work_date}", "worker_id": f"eq.{worker_id}",
                "status": "eq.allocated",
                "select": "id,attendance(id,present,start_time,end_time,end_next_day)"},
        headers=supabase_headers(token))
    rows = r.json() if r.status_code == 200 else []
    segs, ids = [], []
    for a in rows:
        att = a.get("attendance")
        if not att or not att["present"] or not att["end_time"]:
            continue
        segs.append({"start": att["start_time"][:5], "end": att["end_time"][:5],
                     "end_next_day": att["end_next_day"]})
        ids.append((a["id"], att["id"]))
    if len(segs) < 2:
        return {}
    try:
        pairs = compute_day(day_type, segs)
    except ValueError:
        return {}
    out = {}
    for (alloc_id, att_id), (n, o) in zip(ids, pairs):
        await client.patch(f"{REST}/attendance", params={"id": f"eq.{att_id}"},
                           headers={**supabase_headers(token), "Prefer": "return=minimal"},
                           json={"normal_hours": n, "ot_hours": o})
        out[alloc_id] = (n, o)
    return out


@app.post("/api/v1/attendance/bulk_end")
async def bulk_end(body: BulkEnd, user: dict = Depends(get_current_user)):
    if user["role"] not in ("admin", "main_sup", "site_sup"):
        raise HTTPException(status_code=403, detail="Not allowed")
    async with httpx.AsyncClient(timeout=15) as client:
        rows = await _load_day(client, user["token"], body.work_date, body.site_id)
        if not rows:
            raise HTTPException(status_code=404, detail="No allocation for that site/date (or not your site)")
        if user["role"] != "admin" and await month_locked(client, user["token"], body.work_date):
            raise HTTPException(status_code=403, detail="Month closed by payroll — administrator only")
        day_type = await get_day_type(client, user["token"], body.work_date)
        updated = 0
        for a in rows:
            att = a.get("attendance")
            if att and att["submitted_at"]:
                continue
            present = att["present"] if att else True
            if not present:
                continue
            start = att["start_time"][:5] if att and att["start_time"] else "08:00"
            normal, ot = compute_hours(day_type, start, body.end_time, False)
            payload = {"present": True, "start_time": start, "end_time": body.end_time,
                       "end_next_day": False, "normal_hours": normal, "ot_hours": ot,
                       "day_type": day_type}
            if att:
                await client.patch(f"{REST}/attendance", params={"id": f"eq.{att['id']}"},
                                   headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                                   json=payload)
            else:
                await client.post(f"{REST}/attendance",
                                  headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                                  json={**payload, "allocation_id": a["id"]})
            updated += 1
        await audit(client, user, "bulk_end", "attendance",
                    f"{body.work_date}:{body.site_id}", None,
                    {"end_time": body.end_time, "workers": updated})
        return {"ok": True, "updated": updated}


@app.post("/api/v1/attendance/submit")
async def submit_day(body: SubmitDay, user: dict = Depends(get_current_user)):
    if user["role"] not in ("admin", "site_sup"):
        raise HTTPException(status_code=403, detail="Only the Site Supervisor or Administrator can submit")
    async with httpx.AsyncClient(timeout=15) as client:
        rows = await _load_day(client, user["token"], body.work_date, body.site_id)
        if not rows:
            raise HTTPException(status_code=404, detail="No allocation for that site/date (or not your site)")
        if user["role"] != "admin" and await month_locked(client, user["token"], body.work_date):
            raise HTTPException(status_code=403, detail="Month closed by payroll — administrator only")
        missing = [
            (a.get("workers") or {}).get("name", "?")
            for a in rows
            if not a.get("attendance")
            or (a["attendance"]["present"] and not a["attendance"]["end_time"])
        ]
        if missing:
            raise HTTPException(status_code=400,
                                detail="End time missing for: " + ", ".join(missing[:5]) +
                                       (f" (+{len(missing)-5} more)" if len(missing) > 5 else ""))
        att_ids = [a["attendance"]["id"] for a in rows if a.get("attendance")]
        r = await client.patch(
            f"{REST}/attendance",
            params={"id": f"in.({','.join(att_ids)})"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
            json={"submitted_at": "now()", "submitted_by": user["user_id"]},
        )
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not submit the day")
        await audit(client, user, "submit_day", "attendance",
                    f"{body.work_date}:{body.site_id}", None, {"workers": len(att_ids)})
        return {"ok": True, "submitted": len(att_ids)}


# ---------------- Wrong-site transfer (site request 22/07/2026) ----------------
class TransferBody(BaseModel):
    work_date: str
    worker_id: str
    to_site_id: str
    keep_other: bool = False   # True = split day (also worked at the other site)


@app.get("/api/v1/attendance/transferable")
async def transferable_workers(date: str, site_id: str,
                               user: dict = Depends(get_current_user)):
    """Workers who did NOT turn up at their allocated site — i.e. everyone
    allocated elsewhere today, plus anyone unallocated. Used when a worker
    reports to the wrong site in the morning."""
    if user["role"] not in ("admin", "main_sup", "site_sup"):
        raise HTTPException(status_code=403, detail="Not allowed")
    async with httpx.AsyncClient(timeout=15) as client:
        ra = await client.get(
            f"{REST}/allocations",
            params={"work_date": f"eq.{date}", "status": "eq.allocated",
                    "select": "worker_id,site_id,sites(site_name),workers(name,worker_code),"
                              "attendance(submitted_at)"},
            headers=supabase_headers(user["token"]))
        allocs = ra.json() if ra.status_code == 200 else []

        rw = await client.get(
            f"{REST}/workers",
            params={"status": "eq.active", "select": "id,name,worker_code", "order": "name.asc"},
            headers=supabase_headers(user["token"]))
        workers = rw.json() if rw.status_code == 200 else []

        alloc_by_worker = {a["worker_id"]: a for a in allocs}
        out = []
        for w in workers:
            a = alloc_by_worker.get(w["id"])
            if a and a["site_id"] == site_id:
                continue                      # already here
            if a and (a.get("attendance") or {}).get("submitted_at"):
                continue                      # their day is already closed elsewhere
            out.append({
                "worker_id": w["id"], "name": w["name"], "worker_code": w["worker_code"],
                "current_site": (a.get("sites") or {}).get("site_name") if a else None,
            })
        return out


@app.post("/api/v1/attendance/transfer")
async def transfer_worker(body: TransferBody, user: dict = Depends(get_current_user)):
    """Move a worker's allocation to the site where he actually reported.
    Allowed for admin, main_sup, and the receiving site's supervisor."""
    if user["role"] not in ("admin", "main_sup", "site_sup"):
        raise HTTPException(status_code=403, detail="Not allowed")
    async with httpx.AsyncClient(timeout=15) as client:
        if user["role"] != "admin" and await month_locked(client, user["token"], body.work_date):
            raise HTTPException(status_code=403, detail="Month closed by payroll — administrator only")

        r = await client.get(
            f"{REST}/allocations",
            params={"work_date": f"eq.{body.work_date}", "worker_id": f"eq.{body.worker_id}",
                    "select": "id,site_id,sites(site_name),workers(name),attendance(id,submitted_at)"},
            headers=supabase_headers(user["token"]))
        rows = r.json() if r.status_code == 200 else []

        rows = [a for a in rows if a["site_id"] != body.to_site_id]
        if rows and body.keep_other:
            # SPLIT DAY: keep the other site's record and add this site too
            ins = await client.post(
                f"{REST}/allocations",
                headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                json={"work_date": body.work_date, "site_id": body.to_site_id,
                      "worker_id": body.worker_id, "status": "allocated",
                      "created_by": user["user_id"], "updated_by": user["user_id"]})
            if ins.status_code not in (200, 201):
                raise HTTPException(status_code=500,
                                    detail="Could not add the second site — the database may not allow split days yet")
            await audit(client, user, "split_day", "allocation",
                        f"{body.work_date}:{body.worker_id}", None,
                        {"added_site": body.to_site_id, "reason": "worked at two sites today"})
            return {"ok": True, "moved": True, "split": True,
                    "from": (rows[0].get("sites") or {}).get("site_name", "?")}

        if rows:
            a = rows[0]
            att = a.get("attendance")
            if att and att.get("submitted_at"):
                raise HTTPException(
                    status_code=400,
                    detail="That worker's day was already submitted at " +
                           ((a.get("sites") or {}).get("site_name", "the other site")) +
                           " — ask the administrator")
            up = await client.patch(
                f"{REST}/allocations", params={"id": f"eq.{a['id']}"},
                headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                json={"site_id": body.to_site_id, "updated_by": user["user_id"]})
            if up.status_code not in (200, 204):
                raise HTTPException(status_code=500, detail="Could not move the worker")
            await audit(client, user, "transfer_worker", "allocation", a["id"],
                        {"site_id": a["site_id"], "site": (a.get("sites") or {}).get("site_name")},
                        {"site_id": body.to_site_id, "reason": "reported to this site"})
            return {"ok": True, "moved": True,
                    "from": (a.get("sites") or {}).get("site_name", "?"),
                    "worker": (a.get("workers") or {}).get("name", "?")}

        # not allocated anywhere today -> allocate him here
        ins = await client.post(
            f"{REST}/allocations",
            headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
            json={"work_date": body.work_date, "site_id": body.to_site_id,
                  "worker_id": body.worker_id, "status": "allocated",
                  "created_by": user["user_id"], "updated_by": user["user_id"]})
        if ins.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Could not add the worker")
        await audit(client, user, "transfer_worker", "allocation",
                    f"{body.work_date}:{body.worker_id}", None,
                    {"site_id": body.to_site_id, "reason": "unallocated, reported to this site"})
        return {"ok": True, "moved": True, "from": None}


# ---------------- WhatsApp Generators (Phase 9 · spec §7, real formats) ----------------
MONTHS = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY",
          "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
DIVIDER = "________________________________"


def format_allocation_message(work_date: str, site_names: list[str],
                              by_site: dict[str, list[str]],
                              home_leave: list[str]) -> str:
    """Spec §7.1 (Rev 7 format): worker lines are WORKERID_NAME, all caps."""
    d = date_cls.fromisoformat(work_date)
    lines = ["*MANPOWER DISTRIBUTION*",
             f"*{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}*",
             f"*{DAYS[d.weekday()]}*"]
    for sname in site_names:
        lines.append(DIVIDER)
        lines.append(f"*{sname.upper()}*")
        for i, x in enumerate(by_site.get(sname, []), 1):
            lines.append(f"{i}. {x.upper()}")
    if home_leave:
        lines.append(DIVIDER)
        lines.append("*HOME LEAVE*")
        for i, x in enumerate(home_leave, 1):
            lines.append(f"{i}. {x.upper()}")
    return "\n".join(lines)


def format_update_message(work_date: str, site_name: str, supervisor: str,
                          rows: list[dict]) -> str:
    """Spec §7.2 (Rev 7 format): WORKERID_NAME_ENDTIME, all caps.
    Non-default starts shown as WORKERID_NAME_START-END."""
    d = date_cls.fromisoformat(work_date)
    lines = [f"*SITE: {site_name.upper()}*",
             f"*DATE: {d.day:02d}/{d.month:02d}/{d.year}*",
             f"*SUPERVISOR: {supervisor.upper()}*",
             ""]
    n = 0
    for r in rows:
        n += 1
        t = r["end_time"]
        if r.get("start_time") and r["start_time"] != "08:00":
            t = f'{r["start_time"]}-{r["end_time"]}'
        lines.append(f'{n}.{r["code"]}_{r["name"].upper()}_{t}')
    return "\n".join(lines)


@app.get("/api/v1/messages/allocation")
async def allocation_message(date: str, user: dict = Depends(get_current_user)):
    if user["role"] not in ("admin", "main_sup"):
        raise HTTPException(status_code=403, detail="Only the Main Supervisor or Administrator can generate this message")
    async with httpx.AsyncClient(timeout=10) as client:
        rs = await client.get(f"{REST}/sites",
                              params={"status": "eq.active", "select": "id,site_name", "order": "site_name.asc"},
                              headers=supabase_headers(user["token"]))
        sites = rs.json() if rs.status_code == 200 else []
        ra = await client.get(f"{REST}/allocations",
                              params={"work_date": f"eq.{date}", "status": "eq.allocated",
                                      "select": "site_id,workers(name,worker_code),sites(site_name)"},
                              headers=supabase_headers(user["token"]))
        allocs = ra.json() if ra.status_code == 200 else []
        rw = await client.get(f"{REST}/workers",
                              params={"status": "eq.on_leave", "select": "name,worker_code",
                                      "order": "name.asc"},
                              headers=supabase_headers(user["token"]))
        leave = [f'{w["worker_code"]}_{w["name"]}'
                 for w in (rw.json() if rw.status_code == 200 else [])]

        by_site: dict[str, list[str]] = {}
        for a in allocs:
            sname = (a.get("sites") or {}).get("site_name", "?")
            w = a.get("workers") or {}
            by_site.setdefault(sname, []).append(
                f'{w.get("worker_code", "?")}_{w.get("name", "?")}')
        for k in by_site:
            by_site[k].sort()

        msg = format_allocation_message(date, [s["site_name"] for s in sites], by_site, leave)
        await audit(client, user, "generate_allocation_msg", "message", date, None,
                    {"workers": len(allocs)})
        return {"message": msg, "workers": len(allocs), "sites": len(sites),
                "home_leave": len(leave)}


@app.get("/api/v1/messages/update")
async def update_message(date: str, site_id: str,
                         user: dict = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=10) as client:
        rows = await _load_day(client, user["token"], date, site_id)
        if not rows:
            raise HTTPException(status_code=404, detail="No allocation for that site/date (or not your site)")
        site_name = (rows[0].get("sites") or {}).get("site_name", "?")

        present, missing = [], 0
        for a in rows:
            att = a.get("attendance")
            if not att or not att["present"]:
                continue
            if not att["end_time"]:
                missing += 1
                continue
            present.append({"name": (a.get("workers") or {}).get("name", "?"),
                            "code": (a.get("workers") or {}).get("worker_code", "?"),
                            "start_time": att["start_time"][:5] if att["start_time"] else "08:00",
                            "end_time": att["end_time"][:5]})
        present.sort(key=lambda x: x["name"])

        msg = format_update_message(date, site_name, user["name"], present)
        await audit(client, user, "generate_update_msg", "message",
                    f"{date}:{site_id}", None, {"workers": len(present)})
        return {"message": msg, "workers": len(present), "missing_end_time": missing}


def format_request_message(request_date: str, by_site: dict[str, list[str]]) -> str:
    """Consolidated manpower request summary the allocator posts in the group."""
    d = date_cls.fromisoformat(request_date)
    lines = ["*MANPOWER REQUEST*",
             f"*{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}*",
             f"*{DAYS[d.weekday()]}*"]
    total = 0
    for sname in sorted(by_site.keys()):
        workers = by_site[sname]
        total += len(workers)
        lines.append(DIVIDER)
        lines.append(f"*{sname.upper()}*  ({len(workers)})")
        for i, x in enumerate(sorted(workers), 1):
            lines.append(f"{i}. {x.upper()}")
    lines.append(DIVIDER)
    lines.append(f"*TOTAL REQUESTED: {total}*")
    return "\n".join(lines)


@app.get("/api/v1/messages/requests")
async def request_message(date: str, user: dict = Depends(get_current_user)):
    # admin/main_sup get the consolidated (all sites) message;
    # a site supervisor gets only their own site's request (RLS scopes the query).
    if user["role"] not in ("admin", "main_sup", "site_sup"):
        raise HTTPException(status_code=403, detail="You cannot generate this message")
    async with httpx.AsyncClient(timeout=10) as client:
        rr = await client.get(
            f"{REST}/manpower_requests",
            params={"request_date": f"eq.{date}",
                    "select": "site_id,workers(name,worker_code),sites(site_name)"},
            headers=supabase_headers(user["token"]),
        )
        rows = rr.json() if rr.status_code == 200 else []
        by_site: dict[str, list[str]] = {}
        for a in rows:
            sname = (a.get("sites") or {}).get("site_name", "?")
            w = a.get("workers") or {}
            by_site.setdefault(sname, []).append(
                f'{w.get("worker_code", "?")}_{w.get("name", "?")}')
        msg = format_request_message(date, by_site)
        await audit(client, user, "generate_request_msg", "message", date, None,
                    {"workers": len(rows), "sites": len(by_site)})
        return {"message": msg, "workers": len(rows), "sites": len(by_site)}


# ---------------- Dashboard (Phase 10 · spec §8) ----------------
from datetime import datetime, timedelta, timezone


def sgt_today() -> str:
    """Working dates are SGT dates (spec §12)."""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()


@app.get("/api/v1/dashboard")
async def dashboard(date: str = "", user: dict = Depends(get_current_user)):
    # `date` lets the user view any day; defaults to today (SGT).
    today = date or sgt_today()
    month_start = today[:8] + "01"

    async with httpx.AsyncClient(timeout=15) as client:
        rw = await client.get(f"{REST}/workers",
                              params={"select": "id,status"},
                              headers=supabase_headers(user["token"]))
        workers = rw.json() if rw.status_code == 200 else []
        scoped = user["role"] == "site_sup"

        rs = await client.get(f"{REST}/sites",
                              params={"status": "eq.active", "select": "id,site_name"},
                              headers=supabase_headers(user["token"]))
        sites = rs.json() if rs.status_code == 200 else []

        # Site Supervisors see only their own sites (request 22/07/2026)
        if user["role"] == "site_sup":
            rl = await client.get(f"{REST}/site_supervisors",
                                  params={"user_id": f"eq.{user['user_id']}", "select": "site_id"},
                                  headers=supabase_headers(user["token"]))
            mine = {x["site_id"] for x in (rl.json() if rl.status_code == 200 else [])}
            sites = [s for s in sites if s["id"] in mine]

        # everything in the selected date's month, up to and including that date
        rm = await client.get(
            f"{REST}/allocations",
            params={"and": f"(work_date.gte.{month_start},work_date.lte.{today})",
                    "status": "eq.allocated",
                    "select": "work_date,site_id,sites(site_name),"
                              "attendance(present,submitted_at,normal_hours,ot_hours,absence_type)"},
            headers=supabase_headers(user["token"]))
        month_rows = rm.json() if rm.status_code == 200 else []

        month_nh = month_ot = 0.0
        today_mc = 0
        today_by_site: dict[str, dict] = {}
        site_month: dict[str, dict] = {}

        for a in month_rows:
            sname = (a.get("sites") or {}).get("site_name", "?")
            att = a.get("attendance")
            nh = float(att["normal_hours"]) if att and att["present"] else 0.0
            ot = float(att["ot_hours"]) if att and att["present"] else 0.0
            month_nh += nh
            month_ot += ot

            sm = site_month.setdefault(sname, {"nh": 0.0, "ot": 0.0})
            sm["nh"] += nh
            sm["ot"] += ot

            if a["work_date"] == today:
                t = today_by_site.setdefault(sname, {"allocated": 0, "submitted": 0, "with_att": 0})
                t["allocated"] += 1
                if att:
                    t["with_att"] += 1
                    if att["submitted_at"]:
                        t["submitted"] += 1
                    if not att["present"] and att.get("absence_type") == "mc":
                        today_mc += 1

        pending, completed = [], []
        for sname, t in today_by_site.items():
            if t["allocated"] > 0 and t["submitted"] >= t["allocated"] and t["allocated"] == t["with_att"]:
                completed.append(sname)
            else:
                pending.append(sname)

        summary = [{"site_name": s["site_name"],
                    "today": today_by_site.get(s["site_name"], {}).get("allocated", 0),
                    "month_nh": round(site_month.get(s["site_name"], {}).get("nh", 0), 1),
                    "month_ot": round(site_month.get(s["site_name"], {}).get("ot", 0), 1)}
                   for s in sites]

        return {
            "date": today,
            "scoped": scoped,
            "total_workers": (sum(t["allocated"] for t in today_by_site.values())
                              if scoped else sum(1 for w in workers if w["status"] == "active")),
            "on_leave": 0 if scoped else sum(1 for w in workers if w["status"] == "on_leave"),
            "total_sites": len(sites),
            "today_allocated": sum(t["allocated"] for t in today_by_site.values()),
            "today_mc": today_mc,
            "pending_updates": sorted(pending),
            "completed_updates": sorted(completed),
            "month_normal_hours": round(month_nh, 1),
            "month_ot_hours": round(month_ot, 1),
            "site_summary": summary,
        }


# ---------------- Reports & Monthly Man-Hours (Phases 11–12 · spec §9) ----------------
async def month_locked(client: httpx.AsyncClient, token: str, work_date: str) -> bool:
    m = work_date[:7] + "-01"
    r = await client.get(f"{REST}/month_locks",
                         params={"month": f"eq.{m}", "select": "month"},
                         headers=supabase_headers(token))
    return r.status_code == 200 and bool(r.json())


async def _range_rows(client, token, dfrom: str, dto: str, site_id: str | None):
    params = {"work_date": f"gte.{dfrom}", "status": "eq.allocated",
              "select": "work_date,site_id,sites(site_name),"
                        "workers(name,worker_code),"
                        "attendance(present,start_time,end_time,normal_hours,ot_hours,day_type,submitted_at,absence_type)",
              "order": "work_date.asc"}
    r = await client.get(f"{REST}/allocations",
                         params={**params, "and": f"(work_date.lte.{dto}" + (f",site_id.eq.{site_id}" if site_id else "") + ")"},
                         headers=supabase_headers(token))
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Could not load report data")
    return r.json()


@app.get("/api/v1/reports/attendance")
async def report_attendance(dfrom: str, dto: str, site_id: str = "",
                            user: dict = Depends(get_current_user)):
    d1, d2 = date_cls.fromisoformat(dfrom), date_cls.fromisoformat(dto)
    if d2 < d1 or (d2 - d1).days > 62:
        raise HTTPException(status_code=400, detail="Date range must be 1–62 days")
    async with httpx.AsyncClient(timeout=20) as client:
        rows = await _range_rows(client, user["token"], dfrom, dto, site_id or None)
        out = []
        for a in rows:
            att = a.get("attendance")
            out.append({
                "date": a["work_date"],
                "site": (a.get("sites") or {}).get("site_name", "?"),
                "worker_code": (a.get("workers") or {}).get("worker_code", ""),
                "worker": (a.get("workers") or {}).get("name", "?"),
                "present": att["present"] if att else None,
                "absence": ((att.get("absence_type") or "absent") if att and not att["present"] else ""),
                "start": att["start_time"][:5] if att and att["start_time"] else "",
                "end": att["end_time"][:5] if att and att["end_time"] else "",
                "nh": float(att["normal_hours"]) if att and att["present"] else 0,
                "ot": float(att["ot_hours"]) if att and att["present"] else 0,
                "day_type": att["day_type"] if att else "",
                "submitted": bool(att and att["submitted_at"]),
            })
        return out


@app.get("/api/v1/reports/manhours")
async def report_manhours(month: str, user: dict = Depends(get_current_user)):
    # month = YYYY-MM
    dfrom = month + "-01"
    y, m = int(month[:4]), int(month[5:7])
    dto = (date_cls(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)).isoformat()
    async with httpx.AsyncClient(timeout=20) as client:
        rows = await _range_rows(client, user["token"], dfrom, dto, None)
        sites: dict[str, dict] = {}
        workers: dict[str, dict] = {}
        for a in rows:
            att = a.get("attendance")
            if not att or not att["present"]:
                continue
            sname = (a.get("sites") or {}).get("site_name", "?")
            w = a.get("workers") or {}
            nh, ot = float(att["normal_hours"]), float(att["ot_hours"])

            s = sites.setdefault(sname, {"days": set(), "workers": set(), "nh": 0.0, "ot": 0.0})
            s["days"].add(a["work_date"])
            s["workers"].add(w.get("worker_code", "?"))
            s["nh"] += nh
            s["ot"] += ot

            wk = workers.setdefault(w.get("worker_code", "?"),
                                    {"name": w.get("name", "?"), "days": 0, "nh": 0.0, "ot": 0.0})
            wk["days"] += 1
            wk["nh"] += nh
            wk["ot"] += ot

        locked = await month_locked(client, user["token"], dfrom)
        return {
            "month": month, "locked": locked,
            "sites": [{"site": k, "attendance_days": len(v["days"]),
                       "total_workers": len(v["workers"]),
                       "nh": round(v["nh"], 1), "ot": round(v["ot"], 1)}
                      for k, v in sorted(sites.items())],
            "workers": [{"worker_code": k, "name": v["name"], "days": v["days"],
                         "nh": round(v["nh"], 1), "ot": round(v["ot"], 1)}
                        for k, v in sorted(workers.items())],
            "totals": {"nh": round(sum(v["nh"] for v in sites.values()), 1),
                       "ot": round(sum(v["ot"] for v in sites.values()), 1)},
        }


class MonthBody(BaseModel):
    month: str  # YYYY-MM


@app.post("/api/v1/months/lock")
async def lock_month(body: MonthBody, user: dict = Depends(get_current_user)):
    if user["role"] not in ("admin", "payroll"):
        raise HTTPException(status_code=403, detail="Only Payroll or the Administrator can close a month")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{REST}/month_locks",
            params={"on_conflict": "month"},
            headers={**supabase_headers(user["token"]),
                     "Prefer": "return=minimal,resolution=ignore-duplicates"},
            json={"month": body.month + "-01", "locked_by": user["user_id"]})
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Could not close the month")
        await audit(client, user, "lock_month", "month", body.month, None, {"locked": True})
        return {"ok": True, "month": body.month, "locked": True}


@app.post("/api/v1/months/unlock")
async def unlock_month(body: MonthBody, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the Administrator can re-open a month")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.delete(
            f"{REST}/month_locks",
            params={"month": f"eq.{body.month}-01"},
            headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not re-open the month")
        await audit(client, user, "unlock_month", "month", body.month, {"locked": True}, {"locked": False})
        return {"ok": True, "month": body.month, "locked": False}


# ---------------- Settings & Public Holidays (Phase 12) ----------------
class HolidayBody(BaseModel):
    holiday_date: str
    description: str


@app.get("/api/v1/holidays")
async def list_holidays(user: dict = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{REST}/public_holidays",
                             params={"select": "holiday_date,description", "order": "holiday_date.asc"},
                             headers=supabase_headers(user["token"]))
        return r.json() if r.status_code == 200 else []


@app.post("/api/v1/holidays", status_code=201)
async def add_holiday(body: HolidayBody, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the administrator can edit holidays")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{REST}/public_holidays",
                              headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                              json={"holiday_date": body.holiday_date, "description": body.description.strip()})
        if r.status_code == 409:
            raise HTTPException(status_code=409, detail="That date is already a holiday")
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Could not save holiday")
        await audit(client, user, "add_holiday", "holiday", body.holiday_date, None,
                    {"description": body.description})
        return {"ok": True}


@app.delete("/api/v1/holidays/{holiday_date}")
async def delete_holiday(holiday_date: str, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the administrator can edit holidays")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.delete(f"{REST}/public_holidays",
                                params={"holiday_date": f"eq.{holiday_date}"},
                                headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete holiday")
        await audit(client, user, "delete_holiday", "holiday", holiday_date, None, None)
        return {"ok": True}


@app.get("/api/v1/settings")
async def list_settings(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{REST}/settings",
                             params={"select": "key,value,effective_from", "order": "key.asc"},
                             headers=supabase_headers(user["token"]))
        return r.json() if r.status_code == 200 else []
