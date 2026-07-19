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

app = FastAPI(title="VMMS API", version="0.7.0")

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
    return {"app": "VMMS", "phase": 7, "status": "running"}


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
    return {"name": user["name"], "role": user["role"], "email": user["email"]}


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

    return round(normal, 2), round(ot, 2)


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
                        "normal_hours,ot_hours,day_type,submitted_at)"}
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

        if att and att["submitted_at"] and user["role"] == "site_sup":
            raise HTTPException(status_code=403, detail="Day already submitted — ask the administrator to amend")
        if att and att["submitted_at"] and not body.edit_reason:
            raise HTTPException(status_code=400, detail="A reason is required when editing a submitted day")

        start = body.start_time or (att["start_time"][:5] if att and att["start_time"] else "08:00")
        end = body.end_time if body.end_time is not None else (att["end_time"][:5] if att and att["end_time"] else None)
        end_nd = body.end_next_day if body.end_next_day is not None else (att["end_next_day"] if att else False)
        present = body.present if body.present is not None else (att["present"] if att else True)

        day_type = await get_day_type(client, user["token"], alloc["work_date"])
        normal, ot = (0.0, 0.0)
        if present and end:
            try:
                normal, ot = compute_hours(day_type, start, end, end_nd)
            except ValueError as ve:
                raise HTTPException(status_code=400, detail=str(ve))

        payload = {"present": present, "start_time": start, "end_time": end,
                   "end_next_day": end_nd, "normal_hours": normal, "ot_hours": ot,
                   "day_type": day_type, "edit_reason": body.edit_reason}
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

        await audit(client, user, "mark_attendance", "attendance", body.allocation_id,
                    {k: att.get(k) for k in ("present", "end_time")} if att else None,
                    {"present": present, "end_time": end, "normal": normal, "ot": ot})
        return {"ok": True, "normal_hours": normal, "ot_hours": ot, "day_type": day_type}


@app.post("/api/v1/attendance/bulk_end")
async def bulk_end(body: BulkEnd, user: dict = Depends(get_current_user)):
    if user["role"] not in ("admin", "main_sup", "site_sup"):
        raise HTTPException(status_code=403, detail="Not allowed")
    async with httpx.AsyncClient(timeout=15) as client:
        rows = await _load_day(client, user["token"], body.work_date, body.site_id)
        if not rows:
            raise HTTPException(status_code=404, detail="No allocation for that site/date (or not your site)")
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
