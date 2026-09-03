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
from __future__ import annotations

import asyncio
import re
from datetime import date as date_cls, datetime, timedelta, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel

from .auth import (
    cache_user as _cache_put,
    get_current_user,
    invalidate_users as _cache_invalidate_users,
)

from .core.roles import (
    ALL_ROLES, ATTENDANCE_ROLES, COORDINATOR_ROLES, FULL_ROLES,
    MANAGER_ROLES, SUPERVISOR_ROLES,
)
from .db import (
    close_http_client, require_service, service_headers, shared_client,
    supabase_headers,
)
from .errors import install_error_handlers
from .settings import (
    R2_ENABLED, R2_PUBLIC_BASE, REST, SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_KEY, SUPABASE_URL,
)
from .storage import r2_presign_delete as _r2_presign_delete
from .storage import r2_presign_put as _r2_presign_put
from .modules.planning.router import PlanningContext, build_planning_router; from .modules.pcs_router import PcsContext, build_pcs_router; from .modules.pcs_plan_router import PcsPlanContext, build_pcs_plan_router; from .modules.pcs_report_router import PcsReportContext, build_pcs_report_router
from .modules.projects.router import ProjectModuleContext, build_projects_router
from .modules.equipment.router import EquipmentContext, build_equipment_router

app = FastAPI(title="VCMS API", version="0.88.0")
install_error_handlers(app)
app.add_middleware(GZipMiddleware, minimum_size=750, compresslevel=5)

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



@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(self), microphone=(), geolocation=(), payment=(), usb=()"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.on_event("shutdown")
async def _close_http():
    await close_http_client()


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


app.include_router(build_projects_router(ProjectModuleContext(
    get_current_user=get_current_user, shared_client=shared_client, rest_url=REST,
    supabase_headers=supabase_headers, audit=audit,
)))
app.include_router(build_pcs_report_router(PcsReportContext(get_current_user=get_current_user, shared_client=shared_client, rest_url=REST, supabase_headers=supabase_headers, audit=audit))); app.include_router(build_pcs_plan_router(PcsPlanContext(get_current_user=get_current_user, shared_client=shared_client, rest_url=REST, supabase_headers=supabase_headers, audit=audit))); app.include_router(build_pcs_router(PcsContext(get_current_user=get_current_user, shared_client=shared_client, rest_url=REST, supabase_headers=supabase_headers, audit=audit))); app.include_router(build_planning_router(PlanningContext(
    get_current_user=get_current_user, shared_client=shared_client, rest_url=REST,
    supabase_headers=supabase_headers, audit=audit,
)))
app.include_router(build_equipment_router(EquipmentContext(
    get_current_user=get_current_user, shared_client=shared_client, rest_url=REST,
    supabase_headers=supabase_headers, audit=audit, r2_public_base=R2_PUBLIC_BASE,
)))


@app.get("/api/v1/audit-log")
async def get_audit_log(date_from: str | None = None, date_to: str | None = None,
                        action: str | None = None, actor_id: str | None = None,
                        limit: int = 200, user: dict = Depends(get_current_user)):
    """Administrator-only, read-only audit history for the VCMS Audit Log page."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Administrator only")
    try:
        start = date_cls.fromisoformat(date_from) if date_from else date_cls.today() - timedelta(days=6)
        end = date_cls.fromisoformat(date_to) if date_to else date_cls.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date")
    if end < start or (end - start).days > 92:
        raise HTTPException(status_code=400, detail="Choose a date range up to 93 days")
    limit = max(1, min(limit, 500))
    filters = [f"at.gte.{start.isoformat()}T00:00:00+08:00",
               f"at.lt.{(end + timedelta(days=1)).isoformat()}T00:00:00+08:00"]
    if action:
        filters.append(f"action.eq.{action}")
    if actor_id:
        filters.append(f"user_id.eq.{actor_id}")
    async with shared_client() as client:
        r = await client.get(
            f"{REST}/audit_log",
            params={"select": "id,user_id,action,entity,entity_id,old_value,new_value,at,users(name)",
                    "and": "(" + ",".join(filters) + ")", "order": "at.desc", "limit": str(limit)},
            headers=supabase_headers(user["token"]),
        )
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load audit log")
        rows = r.json()
        site_ids = set()
        for row in rows:
            if row.get("action") == "request_manpower" and ":" in (row.get("entity_id") or ""):
                site_ids.add(row["entity_id"].split(":", 1)[1])
        site_names = {}
        if site_ids:
            sr = await client.get(f"{REST}/sites",
                params={"id": f"in.({','.join(site_ids)})", "select": "id,site_name"},
                headers=supabase_headers(user["token"]))
            if sr.status_code == 200:
                site_names = {x["id"]: x["site_name"] for x in sr.json()}
        items = []
        for row in rows:
            entity_id = row.get("entity_id") or ""
            site_name = None
            if row.get("action") == "request_manpower" and ":" in entity_id:
                site_name = site_names.get(entity_id.split(":", 1)[1])
            items.append({
                "id": row["id"], "at": row["at"], "user_id": row.get("user_id"),
                "user_name": (row.get("users") or {}).get("name") or "Unknown user",
                "action": row["action"], "entity": row["entity"], "entity_id": entity_id,
                "site_name": site_name, "old_value": row.get("old_value"),
                "new_value": row.get("new_value"),
            })
        actors = sorted({(x["user_id"], x["user_name"]) for x in items if x["user_id"]}, key=lambda x: x[1])
        return {"items": items, "actors": [{"id": x[0], "name": x[1]} for x in actors],
                "count": len(items), "limited": len(items) == limit}


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
            async with shared_client() as client:
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
            "user_id": user["user_id"], "menu": user.get("menu"),
            "dpr_reminders": user.get("dpr_reminders", False),
            "dpr_reminder_sites": user.get("dpr_reminder_sites")}


class MyPreferences(BaseModel):
    dpr_reminders: bool


@app.patch("/api/v1/me/preferences")
async def update_my_preferences(body: MyPreferences, user: dict = Depends(get_current_user)):
    async with shared_client() as client:
        r = await client.post(
            f"{REST}/rpc/set_my_dpr_reminders",
            headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
            json={"enabled": body.dpr_reminders},
        )
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not save reminder preference")
    user["dpr_reminders"] = body.dpr_reminders
    _cache_put(user["token"], user)
    return {"ok": True, "dpr_reminders": body.dpr_reminders}


# ---------------- Worker Master (Phase 4) ----------------
class WorkerCreate(BaseModel):
    worker_code: str
    name: str


class WorkerUpdate(BaseModel):
    name: str | None = None
    status: str | None = None  # active | on_leave | inactive
    fin: str | None = None     # work-permit / FIN number (for card sheets)


VALID_STATUS = {"active", "on_leave", "inactive"}


@app.get("/api/v1/workers")
async def list_workers(search: str = "", status: str = "",
                       user: dict = Depends(get_current_user)):
    params = {"select": "id,worker_code,name,status,fin,trade,updated_at", "order": "name.asc"}
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        params["status"] = f"eq.{status}"
    if search:
        s = search.replace("%", "").replace(",", "").strip()
        params["or"] = f"(name.ilike.*{s}*,worker_code.ilike.*{s}*)"
    async with shared_client() as client:
        r = await client.get(f"{REST}/workers", params=params,
                             headers=supabase_headers(user["token"]))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load workers")
        return r.json()


@app.post("/api/v1/workers", status_code=201)
async def create_worker(body: WorkerCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can add workers")
    code = body.worker_code.strip().upper()
    name = body.name.strip()
    if not code or not name:
        raise HTTPException(status_code=400, detail="Worker ID and name are required")

    async with shared_client() as client:
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
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can add workers")
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

    async with shared_client() as client:
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
    if body.fin is not None:
        changes["fin"] = body.fin.strip().upper() or None
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")

    # Rev 6: only the full-access tier (admin/GM/OM/HR) edits workers.
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can edit workers")

    changes["updated_by"] = user["user_id"]

    async with shared_client() as client:
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
    async with shared_client() as client:
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
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can add sites")
    code = body.site_code.strip().upper()
    name = body.site_name.strip().upper()   # site names print in CAPS in WhatsApp messages
    if not code or not name:
        raise HTTPException(status_code=400, detail="Site code and name are required")

    async with shared_client() as client:
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
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can edit sites")
    changes = {}
    if body.site_name is not None and body.site_name.strip():
        changes["site_name"] = body.site_name.strip().upper()
    if body.status is not None:
        if body.status not in ("active", "archived"):
            raise HTTPException(status_code=400, detail="Invalid status")
        changes["status"] = body.status
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")

    async with shared_client() as client:
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
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    params = {"select": "id,name,role,status,menu,dpr_reminders,dpr_reminder_sites", "order": "name.asc"}
    if role:
        params["role"] = f"eq.{role}"
    async with shared_client() as client:
        r = await client.get(f"{REST}/users", params=params,
                             headers=supabase_headers(user["token"]))
        if r.status_code != 200:   # tolerate the 'menu' column not existing yet
            params["select"] = "id,name,role,status"
            r = await client.get(f"{REST}/users", params=params,
                                 headers=supabase_headers(user["token"]))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load users")
        return r.json()


# ---------------- User administration (admin only) ----------------
ROLES = ALL_ROLES


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str


class UserStatus(BaseModel):
    status: str | None = None       # "active" | "inactive"
    role: str | None = None         # change the user's role
    menu: list[str] | None = None   # per-user menu allow-list; null = role default
    dpr_reminders: bool | None = None
    dpr_reminder_sites: list[str] | None = None  # null = all accessible sites


class PwReset(BaseModel):
    password: str


@app.post("/api/v1/users", status_code=201)
async def create_user(body: UserCreate, user: dict = Depends(get_current_user)):
    """Create a login (Supabase Auth) + a VMMS profile row. Full-access tier only."""
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can add users")
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if len(body.password or "") < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters")
    require_service()
    async with shared_client() as client:
        # 1) create the auth login (email pre-confirmed so they can log in right away)
        a = await client.post(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers=service_headers(),
            json={"email": body.email.strip().lower(), "password": body.password,
                  "email_confirm": True})
        if a.status_code not in (200, 201):
            msg = ""
            try:
                j = a.json(); msg = j.get("msg") or j.get("error_description") or j.get("error") or ""
            except Exception:
                pass
            if "already" in msg.lower() or a.status_code == 422:
                raise HTTPException(status_code=409, detail="That email already has a login")
            raise HTTPException(status_code=400, detail="Could not create login" + (f": {msg}" if msg else ""))
        auth_uid = a.json().get("id")

        # 2) create the VMMS profile row (service key → bypass RLS reliably)
        i = await client.post(
            f"{REST}/users",
            headers={**service_headers(), "Prefer": "return=representation"},
            json={"auth_uid": auth_uid, "name": body.name.strip(),
                  "role": body.role, "status": "active"})
        if i.status_code not in (200, 201):
            raise HTTPException(status_code=500,
                                detail="Login created but profile could not be saved — check with the developer")
        await audit(client, user, "create_user", "user", auth_uid or body.email, None,
                    {"name": body.name, "role": body.role})
        return {"ok": True}


@app.patch("/api/v1/users/{user_id}")
async def update_user(user_id: str, body: UserStatus, user: dict = Depends(get_current_user)):
    """Change a user's status (active/inactive), role, and/or menu allow-list.
    Full-access tier only. Send only the field(s) you want to change; for `menu`,
    a list restricts the visible sections, and null resets it to the role default."""
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can change users")

    fields = body.model_fields_set
    updates: dict = {}

    if "status" in fields:
        if body.status not in ("active", "inactive"):
            raise HTTPException(status_code=400, detail="Invalid status")
        if user_id == user["user_id"] and body.status == "inactive":
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
        updates["status"] = body.status

    if "role" in fields:
        if body.role not in ROLES:
            raise HTTPException(status_code=400, detail="Invalid role")
        if user_id == user["user_id"]:
            raise HTTPException(status_code=400, detail="You cannot change your own role")
        updates["role"] = body.role

    if "menu" in fields:
        updates["menu"] = body.menu     # only sent once the section chooser is enabled

    if "dpr_reminders" in fields:
        updates["dpr_reminders"] = bool(body.dpr_reminders)
    if "dpr_reminder_sites" in fields:
        updates["dpr_reminder_sites"] = body.dpr_reminder_sites

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    async with shared_client() as client:
        r = await client.patch(
            f"{REST}/users", params={"id": f"eq.{user_id}"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
            json=updates)
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not update the user")
        await audit(client, user, "update_user", "user", user_id, None, updates)
        _cache_invalidate_users([user_id])
        return {"ok": True, **updates}


@app.post("/api/v1/users/{user_id}/reset_password")
async def reset_password(user_id: str, body: PwReset, user: dict = Depends(get_current_user)):
    """Set a new password for a user's login. Admin only."""
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can reset passwords")
    if len(body.password or "") < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters")
    require_service()
    async with shared_client() as client:
        r = await client.get(f"{REST}/users",
                             params={"id": f"eq.{user_id}", "select": "auth_uid,name"},
                             headers=supabase_headers(user["token"]))
        rows = r.json() if r.status_code == 200 else []
        if not rows or not rows[0].get("auth_uid"):
            raise HTTPException(status_code=404, detail="That user has no linked login")
        auth_uid = rows[0]["auth_uid"]
        u = await client.put(
            f"{SUPABASE_URL}/auth/v1/admin/users/{auth_uid}",
            headers=service_headers(), json={"password": body.password})
        if u.status_code not in (200, 201):
            raise HTTPException(status_code=400, detail="Could not reset the password")
        await audit(client, user, "reset_password", "user", user_id, None, None)
        _cache_invalidate_users([user_id])
        return {"ok": True}


@app.put("/api/v1/sites/{site_id}/supervisors")
async def assign_supervisors(site_id: str, body: SupervisorAssign,
                             user: dict = Depends(get_current_user)):
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can assign supervisors")
    async with shared_client() as client:
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
        _cache_invalidate_users(set(old_ids) | set(body.user_ids))
        return {"ok": True, "site_id": site_id, "user_ids": body.user_ids}


# ---------------- Daily Allocation (Phase 6) ----------------
class AllocationBulk(BaseModel):
    work_date: str          # YYYY-MM-DD
    site_id: str
    worker_ids: list[str]


class AllocationCopy(BaseModel):
    from_date: str
    to_date: str


class AllocationClear(BaseModel):
    work_date: str


def require_allocator(user: dict):
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only the Main Supervisor or Administrator can edit allocations")


@app.get("/api/v1/allocations")
async def list_allocations(date: str, user: dict = Depends(get_current_user)):
    async with shared_client() as client:
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

    async with shared_client() as client:
        # everything already allocated on this date (all sites)
        r = await client.get(
            f"{REST}/allocations",
            params={"work_date": f"eq.{body.work_date}", "status": "eq.allocated",
                    "select": "id,site_id,worker_id,sites(site_name),"
                              "workers(name),attendance(id)"},
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

        # DATA-INTEGRITY GUARD: never delete an allocation that already has an
        # attendance record. attendance.allocation_id is ON DELETE CASCADE, so
        # removing such a worker would silently wipe his marked hours for that day.
        # (Normal same-day / next-day editing has no attendance yet, so it is
        #  unaffected — this only protects days already worked.)
        has_att = {a["id"]: bool(a.get("attendance"))
                   for a in existing}
        name_by_alloc = {a["id"]: (a.get("workers") or {}).get("name", "?")
                         for a in existing}
        blocked = [name_by_alloc[aid] for aid in to_remove if has_att.get(aid)]
        if blocked:
            raise HTTPException(
                status_code=409,
                detail=("Attendance is already recorded for that day, so these worker(s) "
                        "cannot be removed here: " + ", ".join(sorted(blocked)) +
                        ". Correct their record in Attendance instead."))

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
    if body.from_date >= body.to_date:
        raise HTTPException(status_code=400, detail="Copy-from date must be earlier than the target date")
    async with shared_client() as client:
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

        # who is already allocated on the target date (skip them — never double-book)
        tgt = await client.get(
            f"{REST}/allocations",
            params={"work_date": f"eq.{body.to_date}", "status": "eq.allocated",
                    "select": "worker_id"},
            headers=supabase_headers(user["token"]),
        )
        if tgt.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not read the target day")
        already = {a["worker_id"] for a in tgt.json()}

        # copy only workers still active AND not already placed on the target date
        active_rows = [a for a in rows if (a.get("workers") or {}).get("status") == "active"]
        skipped_leave = len(rows) - len(active_rows)
        payload = [{"work_date": body.to_date, "site_id": a["site_id"],
                    "worker_id": a["worker_id"], "status": "allocated",
                    "created_by": user["user_id"], "updated_by": user["user_id"]}
                   for a in active_rows if a["worker_id"] not in already]

        copied = 0
        if payload:
            i = await client.post(
                f"{REST}/allocations",
                headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                json=payload,
            )
            if i.status_code not in (200, 201):
                raise HTTPException(status_code=500, detail="Could not copy the day")
            copied = len(payload)

        await audit(client, user, "copy_day", "allocation",
                    f"{body.from_date}->{body.to_date}", None,
                    {"copied": copied, "skipped_on_leave": skipped_leave})

        return {"ok": True, "copied": copied,
                "skipped_on_leave": skipped_leave,
                "skipped_already_allocated": len(active_rows) - len(payload)}


@app.post("/api/v1/allocations/clear")
async def clear_allocation(body: AllocationClear, user: dict = Depends(get_current_user)):
    """Clear a whole day's allocation (an 'undo' for Copy-from-yesterday, and the
    quick way to strip a light day like Sunday back to blank). Allocations that
    ALREADY have attendance are kept, so marked hours can never be wiped."""
    require_allocator(user)
    async with shared_client() as client:
        r = await client.get(
            f"{REST}/allocations",
            params={"work_date": f"eq.{body.work_date}", "status": "eq.allocated",
                    "select": "id,attendance(id)"},
            headers=supabase_headers(user["token"]),
        )
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not read the day")
        rows = r.json()
        removable = [a["id"] for a in rows if not a.get("attendance")]
        kept = len(rows) - len(removable)
        if removable:
            d = await client.delete(
                f"{REST}/allocations",
                params={"id": f"in.({','.join(removable)})"},
                headers=supabase_headers(user["token"]),
            )
            if d.status_code not in (200, 204):
                raise HTTPException(status_code=500, detail="Could not clear the day")
        await audit(client, user, "clear_day", "allocation", body.work_date, None,
                    {"cleared": len(removable), "kept": kept})
        return {"ok": True, "cleared": len(removable), "kept": kept}


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
    async with shared_client() as client:
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
    async with shared_client() as client:
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
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(status_code=403, detail="You cannot submit manpower requests")
    requested = set(body.worker_ids)

    async with shared_client() as client:
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
    shift_type: str | None = None      # day | night | custom
    partial_leave_type: str | None = None  # mc | al | ul, while present=true
    leave_portion: str | None = None   # first_half | second_half
    edit_reason: str | None = None


class AttendanceBatchIn(BaseModel):
    changes: list[AttendanceMark]


class BulkEnd(BaseModel):
    work_date: str
    site_id: str
    end_time: str
    allocation_ids: list[str] | None = None   # if set, only these present workers get the time
    end_next_day: bool | None = False         # overnight finish (e.g. group finishing 03:30)


class SubmitDay(BaseModel):
    work_date: str
    site_id: str
    stage: str | None = "evening"   # "morning" (attendance verified) | "evening" (end times, final)


async def _load_day(client, token, work_date: str, site_id: str | None):
    params = {"work_date": f"eq.{work_date}", "status": "eq.allocated",
              "select": "id,site_id,worker_id,sites(site_name),workers(name,worker_code),"
                        "attendance(id,present,start_time,end_time,end_next_day,"
                        "normal_hours,ot_hours,day_type,submitted_at,absence_type,"
                        "shift_type,partial_leave_type,leave_portion,leave_value)"}
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
    async with shared_client() as client:
        rows = await _load_day(client, user["token"], date, site_id or None)
        out = []
        for a in rows:
            att = a.get("attendance") or None
            out.append({
                "allocation_id": a["id"], "site_id": a["site_id"],
                "site_name": (a.get("sites") or {}).get("site_name", "?"),
                "worker_name": (a.get("workers") or {}).get("name", "?"),
                "worker_code": (a.get("workers") or {}).get("worker_code", ""),
                # No default tick (site request): a worker is "marked" only once the
                # supervisor has verified him. Unmarked workers show unticked.
                "marked": bool(att),
                "present": att["present"] if att else False,
                "start_time": (att["start_time"][:5] if att and att["start_time"] else "08:00"),
                "end_time": (att["end_time"][:5] if att and att["end_time"] else None),
                "end_next_day": att["end_next_day"] if att else False,
                "normal_hours": float(att["normal_hours"]) if att else 0,
                "ot_hours": float(att["ot_hours"]) if att else 0,
                "submitted": bool(att and att["submitted_at"]),
                "absence_type": (att.get("absence_type") if att else None) or "absent",
                "shift_type": (att.get("shift_type") if att else None) or "day",
                "partial_leave_type": att.get("partial_leave_type") if att else None,
                "leave_portion": att.get("leave_portion") if att else None,
                "leave_value": float(att.get("leave_value") or 0) if att else 0,
            })
        return sorted(out, key=lambda x: (x["site_name"], x["worker_name"]))


@app.patch("/api/v1/attendance/mark")
async def mark_attendance(body: AttendanceMark, user: dict = Depends(get_current_user)):
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    safe_shift_start = ((body.shift_type == "night" and body.start_time == "20:00") or
                        (body.shift_type == "day" and body.start_time == "08:00"))
    if body.start_time and user["role"] in SUPERVISOR_ROLES and not safe_shift_start:
        raise HTTPException(status_code=403, detail="Start time can only be changed by the Main Supervisor or Administrator")

    async with shared_client() as client:
        # the allocation (RLS scopes site_sup to own sites automatically)
        ra = await client.get(
            f"{REST}/allocations",
            params={"id": f"eq.{body.allocation_id}",
                    "select": "id,work_date,site_id,worker_id,attendance(id,present,start_time,end_time,end_next_day,submitted_at,absence_type,shift_type,partial_leave_type,leave_portion,leave_value)"},
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
        fields_set = getattr(body, "model_fields_set", getattr(body, "__fields_set__", set()))
        shift_type = (body.shift_type if "shift_type" in fields_set else
                      ((att or {}).get("shift_type") or "day"))
        partial_leave = (body.partial_leave_type if "partial_leave_type" in fields_set else
                         (att or {}).get("partial_leave_type"))
        leave_portion = (body.leave_portion if "leave_portion" in fields_set else
                         (att or {}).get("leave_portion"))
        partial_leave = partial_leave or None
        leave_portion = leave_portion or None

        # "Class" = paid training day. The worker is not on site but the company
        # pays 08:00–17:00 (a normal 8-hour day). Stored as a present, paid day and
        # tagged 'class' so reports can show it distinctly.
        if body.absence_type == "class":
            present, start, end, end_nd = True, "08:00", "17:00", False
            shift_type, partial_leave, leave_portion = "day", None, None

        if shift_type not in ("day", "night", "custom"):
            raise HTTPException(status_code=400, detail="Invalid shift type")
        if partial_leave not in (None, "mc", "al", "ul"):
            raise HTTPException(status_code=400, detail="Invalid partial leave type")
        if leave_portion not in (None, "first_half", "second_half"):
            raise HTTPException(status_code=400, detail="Invalid leave portion")
        if partial_leave and (not present or not leave_portion):
            raise HTTPException(status_code=400, detail="Partial leave requires a present worker and a half-day period")
        if not present:
            partial_leave, leave_portion, shift_type = None, None, "day"
        if shift_type == "night" and end and _to_min(end) <= _to_min(start):
            end_nd = True

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

        if body.absence_type and body.absence_type not in ("absent", "mc", "ul", "al", "nw", "class"):
            raise HTTPException(status_code=400, detail="Invalid absence type")
        absence = "class" if body.absence_type == "class" else (
            None if present else (body.absence_type or (att.get("absence_type") if att else None) or "absent"))
        leave_value = 0.5 if present and partial_leave else (1.0 if not present and absence in ("mc", "al", "ul") else 0.0)

        payload = {"present": present, "start_time": start, "end_time": end,
                   "end_next_day": end_nd, "normal_hours": normal, "ot_hours": ot,
                   "day_type": day_type, "absence_type": absence,
                   "shift_type": shift_type, "partial_leave_type": partial_leave,
                   "leave_portion": leave_portion, "leave_value": leave_value,
                   "edit_reason": body.edit_reason}
        # The allocation was already authorised through the user's RLS-scoped
        # read above. Use the server-only key for the actual write so an outdated
        # attendance UPDATE policy cannot silently discard a supervisor's save.
        write_headers = service_headers() if SUPABASE_SERVICE_KEY else supabase_headers(user["token"])
        if att:
            ru = await client.patch(
                f"{REST}/attendance", params={"id": f"eq.{att['id']}"},
                headers={**write_headers, "Prefer": "return=representation"},
                json=payload)
        else:
            ru = await client.post(
                f"{REST}/attendance",
                headers={**write_headers, "Prefer": "return=representation"},
                json={**payload, "allocation_id": body.allocation_id})
        if ru.status_code not in (200, 201):
            raise HTTPException(status_code=500,
                detail=f"Could not save attendance (db {ru.status_code}: {ru.text[:160]})")
        if not ru.json():
            raise HTTPException(status_code=500,
                detail="Attendance not saved — the update matched no row (permission / RLS, or the day changed). Reload the day and try again.")

        # split-day: if this worker worked at more than one site today,
        # recalculate the whole day so the 8-hour normal quota is applied once
        try:
            # This is only a secondary split-site adjustment. Never let a slow
            # RLS query hold the phone's save response until the mobile network
            # gives up; the attendance row above is already safely committed.
            res = await asyncio.wait_for(
                recompute_worker_day(client, user["token"],
                                     alloc["work_date"], alloc["worker_id"], day_type),
                timeout=1.5)
            if res:
                normal, ot = res.get(body.allocation_id, (normal, ot))
        except Exception:
            # The individual attendance row is already saved. A secondary
            # split-day recalculation must never turn that success into a false
            # "Failed to fetch" message on the supervisor's phone.
            pass

        try:
            await asyncio.wait_for(
                audit(client, user, "mark_attendance", "attendance", body.allocation_id,
                      {k: att.get(k) for k in ("present", "end_time")} if att else None,
                      {"present": present, "end_time": end, "normal": normal, "ot": ot,
                       "shift_type": shift_type, "partial_leave_type": partial_leave,
                       "leave_portion": leave_portion, "leave_value": leave_value}),
                timeout=1.0)
        except Exception:
            pass

        return {"ok": True, "normal_hours": normal, "ot_hours": ot, "day_type": day_type}


@app.post("/api/v1/attendance/batch")
async def attendance_batch(body: AttendanceBatchIn, user: dict = Depends(get_current_user)):
    """Save a small mobile tap burst through one browser request.

    Each row still passes the existing authorization, locking, hours and audit
    rules in mark_attendance; the speed gain is removal of repeated phone↔Render
    network round trips. A failed row is returned without losing successful rows.
    """
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    if not body.changes or len(body.changes) > 100:
        raise HTTPException(status_code=400, detail="Send between 1 and 100 attendance changes")
    results = []
    for change in body.changes:
        try:
            saved = await mark_attendance(change, user)
            results.append({"allocation_id": change.allocation_id, "ok": True, **saved})
        except HTTPException as exc:
            results.append({"allocation_id": change.allocation_id, "ok": False,
                            "detail": str(exc.detail), "status": exc.status_code})
    return {"ok": all(x["ok"] for x in results), "results": results}


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
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        rows = await _load_day(client, user["token"], body.work_date, body.site_id)
        if not rows:
            raise HTTPException(status_code=404, detail="No allocation for that site/date (or not your site)")
        if user["role"] != "admin" and await month_locked(client, user["token"], body.work_date):
            raise HTTPException(status_code=403, detail="Month closed by payroll — administrator only")
        day_type = await get_day_type(client, user["token"], body.work_date)
        # When allocation_ids is given, only those workers get the time (group
        # apply); otherwise every present worker at the site does (whole-site).
        sel = set(body.allocation_ids) if body.allocation_ids is not None else None
        end_nd = bool(body.end_next_day)
        attempted = 0
        updated = 0
        failed: list[str] = []
        write_headers = service_headers() if SUPABASE_SERVICE_KEY else supabase_headers(user["token"])
        saves: list[tuple[str, object]] = []

        async def save_end_time(a: dict, att: dict, payload: dict):
            return a["id"], await client.patch(
                f"{REST}/attendance", params={"id": f"eq.{att['id']}"},
                headers={**write_headers, "Prefer": "return=representation"},
                json=payload)

        for a in rows:
            att = a.get("attendance")
            # only workers already verified present get a bulk end time
            # (no default tick — unmarked and absent workers are skipped)
            if not att:
                continue
            if sel is not None and a["id"] not in sel:
                continue
            if att["submitted_at"]:
                continue
            if not att["present"]:
                continue
            attempted += 1
            start = att["start_time"][:5] if att and att["start_time"] else "08:00"
            normal, ot = compute_hours(day_type, start, body.end_time, end_nd)
            payload = {"present": True, "start_time": start, "end_time": body.end_time,
                       "end_next_day": end_nd, "normal_hours": normal, "ot_hours": ot,
                       "day_type": day_type}
            # Run independent worker saves concurrently. The former sequential
            # loop made a 20–40 worker site exceed mobile network timeouts even
            # though Supabase eventually committed every row.
            saves.append((a["id"], save_end_time(a, att, payload)))

        results = await asyncio.gather(*(job for _, job in saves), return_exceptions=True)
        for (allocation_id, _), result in zip(saves, results):
            if isinstance(result, Exception):
                failed.append(allocation_id)
                continue
            _, ru = result
            # A PostgREST PATCH can return success with zero affected rows when
            # RLS rejects the row. Verify the returned representation.
            saved = ru.status_code in (200, 201) and bool(ru.json())
            if saved:
                updated += 1
            else:
                failed.append(allocation_id)
        try:
            await audit(client, user, "bulk_end", "attendance",
                        f"{body.work_date}:{body.site_id}", None,
                        {"end_time": body.end_time, "attempted": attempted,
                         "workers": updated, "failed": len(failed)})
        except Exception:
            pass
        if attempted and not updated:
            raise HTTPException(status_code=409,
                detail="The end times were not confirmed by the database. They remain pending on this phone; retry after checking the connection.")
        return {"ok": not failed, "attempted": attempted, "updated": updated,
                "failed": len(failed), "failed_allocation_ids": failed}


@app.post("/api/v1/attendance/present_all")
async def present_all(body: SubmitDay, user: dict = Depends(get_current_user)):
    """Quick helper: mark every not-yet-marked worker as Present (no end time).
    The supervisor then unticks the few who are absent. Default is still unticked."""
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        rows = await _load_day(client, user["token"], body.work_date, body.site_id)
        if not rows:
            raise HTTPException(status_code=404, detail="No allocation for that site/date (or not your site)")
        if user["role"] != "admin" and await month_locked(client, user["token"], body.work_date):
            raise HTTPException(status_code=403, detail="Month closed by payroll — administrator only")
        day_type = await get_day_type(client, user["token"], body.work_date)
        added = 0
        for a in rows:
            if a.get("attendance"):
                continue   # already marked (present or absent) — leave it
            await client.post(
                f"{REST}/attendance",
                headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                json={"allocation_id": a["id"], "present": True, "start_time": "08:00",
                      "end_time": None, "end_next_day": False, "normal_hours": 0, "ot_hours": 0,
                      "day_type": day_type, "absence_type": None})
            added += 1
        await audit(client, user, "present_all", "attendance",
                    f"{body.work_date}:{body.site_id}", None, {"marked_present": added})
        return {"ok": True, "marked_present": added}


@app.post("/api/v1/attendance/submit")
async def submit_day(body: SubmitDay, user: dict = Depends(get_current_user)):
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(status_code=403, detail="Only a Supervisor or the Administrator can submit")
    async with shared_client() as client:
        rows = await _load_day(client, user["token"], body.work_date, body.site_id)
        if not rows:
            raise HTTPException(status_code=404, detail="No allocation for that site/date (or not your site)")
        if user["role"] != "admin" and await month_locked(client, user["token"], body.work_date):
            raise HTTPException(status_code=403, detail="Month closed by payroll — administrator only")

        # MORNING stage (toolbox meeting): everyone must be verified — present, or
        # marked absent / MC. No end times needed yet. Nothing is locked.
        if (body.stage or "evening") == "morning":
            unmarked = [(a.get("workers") or {}).get("name", "?")
                        for a in rows if not a.get("attendance")]
            if unmarked:
                raise HTTPException(status_code=400,
                    detail="Not yet verified: " + ", ".join(unmarked[:5]) +
                           (f" (+{len(unmarked)-5} more)" if len(unmarked) > 5 else "") +
                           ". Tick who is present, and mark the rest Absent or MC.")
            present = sum(1 for a in rows if a["attendance"]["present"])
            await audit(client, user, "submit_morning", "attendance",
                        f"{body.work_date}:{body.site_id}", None,
                        {"present": present, "total": len(rows)})
            return {"ok": True, "stage": "morning", "present": present, "total": len(rows)}

        # EVENING stage (final): present workers need an end time; then lock the day.
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
        # Authorization was already established by the user's RLS-scoped read
        # above. Use the server-only key for the final lock, just as individual
        # end-time saves do, and verify every row was actually updated.
        write_headers = service_headers() if SUPABASE_SERVICE_KEY else supabase_headers(user["token"])
        r = await client.patch(
            f"{REST}/attendance",
            params={"id": f"in.({','.join(att_ids)})"},
            headers={**write_headers, "Prefer": "return=representation"},
            json={"submitted_at": "now()", "submitted_by": user["user_id"]},
        )
        saved_rows = r.json() if r.status_code in (200, 201) else []
        if len(saved_rows) != len(att_ids):
            raise HTTPException(status_code=500,
                                detail="End times were saved, but final submission was not confirmed. Please tap Submit End Times again.")
        await audit(client, user, "submit_day", "attendance",
                    f"{body.work_date}:{body.site_id}", None, {"workers": len(att_ids)})
        return {"ok": True, "stage": "evening", "submitted": len(att_ids)}


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
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
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
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
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


def tc(name: str) -> str:
    """Worker names print in Title Case in the WhatsApp messages, not ALL CAPS
    (HR request 25/07/2026). Worker codes and site names stay in caps."""
    return (name or "").strip().title()


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
            lines.append(f"{i}. {x}")
    if home_leave:
        lines.append(DIVIDER)
        lines.append("*HOME LEAVE*")
        for i, x in enumerate(home_leave, 1):
            lines.append(f"{i}. {x}")
    return "\n".join(lines)


ABSENCE_LABEL = {"mc": "MC", "ul": "UL", "al": "AL",
                 "half_mc": "½ DAY MC", "half_ul": "½ DAY UL", "half_al": "½ DAY AL"}


def _leave_lines(leave: list[dict]) -> list[str]:
    """A '*ON LEAVE*' block listing MC / UL / AL workers, or [] if none."""
    if not leave:
        return []
    out = ["", "*ON LEAVE*"]
    for i, r in enumerate(sorted(leave, key=lambda x: x["name"]), 1):
        out.append(f'{i}.{r["code"]}_{tc(r["name"])}_{ABSENCE_LABEL.get(r["type"], r["type"].upper())}')
    return out


def format_update_message(work_date: str, site_name: str, supervisor: str,
                          rows: list[dict], leave: list[dict] | None = None) -> str:
    """Spec §7.2: WORKERID_NAME_ENDTIME, plus an ON LEAVE block for MC/UL/AL."""
    d = date_cls.fromisoformat(work_date)
    lines = [f"*SITE: {site_name.upper()}*",
             f"*DATE: {d.day:02d}/{d.month:02d}/{d.year}*",
             f"*REPORTED BY: {supervisor.upper()}*",
             ""]
    n = 0
    for r in rows:
        n += 1
        t = r["end_time"]
        if r.get("start_time") and r["start_time"] != "08:00":
            t = f'{r["start_time"]}-{r["end_time"]}'
        lines.append(f'{n}.{r["code"]}_{tc(r["name"])}_{t}')
    lines += _leave_lines(leave)
    return "\n".join(lines)


@app.get("/api/v1/messages/allocation")
async def allocation_message(date: str, user: dict = Depends(get_current_user)):
    if user["role"] not in COORDINATOR_ROLES:
        raise HTTPException(status_code=403, detail="Only the Main Supervisor or Administrator can generate this message")
    async with shared_client() as client:
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
        leave = [f'{w["worker_code"]}_{tc(w["name"])}'
                 for w in (rw.json() if rw.status_code == 200 else [])]

        by_site: dict[str, list[str]] = {}
        for a in allocs:
            sname = (a.get("sites") or {}).get("site_name", "?")
            w = a.get("workers") or {}
            by_site.setdefault(sname, []).append(
                f'{w.get("worker_code", "?")}_{tc(w.get("name", "?"))}')
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
    async with shared_client() as client:
        rows = await _load_day(client, user["token"], date, site_id)
        if not rows:
            raise HTTPException(status_code=404, detail="No allocation for that site/date (or not your site)")
        site_name = (rows[0].get("sites") or {}).get("site_name", "?")

        present, leave, missing = [], [], 0
        for a in rows:
            att = a.get("attendance")
            if not att:
                continue
            w = a.get("workers") or {}
            if not att["present"]:
                if att.get("absence_type") in ("mc", "ul", "al"):
                    leave.append({"name": w.get("name", "?"), "code": w.get("worker_code", "?"),
                                  "type": att["absence_type"]})
                continue
            if att.get("partial_leave_type") in ("mc", "ul", "al"):
                leave.append({"name": w.get("name", "?"), "code": w.get("worker_code", "?"),
                              "type": "half_" + att["partial_leave_type"]})
            if not att["end_time"]:
                missing += 1
                continue
            present.append({"name": w.get("name", "?"), "code": w.get("worker_code", "?"),
                            "start_time": att["start_time"][:5] if att["start_time"] else "08:00",
                            "end_time": att["end_time"][:5]})
        present.sort(key=lambda x: x["name"])

        msg = format_update_message(date, site_name, user["name"], present, leave)
        await audit(client, user, "generate_update_msg", "message",
                    f"{date}:{site_id}", None, {"workers": len(present)})
        return {"message": msg, "workers": len(present), "missing_end_time": missing}


@app.get("/api/v1/messages/update_all")
async def update_all_message(date: str, user: dict = Depends(get_current_user)):
    """One combined end-time message for ALL sites (co-ordinator posts once)."""
    if user["role"] not in COORDINATOR_ROLES:
        raise HTTPException(status_code=403, detail="Only the Co-ordinator or Administrator can generate the all-sites update")
    async with shared_client() as client:
        rows = await _load_day(client, user["token"], date, None)
        by_site: dict[str, list[dict]] = {}
        leave_by_site: dict[str, list[dict]] = {}
        missing = 0
        for a in rows:
            att = a.get("attendance")
            sname = (a.get("sites") or {}).get("site_name", "?")
            w = a.get("workers") or {}
            if not att:
                continue
            if not att["present"]:
                if att.get("absence_type") in ("mc", "ul", "al"):
                    leave_by_site.setdefault(sname, []).append(
                        {"name": w.get("name", "?"), "code": w.get("worker_code", "?"),
                         "type": att["absence_type"]})
                continue
            if att.get("partial_leave_type") in ("mc", "ul", "al"):
                leave_by_site.setdefault(sname, []).append(
                    {"name": w.get("name", "?"), "code": w.get("worker_code", "?"),
                     "type": "half_" + att["partial_leave_type"]})
            if not att["end_time"]:
                missing += 1
                continue
            by_site.setdefault(sname, []).append({
                "name": w.get("name", "?"), "code": w.get("worker_code", "?"),
                "start": att["start_time"][:5] if att["start_time"] else "08:00",
                "end": att["end_time"][:5],
            })
        d = date_cls.fromisoformat(date)
        lines = ["*END TIME UPDATE*", f"*{d.day:02d}/{d.month:02d}/{d.year}*"]
        total = 0
        for sname in sorted(set(by_site) | set(leave_by_site)):
            lines.append(DIVIDER)
            lines.append(f"*{sname.upper()}*")
            for i, r in enumerate(sorted(by_site.get(sname, []), key=lambda x: x["name"]), 1):
                t = r["end"] if r["start"] == "08:00" else f'{r["start"]}-{r["end"]}'
                lines.append(f'{i}.{r["code"]}_{tc(r["name"])}_{t}')
                total += 1
            lines += _leave_lines(leave_by_site.get(sname))
        msg = "\n".join(lines)
        await audit(client, user, "generate_update_all_msg", "message", date, None, {"workers": total})
        return {"message": msg, "workers": total, "missing_end_time": missing, "sites": len(by_site)}


@app.get("/api/v1/messages/home_leave")
async def home_leave_message(user: dict = Depends(get_current_user)):
    """Message listing every worker currently on Home Leave (status on_leave)."""
    async with shared_client() as client:
        rw = await client.get(f"{REST}/workers",
                              params={"status": "eq.on_leave", "select": "name,worker_code",
                                      "order": "name.asc"},
                              headers=supabase_headers(user["token"]))
        workers = rw.json() if rw.status_code == 200 else []
        d = date_cls.fromisoformat(sgt_today())
        lines = ["*HOME LEAVE*", f"*{d.day:02d}/{d.month:02d}/{d.year}*", DIVIDER]
        for i, w in enumerate(workers, 1):
            lines.append(f'{i}.{w["worker_code"]}_{tc(w["name"])}')
        lines.append(DIVIDER)
        lines.append(f"*TOTAL ON HOME LEAVE: {len(workers)}*")
        return {"message": "\n".join(lines), "workers": len(workers)}


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
            lines.append(f"{i}. {x}")
    lines.append(DIVIDER)
    lines.append(f"*TOTAL REQUESTED: {total}*")
    return "\n".join(lines)


@app.get("/api/v1/messages/requests")
async def request_message(date: str, user: dict = Depends(get_current_user)):
    # admin/main_sup get the consolidated (all sites) message;
    # a site supervisor gets only their own site's request (RLS scopes the query).
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(status_code=403, detail="You cannot generate this message")
    async with shared_client() as client:
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
                f'{w.get("worker_code", "?")}_{tc(w.get("name", "?"))}')
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

    async with shared_client() as client:
        rw = await client.get(f"{REST}/workers",
                              params={"select": "id,status"},
                              headers=supabase_headers(user["token"]))
        workers = rw.json() if rw.status_code == 200 else []
        scoped = user["role"] in SUPERVISOR_ROLES

        rs = await client.get(f"{REST}/sites",
                              params={"select": "id,site_name,status"},
                              headers=supabase_headers(user["token"]))
        sites = rs.json() if rs.status_code == 200 else []

        # Supervisors see only their own sites (request 22/07/2026)
        if user["role"] in SUPERVISOR_ROLES:
            rl = await client.get(f"{REST}/site_supervisors",
                                  params={"user_id": f"eq.{user['user_id']}", "select": "site_id"},
                                  headers=supabase_headers(user["token"]))
            mine = {x["site_id"] for x in (rl.json() if rl.status_code == 200 else [])}
            sites = [s for s in sites if s["id"] in mine]

        # One database-side aggregation replaces thousands of allocation rows on
        # mobile.  Never silently return zeroes when the RPC is unavailable.
        ra = await client.post(
            f"{REST}/rpc/home_dashboard_agg",
            json={"p_start": month_start, "p_today": today,
                  "p_site_ids": (list(mine) if scoped else None)},
            headers=supabase_headers(user["token"]),
        )
        if ra.status_code != 200:
            raise HTTPException(status_code=503,
                                detail="Dashboard summary is temporarily unavailable. Please retry.")
        try:
            agg = ra.json()
            if not isinstance(agg, dict):
                raise ValueError("invalid dashboard aggregate")
            month_nh = float(agg.get("month_nh") or 0)
            month_ot = float(agg.get("month_ot") or 0)
            today_mc = float(agg.get("today_mc") or 0)
            today_al = float(agg.get("today_al") or 0)
            today_ul = float(agg.get("today_ul") or 0)
            site_month = {
                x["site_name"]: {"nh": float(x.get("nh") or 0),
                                 "ot": float(x.get("ot") or 0)}
                for x in (agg.get("site_month") or []) if x.get("site_name")
            }
            today_by_site = {
                x["site_name"]: {"allocated": int(x.get("allocated") or 0),
                                 "with_att": int(x.get("with_att") or 0),
                                 "submitted": int(x.get("submitted") or 0)}
                for x in (agg.get("today_by_site") or []) if x.get("site_name")
            }
            leave_by_worker = {
                x["code"]: {"name": x.get("name") or "?", "code": x["code"],
                            "mc": float(x.get("mc") or 0),
                            "al": float(x.get("al") or 0),
                            "ul": float(x.get("ul") or 0)}
                for x in (agg.get("leave_by_worker") or []) if x.get("code")
            }
        except (TypeError, ValueError, KeyError):
            raise HTTPException(status_code=503,
                                detail="Dashboard summary returned invalid data. Please retry.")

        # Split the day into MORNING (attendance marked) and EVENING (end times submitted)
        morning_pending, morning_completed = [], []
        evening_pending, evening_completed = [], []
        for sname, t in today_by_site.items():
            if t["allocated"] <= 0:
                continue
            (morning_completed if t["with_att"] >= t["allocated"] else morning_pending).append(sname)
            (evening_completed if t["submitted"] >= t["allocated"] else evening_pending).append(sname)

        # Backward-compatible fields = the evening (end-time) view
        pending, completed = evening_pending, evening_completed

        # Include inactive/historical sites that recorded hours earlier in the
        # selected month. Otherwise KPI totals include those hours while the
        # site table silently omits them, making the two totals disagree.
        site_state = {s["site_name"]: s.get("status") == "active" for s in sites}
        summary_names = list(dict.fromkeys(
            [s["site_name"] for s in sites if s.get("status") == "active"]
            + list(site_month.keys()) + list(today_by_site.keys())))
        summary = [{"site_name": name,
                    "site_active": site_state.get(name, False),
                    "today": today_by_site.get(name, {}).get("allocated", 0),
                    "month_nh": round(site_month.get(name, {}).get("nh", 0), 1),
                    "month_ot": round(site_month.get(name, {}).get("ot", 0), 1)}
                   for name in summary_names]

        # leave leaderboard — most total leave days this month (MC + AL + UL)
        leave_leaders = sorted(
            ({**v, "total": v["mc"] + v["al"] + v["ul"]} for v in leave_by_worker.values()),
            key=lambda x: (-x["total"], x["name"]))

        return {
            "date": today,
            "scoped": scoped,
            "total_workers": (sum(t["allocated"] for t in today_by_site.values())
                              if scoped else sum(1 for w in workers if w["status"] == "active")),
            "on_leave": 0 if scoped else sum(1 for w in workers if w["status"] == "on_leave"),
            "total_sites": sum(1 for s in sites if s.get("status") == "active"),
            "today_allocated": sum(t["allocated"] for t in today_by_site.values()),
            "today_mc": today_mc,
            "today_al": today_al,
            "today_ul": today_ul,
            "pending_updates": sorted(pending),
            "completed_updates": sorted(completed),
            "morning_pending": sorted(morning_pending),
            "morning_completed": sorted(morning_completed),
            "evening_pending": sorted(evening_pending),
            "evening_completed": sorted(evening_completed),
            "month_normal_hours": round(month_nh, 1),
            "month_ot_hours": round(month_ot, 1),
            "site_summary": summary,
            "leave_leaders": leave_leaders,
        }


# ---------------- Reports & Monthly Man-Hours (Phases 11–12 · spec §9) ----------------
async def month_locked(client: httpx.AsyncClient, token: str, work_date: str) -> bool:
    m = work_date[:7] + "-01"
    r = await client.get(f"{REST}/month_locks",
                         params={"month": f"eq.{m}", "select": "month"},
                         headers=supabase_headers(token))
    return r.status_code == 200 and bool(r.json())


async def _range_rows(client, token, dfrom: str, dto: str, site_id: str | None):
    # Page through all rows — PostgREST caps a single response at ~1000, which
    # would silently truncate a busy range and undercount reports/man-hours.
    base = {"work_date": f"gte.{dfrom}", "status": "eq.allocated",
            "select": "work_date,site_id,sites(site_name),"
                      "workers(name,worker_code),"
                      "attendance(present,start_time,end_time,end_next_day,normal_hours,ot_hours,day_type,submitted_at,absence_type,shift_type,partial_leave_type,leave_portion,leave_value)",
            "and": f"(work_date.lte.{dto}" + (f",site_id.eq.{site_id}" if site_id else "") + ")",
            "order": "work_date.asc,id.asc"}
    rows, off, page = [], 0, 1000
    while True:
        r = await client.get(f"{REST}/allocations",
                             params={**base, "limit": page, "offset": off},
                             headers=supabase_headers(token))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load report data")
        batch = r.json()
        rows.extend(batch)
        if len(batch) < page:
            break
        off += page
    return rows


@app.get("/api/v1/reports/attendance")
async def report_attendance(dfrom: str, dto: str, site_id: str = "",
                            user: dict = Depends(get_current_user)):
    d1, d2 = date_cls.fromisoformat(dfrom), date_cls.fromisoformat(dto)
    if d2 < d1 or (d2 - d1).days > 62:
        raise HTTPException(status_code=400, detail="Date range must be 1–62 days")
    async with shared_client() as client:
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
                "absence": ("class" if att and att.get("absence_type") == "class"
                            else ((att.get("absence_type") or "absent") if att and not att["present"] else "")),
                "partial_leave": att.get("partial_leave_type") if att and att.get("present") else "",
                "leave_portion": att.get("leave_portion") if att else "",
                "leave_value": float(att.get("leave_value") or 0) if att else 0,
                "shift_type": att.get("shift_type") or "day" if att else "",
                "end_next_day": bool(att and att.get("end_next_day")),
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
    async with shared_client() as client:
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
    async with shared_client() as client:
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
    async with shared_client() as client:
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
    async with shared_client() as client:
        r = await client.get(f"{REST}/public_holidays",
                             params={"select": "holiday_date,description", "order": "holiday_date.asc"},
                             headers=supabase_headers(user["token"]))
        return r.json() if r.status_code == 200 else []


@app.post("/api/v1/holidays", status_code=201)
async def add_holiday(body: HolidayBody, user: dict = Depends(get_current_user)):
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can edit holidays")
    async with shared_client() as client:
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
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only management can edit holidays")
    async with shared_client() as client:
        r = await client.delete(f"{REST}/public_holidays",
                                params={"holiday_date": f"eq.{holiday_date}"},
                                headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete holiday")
        await audit(client, user, "delete_holiday", "holiday", holiday_date, None, None)
        return {"ok": True}


@app.get("/api/v1/settings")
async def list_settings(user: dict = Depends(get_current_user)):
    if user["role"] not in FULL_ROLES + MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.get(f"{REST}/settings",
                             params={"select": "key,value,effective_from", "order": "key.asc"},
                             headers=supabase_headers(user["token"]))
        return r.json() if r.status_code == 200 else []


class AppearanceBody(BaseModel):
    preset: str = "executive"
    primary: str = "#B42318"
    secondary: str = "#273142"
    accent: str = "#D6A32F"
    page: str = "#F2F4F7"
    surface: str = "#FFFFFF"
    ink: str = "#182230"
    theme_bundle: dict | None = None


APPEARANCE_PRESETS = {
    "executive": {"primary": "#B42318", "secondary": "#273142", "accent": "#D6A32F", "page": "#F2F4F7", "surface": "#FFFFFF", "ink": "#182230"},
    "industrial": {"primary": "#175CD3", "secondary": "#202B3C", "accent": "#00A3A3", "page": "#EEF3F8", "surface": "#FFFFFF", "ink": "#172B4D"},
    "construction": {"primary": "#C76A00", "secondary": "#29313D", "accent": "#1E6F68", "page": "#F7F3ED", "surface": "#FFFFFF", "ink": "#252A32"},
    "vortex": "#C00000", "blue": "#1565C0", "orange": "#C2410C",
    "navy": "#1E3A5F", "emerald": "#047857", "custom": None,
}

THEME_COLOUR_KEYS = (
    "brand", "secondary", "accent", "page", "surface", "ink", "muted",
    "heading", "line", "success", "warning", "danger", "info", "sidebar",
    "sidebarInk", "thead", "theadInk", "rowAlt",
)


def _bounded_number(value, low: float, high: float, label: str) -> float:
    if isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"Invalid theme {label}")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Invalid theme {label}")
    if number < low or number > high:
        raise HTTPException(status_code=400, detail=f"Theme {label} is outside the allowed range")
    return number


def _normalise_theme_bundle(raw: dict | None) -> dict | None:
    """Allow only documented design tokens; arbitrary CSS/HTML never reaches storage."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("themes"), dict):
        raise HTTPException(status_code=400, detail="Invalid company theme configuration")
    themes_raw = raw["themes"]
    if not 1 <= len(themes_raw) <= 12:
        raise HTTPException(status_code=400, detail="Keep between 1 and 12 company themes")
    active = str(raw.get("active") or "")
    if active not in themes_raw:
        raise HTTPException(status_code=400, detail="The active company theme is missing")
    clean_themes = {}
    for name, theme in themes_raw.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._()&-]{0,39}", name):
            raise HTTPException(status_code=400, detail="Theme names may contain letters, numbers, spaces and basic punctuation")
        if not isinstance(theme, dict):
            raise HTTPException(status_code=400, detail=f"Invalid theme: {name}")
        colours, shapes = theme.get("colors"), theme.get("shapes")
        type_tokens, animation = theme.get("type"), theme.get("anim")
        if not all(isinstance(x, dict) for x in (colours, shapes, type_tokens, animation)):
            raise HTTPException(status_code=400, detail=f"Theme {name} is incomplete")
        clean_colours = {}
        for key in THEME_COLOUR_KEYS:
            value = str(colours.get(key) or "").upper()
            if not re.fullmatch(r"#[0-9A-F]{6}", value):
                raise HTTPException(status_code=400, detail=f"Theme {name} has an invalid {key} colour")
            clean_colours[key] = value
        density = str(shapes.get("density") or "")
        font = str(type_tokens.get("font") or "")
        level = str(animation.get("level") or "")
        hover = str(animation.get("hover") or "")
        press = str(animation.get("press") or "")
        if density not in {"compact", "standard", "spacious"}:
            raise HTTPException(status_code=400, detail="Invalid theme density")
        if font not in {"system", "arial", "arialnarrow", "inter", "georgia", "mono"}:
            raise HTTPException(status_code=400, detail="Invalid theme font")
        if type_tokens.get("fwH") not in {600, 700, 800} or type_tokens.get("fwBtn") not in {600, 700, 800}:
            raise HTTPException(status_code=400, detail="Invalid theme font weight")
        if level not in {"none", "subtle", "standard", "smooth"}:
            raise HTTPException(status_code=400, detail="Invalid animation level")
        if hover not in {"none", "lift", "glow"} or press not in {"none", "scale", "sink"}:
            raise HTTPException(status_code=400, detail="Invalid theme animation effect")
        clean_themes[name] = {
            "colors": clean_colours,
            "shapes": {
                "btnRadius": _bounded_number(shapes.get("btnRadius"), 0, 22, "button radius"),
                "inputRadius": _bounded_number(shapes.get("inputRadius"), 0, 22, "input radius"),
                "cardRadius": _bounded_number(shapes.get("cardRadius"), 0, 28, "card radius"),
                "modalRadius": _bounded_number(shapes.get("modalRadius"), 0, 28, "modal radius"),
                "borderW": _bounded_number(shapes.get("borderW"), 0, 3, "border width"),
                "shadow": _bounded_number(shapes.get("shadow"), 0, 1.4, "shadow"),
                "density": density,
            },
            "type": {
                "font": font,
                "fsBase": _bounded_number(type_tokens.get("fsBase"), 12, 17, "base font size"),
                "fsH": _bounded_number(type_tokens.get("fsH"), 16, 26, "heading size"),
                "fwH": int(_bounded_number(type_tokens.get("fwH"), 600, 800, "heading weight")),
                "fwBtn": int(_bounded_number(type_tokens.get("fwBtn"), 600, 800, "button weight")),
            },
            "anim": {
                "level": level,
                "tspeed": int(_bounded_number(animation.get("tspeed"), 120, 400, "transition speed")),
                "hover": hover,
                "press": press,
            },
        }
    try:
        version = max(1, min(int(raw.get("version") or 1), 1_000_000_000))
    except (TypeError, ValueError):
        version = 1
    return {"version": version, "active": active, "themes": clean_themes}


@app.get("/api/v1/appearance")
async def get_appearance(user: dict = Depends(get_current_user)):
    """Company brand is readable by every signed-in user."""
    async with shared_client() as client:
        r = await client.get(
            f"{REST}/settings",
            params={"key": "eq.ui_company_theme", "select": "value", "limit": "1"},
            headers=supabase_headers(user["token"]),
        )
        rows = r.json() if r.status_code == 200 else []
        value = rows[0].get("value") if rows else None
        if not isinstance(value, dict):
            value = {"preset": "executive", **APPEARANCE_PRESETS["executive"]}
        return value


@app.patch("/api/v1/appearance")
async def update_appearance(body: AppearanceBody,
                            user: dict = Depends(get_current_user)):
    """Only Admin changes the company brand; safety colours remain fixed."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the Administrator can change the company theme")
    bundle = _normalise_theme_bundle(body.theme_bundle)
    preset = body.preset.strip().lower()
    if preset not in APPEARANCE_PRESETS:
        raise HTTPException(status_code=400, detail="Choose an approved colour preset")
    selected = APPEARANCE_PRESETS[preset]
    if bundle:
        colours = bundle["themes"][bundle["active"]]["colors"]
        value = {"preset": "custom", "primary": colours["brand"],
                 "secondary": colours["secondary"], "accent": colours["accent"],
                 "page": colours["page"], "surface": colours["surface"],
                 "ink": colours["ink"], "theme_bundle": bundle}
    elif isinstance(selected, dict):
        value = {"preset": preset, **selected}
    else:
        primary = selected or body.primary.strip().upper()
        value = {"preset": preset, "primary": primary, "secondary": body.secondary.strip().upper(),
                 "accent": body.accent.strip().upper(), "page": body.page.strip().upper(),
                 "surface": body.surface.strip().upper(), "ink": body.ink.strip().upper()}
    if any(not re.fullmatch(r"#[0-9A-F]{6}", str(value.get(k, "")))
           for k in ("primary", "secondary", "accent", "page", "surface", "ink")):
        raise HTTPException(status_code=400, detail="Choose valid six-digit theme colours")
    async with shared_client() as client:
        r = await client.post(
            f"{REST}/settings",
            params={"on_conflict": "key"},
            headers={**supabase_headers(user["token"]),
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            json={"key": "ui_company_theme", "value": value},
        )
        if r.status_code not in (200, 201, 204):
            raise HTTPException(status_code=500, detail="Could not save the company theme")
        await audit(client, user, "update", "appearance", "company", None, value)
    return {"ok": True, **value}


# ---------------- Site "not working" (off) days ----------------
class SiteOff(BaseModel):
    site_id: str
    off_date: str
    off: bool = True


@app.get("/api/v1/site_off")
async def list_site_off(date: str, user: dict = Depends(get_current_user)):
    async with shared_client() as client:
        r = await client.get(f"{REST}/site_off_days",
                             params={"off_date": f"eq.{date}", "select": "site_id"},
                             headers=supabase_headers(user["token"]))
        return [x["site_id"] for x in (r.json() if r.status_code == 200 else [])]


@app.post("/api/v1/site_off")
async def set_site_off(body: SiteOff, user: dict = Depends(get_current_user)):
    """Mark (or clear) a site as not working on a date. Site supervisor for their
    own site, or the allocator/management for any site (enforced by RLS)."""
    async with shared_client() as client:
        if body.off:
            r = await client.post(
                f"{REST}/site_off_days",
                headers={**supabase_headers(user["token"]),
                         "Prefer": "resolution=ignore-duplicates,return=minimal"},
                json={"site_id": body.site_id, "off_date": body.off_date,
                      "created_by": user["user_id"]})
            if r.status_code not in (200, 201, 204):
                raise HTTPException(status_code=403,
                    detail="Only the site's supervisor or the allocator can mark this site off")
        else:
            d = await client.delete(
                f"{REST}/site_off_days",
                params={"site_id": f"eq.{body.site_id}", "off_date": f"eq.{body.off_date}"},
                headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"})
            if d.status_code not in (200, 204):
                raise HTTPException(status_code=403, detail="Could not update the site")
        return {"ok": True, "off": body.off}


# ================= Daily Progress Report (Daily Work Record) =================
DPR_ROLES = FULL_ROLES + MANAGER_ROLES + SUPERVISOR_ROLES   # anyone who runs a site


class DailyReport(BaseModel):
    site_id: str
    report_date: str
    project_title: str | None = None
    to_party: str | None = None
    attention: str | None = None
    location: str | None = None
    item_of_work: str | None = None
    date_job_carried: str | None = None
    description: str | None = None
    manpower: list[dict] = []
    equipment: list[dict] = []
    materials: list[dict] = []
    photos: list[dict] = []
    signature_url: str | None = None
    prepared_by_name: str | None = None
    conformed_by_party: str | None = None
    status: str | None = "submitted"
    planning_progress: list[dict] = []


def _nz_date(v):
    """Empty string → None, so Postgres date columns don't choke."""
    return v if (v and str(v).strip()) else None


@app.get("/api/v1/dpr")
async def get_dpr(date: str, site_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.get(
            f"{REST}/daily_reports",
            params={"site_id": f"eq.{site_id}", "report_date": f"eq.{date}", "select": "*"},
            headers=supabase_headers(user["token"]))
        rows = r.json() if r.status_code == 200 else []
        return rows[0] if rows else {}


@app.get("/api/v1/dpr/prefill")
async def dpr_prefill(date: str, site_id: str, user: dict = Depends(get_current_user)):
    """Manpower grouped from that day's attendance (by worker trade), plus the
    header fields from this site's most recent report so repeating fields carry over."""
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        ra = await client.get(
            f"{REST}/allocations",
            params={"work_date": f"eq.{date}", "site_id": f"eq.{site_id}",
                    "status": "eq.allocated",
                    "select": "id,workers(trade,name),"
                              "attendance(present,start_time,end_time,end_next_day,normal_hours,ot_hours)"},
            headers=supabase_headers(user["token"]))
        arows = ra.json() if ra.status_code == 200 else []

        # One row per present worker — the supervisor fills the trade/role
        # (from the worker's saved trade if any) and can add extra names (PM/CM).
        manpower = []
        for a in arows:
            att = a.get("attendance")
            if not att or not att.get("present"):
                continue
            w = a.get("workers") or {}
            st = (att.get("start_time") or "08:00")[:5]
            sh = int(st.split(":")[0])
            en = (att.get("end_time") or "")[:5]
            to = (int(en.split(":")[0]) + (24 if att.get("end_next_day") else 0)) if en else None
            total = round(float(att.get("normal_hours") or 0) + float(att.get("ot_hours") or 0), 1)
            manpower.append({"name": w.get("name", ""), "role": (w.get("trade") or ""),
                             "no": 1, "from": sh, "to": to, "total": total, "remarks": ""})
        manpower.sort(key=lambda x: (x["name"] or "").lower())

        # header carry-over from the latest report at this site
        rh = await client.get(
            f"{REST}/daily_reports",
            params={"site_id": f"eq.{site_id}", "order": "report_date.desc", "limit": "1",
                    "select": "project_title,to_party,attention,location,item_of_work,conformed_by_party"},
            headers=supabase_headers(user["token"]))
        hrows = rh.json() if rh.status_code == 200 else []
        header = hrows[0] if hrows else {}
        return {"manpower": manpower, "header": header, "present": len(manpower)}


@app.post("/api/v1/dpr")
async def save_dpr(body: DailyReport, user: dict = Depends(get_current_user)):
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    if body.planning_progress and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only the administrator can update planning progress")
    payload = {
        "site_id": body.site_id,
        "report_date": body.report_date,
        "project_title": body.project_title,
        "to_party": body.to_party,
        "attention": body.attention,
        "location": body.location,
        "item_of_work": body.item_of_work,
        "date_job_carried": _nz_date(body.date_job_carried),
        "description": body.description,
        "manpower": body.manpower or [],
        "equipment": body.equipment or [],
        "materials": body.materials or [],
        "photos": body.photos or [],
        "signature_url": body.signature_url,
        "prepared_by_name": body.prepared_by_name or user.get("name"),
        "prepared_by": user["user_id"],
        "conformed_by_party": body.conformed_by_party or "POKB JV Representative",
        "status": body.status or "submitted",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    async with shared_client() as client:
        r = await client.post(
            f"{REST}/daily_reports",
            params={"on_conflict": "site_id,report_date"},
            headers={**supabase_headers(user["token"]),
                     "Prefer": "resolution=merge-duplicates,return=representation"},
            json=payload)
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500,
                detail=f"Could not save the report (db {r.status_code}: {r.text[:160]})")
        rows = r.json()
        saved = rows[0] if rows else {"ok": True}

        if body.planning_progress:
            progress = []
            for item in body.planning_progress[:100]:
                try:
                    qty = float(item.get("quantity_completed") or 0)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail="Invalid planning progress quantity")
                if qty < 0 or not item.get("activity_id"):
                    raise HTTPException(status_code=400, detail="Invalid planning progress entry")
                progress.append({"activity_id": item["activity_id"], "quantity_completed": qty,
                                 "note": str(item.get("note") or "")[:500]})
            pr = await client.post(f"{REST}/rpc/record_planning_dpr_progress",
                headers=supabase_headers(user["token"]),
                json={"p_dpr_id": saved.get("id"), "p_entries": progress})
            if pr.status_code not in (200, 204):
                raise HTTPException(status_code=409,
                    detail="DPR saved, but planning progress was not confirmed. Reopen the DPR and retry progress.")

        return saved


def _rs_clean(v):
    if isinstance(v, float):
        return int(v) if v.is_integer() else round(v, 1)
    return v


def _rs_number(v, default=0.0):
    """Accept saved numeric text without letting one typo break a whole report."""
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return default


def _rs_pos_rank(role):
    r = (role or "").lower()
    kws = ["manager", "engineer", "supervisor", "wshc", "rescuer", "first aid",
           "confined", "lifting", "rigger", "signal", "banksman", "traffic",
           "operator", "driver", "welder", "fire", "general"]
    for i, kw in enumerate(kws):
        if kw in r:
            return i
    return 90


# Keep summary rows from splitting when the same role/material is typed differently.
_RS_ACRONYMS = {"wshc", "wshs", "csa", "res", "reo", "wah", "cs", "db", "ppe", "t"}
_RS_ROLE_ALIAS = {
    "cs supervisor": "Confined Space Supervisor",
    "confined space supervisor": "Confined Space Supervisor",
    "cs attendant": "Confined Space Attendant",
    "confined space attendant": "Confined Space Attendant",
    "cs assessor": "Confined Space Assessor",
    "confined space assessor": "Confined Space Assessor",
    "general worker": "General Worker", "gen worker": "General Worker", "worker": "General Worker",
    "site supervisor": "Site Supervisor", "site engineer": "Site Engineer",
    "project engineer": "Project Engineer", "project manager": "Project Manager",
    "construction manager": "Construction Manager", "site manager": "Site Manager",
    "wshc/csa and rescuer": "WSHC/CSA and Rescuer",
    "first aider/rescuer": "First Aider/Rescuer", "first aider": "First Aider",
    "rigger and signalman": "Rigger and Signalman", "rigger signalman": "Rigger and Signalman",
    "rigger & signalman": "Rigger and Signalman", "rigger/signalman": "Rigger and Signalman",
    "lifting supervisor": "Lifting Supervisor",
    "traffic controller": "Traffic Controller",
    "excavator operator": "Excavator Operator", "roller operator": "Roller Operator",
    "lorrycrane operator": "Lorry Crane Operator", "lorry crane operator": "Lorry Crane Operator",
    "tipper truck driver": "Tipper Truck Driver", "fire watchman": "Fire Watchman",
    "fireman": "Fire Watchman",
}


def _rs_titlecase(s):
    out = []
    for w in s.split():
        if "/" in w:
            out.append("/".join(p.upper() if p.lower() in _RS_ACRONYMS else p.capitalize()
                                for p in w.split("/")))
        elif w.lower() in _RS_ACRONYMS:
            out.append(w.upper())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def _rs_norm_role(role):
    r = " ".join((role or "").split())      # collapse internal whitespace
    if not r:
        return "-"
    key = r.lower()
    return _RS_ROLE_ALIAS.get(key) or _rs_titlecase(r)


@app.get("/api/v1/resource-summary")
async def resource_summary(site_id: str, month: str, user: dict = Depends(get_current_user)):
    """Roll a month of DPRs for one site into the 4-sheet monthly summary:
    (1) per-employee attendance hours, (2) manpower by position/day,
    (3) materials & tools/day, (4) plant & equipment/day."""
    import calendar
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        y, m = month.split("-"); y, m = int(y), int(m)
        ndays = calendar.monthrange(y, m)[1]
    except Exception:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    start = f"{y:04d}-{m:02d}-01"
    end = f"{y:04d}-{m:02d}-{ndays:02d}"
    days = list(range(1, ndays + 1))
    weekdays = ["MTWTFSS"[date_cls(y, m, d).weekday()] for d in days]

    print(f"[resource-summary] start site={site_id} month={month} role={user['role']}", flush=True)
    try:
      # Monthly reports can return wider JSON than normal app requests. Give this
      # export its own clean connection so a stale shared keep-alive socket cannot
      # leave the page permanently at Loading / Failed to fetch.
      async with httpx.AsyncClient(timeout=60.0) as client:
        # Confirm this signed-in user can see the requested site, then use the
        # server-only key for the heavy monthly roll-up. This avoids expensive
        # per-row RLS evaluation that was timing out on the free database tier.
        # Managers/admins already have organisation-wide DPR permission. Avoid an
        # additional user-RLS site lookup for them: on the free database tier that
        # lookup could stall long enough for Safari/Chrome to drop the request.
        # Supervisors still pass the normal RLS access check.
        if user["role"] not in FULL_ROLES + MANAGER_ROLES:
            access = await client.get(
                f"{REST}/sites", params={"id": f"eq.{site_id}", "select": "id"},
                headers=supabase_headers(user["token"]))
            if access.status_code != 200 or not access.json():
                raise HTTPException(status_code=403, detail="Site not available to this user")
        rollup_headers = service_headers() if SUPABASE_SERVICE_KEY else supabase_headers(user["token"])
        # Read the small report particulars separately from the three JSON arrays.
        # This avoids a PostgREST response-shaping issue seen when all wide JSON
        # columns are requested together on Render's free-tier connection.
        r = await client.get(
                f"{REST}/daily_reports",
                # Fetch through the indexed site_id column, then apply the month
                # range in Python. Combining the date range with large JSON DPR
                # columns caused PostgREST to intermittently stall on this site.
                params={"site_id": f"eq.{site_id}",
                        "select": "id,report_date,project_title,location,item_of_work",
                        "order": "report_date.asc"},
                headers=rollup_headers)
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load Resource Summary DPR data")
        reports = [x for x in r.json() if start <= (x.get("report_date") or "") <= end]
        if reports:
            by_id = {x["id"]: x for x in reports}
            ids = ",".join(by_id)
            for field in ("manpower", "equipment", "materials"):
                rf = await client.get(
                    f"{REST}/daily_reports",
                    params={"id": f"in.({ids})", "select": f"id,{field}"},
                    headers=rollup_headers)
                if rf.status_code != 200:
                    raise HTTPException(status_code=500, detail=f"Could not load Resource Summary {field}")
                for row in rf.json():
                    if row.get("id") in by_id:
                        by_id[row["id"]][field] = row.get(field) or []
        # The Resource Summary header must use the controlled Work Package
        # directory value, not the varying free-text location saved in each DPR.
        rp = await client.get(
            f"{REST}/dpr_projects",
            params={"site_id": f"eq.{site_id}",
                    "select": "location,item_of_work,title,updated_at",
                    "order": "updated_at.desc"},
            headers=rollup_headers)
        project_rows = rp.json() if rp.status_code == 200 else []

        allocation_rows, attendance_by_allocation = [], {}
        # DPR manpower is already a complete prepared resource record. Only use
        # attendance as a fallback when the whole month has no DPRs (for example
        # the completed DLP job on 08/08). This keeps normal report generation fast.
        if not reports:
            ra = await client.get(
                f"{REST}/allocations",
                params={"site_id": f"eq.{site_id}", "status": "eq.allocated",
                        "and": f"(work_date.gte.{start},work_date.lte.{end})",
                        "select": "id,work_date,worker_id,workers(name,trade)",
                        "order": "work_date.asc"},
                headers=rollup_headers)
            if ra.status_code != 200:
                raise HTTPException(status_code=500, detail="Could not load Resource Summary allocation data")
            allocation_rows = ra.json()
            ids = [x.get("id") for x in allocation_rows if x.get("id")]
            if ids:
                ratt = await client.get(
                    f"{REST}/attendance",
                    params={"allocation_id": f"in.({','.join(ids)})",
                            "select": "allocation_id,present,normal_hours,ot_hours"},
                    headers=rollup_headers)
                if ratt.status_code != 200:
                    raise HTTPException(status_code=500, detail="Could not load Resource Summary attendance")
                attendance_by_allocation = {x["allocation_id"]: x for x in ratt.json()}
      print(f"[resource-summary] source complete reports={len(reports)} allocations={len(allocation_rows)}", flush=True)
    except HTTPException:
      raise
    except Exception as exc:
      print(f"[resource-summary] source error {type(exc).__name__}: {exc}", flush=True)
      raise HTTPException(status_code=500, detail=f"Resource Summary source error: {type(exc).__name__}")

    att, mp_pos, mats, plant = {}, {}, {}, {}
    manhours = {d: 0.0 for d in days}
    header = {"project_title": "", "location": "", "item_of_work": ""}
    locations, items_of_work = [], []

    # Attendance/manpower must come from the operational records, not only from
    # prepared DPRs. This keeps the monthly resource sheet complete even if a
    # DPR was missed or was prepared later.
    attendance_workers_by_day = set()
    attendance_days = set()
    for row in allocation_rows:
        attendance_row = attendance_by_allocation.get(row.get("id"))
        if not attendance_row or not attendance_row.get("present"):
            continue
        try:
            d = int(row["work_date"].split("-")[2])
        except Exception:
            continue
        worker = row.get("workers") or {}
        name = (worker.get("name") or "").strip()
        role = _rs_norm_role(worker.get("trade"))
        hrs = float(attendance_row.get("normal_hours") or 0) + float(attendance_row.get("ot_hours") or 0)
        if name:
            a = att.setdefault(name, {"position": role, "days": {}, "total": 0.0})
            a["days"][d] = a["days"].get(d, 0.0) + hrs
            a["total"] += hrs
            if role != "-":
                a["position"] = role
            attendance_workers_by_day.add((d, name.lower()))
        p = mp_pos.setdefault(role, {"days": {}, "total": 0})
        p["days"][d] = p["days"].get(d, 0) + 1
        p["total"] += 1
        manhours[d] += hrs
        attendance_days.add(d)

    for rep in reports:
        try:
            d = int(rep["report_date"].split("-")[2])
        except Exception:
            continue
        if not header["project_title"] and rep.get("project_title"):
            header["project_title"] = rep["project_title"]
        loc = " ".join((rep.get("location") or "").split())
        item = " ".join((rep.get("item_of_work") or "").split())
        if loc and loc.lower() not in [x.lower() for x in locations]:
            locations.append(loc)
        if item and item.lower() not in [x.lower() for x in items_of_work]:
            items_of_work.append(item)
        for w in (rep.get("manpower") or []):
            name = (w.get("name") or "").strip()
            role = _rs_norm_role(w.get("role"))
            hrs = _rs_number(w.get("total"))
            no = int(_rs_number(w.get("no"), 1) or 1)
            # Operational attendance above is authoritative. Keep only DPR-only
            # entries such as PM/CM/visitors who have no worker allocation.
            if name and (d, name.lower()) in attendance_workers_by_day:
                continue
            if name:
                a = att.setdefault(name, {"position": role, "days": {}, "total": 0.0})
                a["days"][d] = a["days"].get(d, 0.0) + hrs
                a["total"] += hrs
                if role != "-":
                    a["position"] = role
            p = mp_pos.setdefault(role, {"days": {}, "total": 0})
            p["days"][d] = p["days"].get(d, 0) + no
            p["total"] += no
            manhours[d] += hrs
        for e in (rep.get("equipment") or []):
            name = " ".join((e.get("name") or "").split())
            if not name:
                continue
            no = _rs_number(e.get("no")) or 1
            key = name.lower()
            pl = plant.setdefault(key, {"name": name, "unit": "Nos", "days": {}, "total": 0.0})
            pl["days"][d] = pl["days"].get(d, 0.0) + no
            pl["total"] += no
        for mt in (rep.get("materials") or []):
            name = " ".join((mt.get("name") or "").split())
            if not name:
                continue
            unit = (mt.get("unit") or "").strip()
            qty = _rs_number(mt.get("qty"))
            key = name.lower() + "||" + unit.lower()
            mm = mats.setdefault(key, {"name": name, "unit": unit, "days": {}, "total": 0.0})
            mm["days"][d] = mm["days"].get(d, 0.0) + qty
            mm["total"] += qty

    # Prefer the matching work package. A site may have more than one historical
    # package, so match its Item of Work first and use the latest as fallback.
    wanted_items = {x.lower() for x in items_of_work}
    project = next((p for p in project_rows
                    if " ".join((p.get("item_of_work") or "").split()).lower() in wanted_items),
                   project_rows[0] if project_rows else None)
    header["location"] = ((project or {}).get("location") or " / ".join(locations)).strip()
    header["item_of_work"] = ((project or {}).get("item_of_work") or " / ".join(items_of_work)).strip()

    def daymap(dd):
        return {str(k): _rs_clean(v) for k, v in dd.items() if v}

    attendance = [{"sn": i, "name": n, "position": a["position"],
                   "days": daymap(a["days"]), "total": _rs_clean(a["total"])}
                  for i, (n, a) in enumerate(sorted(att.items(), key=lambda x: x[0].lower()), 1)]

    mp_sorted = sorted(mp_pos.items(), key=lambda x: (_rs_pos_rank(x[0]), x[0].lower()))
    manpower = [{"sn": i, "description": pos, "unit": "Nos",
                 "days": daymap(v["days"]), "total": _rs_clean(v["total"])}
                for i, (pos, v) in enumerate(mp_sorted, 1)]
    mp_daily = {str(d): _rs_clean(sum(v["days"].get(d, 0) for v in mp_pos.values()))
                for d in days if sum(v["days"].get(d, 0) for v in mp_pos.values())}
    mp_daily_total = _rs_clean(sum(v["total"] for v in mp_pos.values()))
    manhours_row = {str(d): _rs_clean(manhours[d]) for d in days if manhours[d]}
    manhours_total = _rs_clean(sum(manhours.values()))

    mats_sorted = sorted(mats.values(), key=lambda x: x["name"].lower())
    materials = [{"sn": i, "description": v["name"], "unit": v["unit"],
                  "days": daymap(v["days"]), "total": _rs_clean(v["total"])}
                 for i, v in enumerate(mats_sorted, 1)]
    mat_daily = {str(d): _rs_clean(sum(v["days"].get(d, 0) for v in mats.values()))
                 for d in days if sum(v["days"].get(d, 0) for v in mats.values())}

    plant_sorted = sorted(plant.values(), key=lambda v: v["name"].lower())
    plant_rows = [{"sn": i, "description": v["name"], "unit": v["unit"],
                   "days": daymap(v["days"]), "total": _rs_clean(v["total"])}
                  for i, v in enumerate(plant_sorted, 1)]
    plant_daily = {str(d): _rs_clean(sum(v["days"].get(d, 0) for v in plant.values()))
                   for d in days if sum(v["days"].get(d, 0) for v in plant.values())}

    return {
        "month": month, "days": days, "weekdays": weekdays,
        "month_label": f"{calendar.month_name[m].upper()} {y}",
        "header": header, "report_count": len(reports),
        "attendance_day_count": len(attendance_days),
        "has_data": bool(reports or attendance_days),
        "attendance": attendance,
        "manpower": {"rows": manpower, "daily_total": mp_daily, "total": mp_daily_total,
                     "manhours": manhours_row, "manhours_total": manhours_total},
        "materials": {"rows": materials, "daily_total": mat_daily},
        "plant": {"rows": plant_rows, "daily_total": plant_daily},
    }


@app.get("/api/v1/dpr/list")
async def dpr_list(site_id: str = "", month: str = "", user: dict = Depends(get_current_user)):
    """History of saved reports (RLS scopes supervisors to their own sites)."""
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    params = {"select": "id,site_id,report_date,project_title,item_of_work,prepared_by_name,updated_at,manpower,photos,sites(site_name)",
              "order": "report_date.desc", "limit": "300"}
    if site_id:
        params["site_id"] = f"eq.{site_id}"
    if month and len(month) == 7:
        y, m = int(month[:4]), int(month[5:7])
        start = f"{y:04d}-{m:02d}-01"
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        params["and"] = f"(report_date.gte.{start},report_date.lt.{ny:04d}-{nm:02d}-01)"
    async with shared_client() as client:
        r = await client.get(f"{REST}/daily_reports", params=params,
                             headers=supabase_headers(user["token"]))
        rows = r.json() if r.status_code == 200 else []
        return [{"id": x["id"], "site_id": x["site_id"],
                 "site_name": (x.get("sites") or {}).get("site_name", "?"),
                 "report_date": x["report_date"], "project_title": x.get("project_title"),
                 "item_of_work": x.get("item_of_work"),
                 "prepared_by_name": x.get("prepared_by_name"),
                 "manpower": len(x.get("manpower") or []),
                 "photos": len(x.get("photos") or []),
                 "updated_at": x.get("updated_at")} for x in rows]


@app.get("/api/v1/dpr/missing")
async def dpr_missing(days: int = 30, user: dict = Depends(get_current_user)):
    """Allocated site-days without a saved DPR. When enabled, keep matching
    personal Do-first tasks in sync for the signed-in user."""
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    days = max(1, min(days, 90))
    end_d = date_cls.fromisoformat(sgt_today()) - timedelta(days=1)
    # This workflow was introduced on 10/08/2026. Do not create historical
    # reminders before launch; only allocated site-days from launch onward count.
    feature_start = date_cls(2026, 8, 10)
    start_d = max(end_d - timedelta(days=days - 1), feature_start)
    start, end = start_d.isoformat(), end_d.isoformat()
    async with shared_client() as client:
        # Read this preference fresh instead of relying on the long-lived identity
        # cache. An administrator's newly selected sites must take effect at once.
        rp = await client.get(f"{REST}/users",
            params={"id": f"eq.{user['user_id']}",
                    "select": "dpr_reminders,dpr_reminder_sites"},
            headers=supabase_headers(user["token"]))
        prefs = (rp.json() or [{}])[0] if rp.status_code == 200 else {}
        enabled = bool(prefs.get("dpr_reminders", user.get("dpr_reminders", False)))
        selected_sites = prefs.get("dpr_reminder_sites", user.get("dpr_reminder_sites"))
        user["dpr_reminders"], user["dpr_reminder_sites"] = enabled, selected_sites
        _cache_put(user["token"], user)
        if not enabled:
            return {"enabled": False, "from": start, "to": end, "count": 0, "items": []}
        ra, rr, rpj, rpa = await asyncio.gather(
            client.get(f"{REST}/allocations",
                params={"status": "eq.allocated", "and": f"(work_date.gte.{start},work_date.lte.{end})",
                        "select": "work_date,site_id,sites(site_name)"},
                headers=supabase_headers(user["token"])),
            client.get(f"{REST}/daily_reports",
                params={"and": f"(report_date.gte.{start},report_date.lte.{end})",
                        "select": "report_date,site_id"},
                headers=supabase_headers(user["token"])),
            client.get(f"{REST}/dpr_projects",
                params={"select": "id,site_id,start_date,actual_completion_date,cancelled_date,lifecycle_status,reminder_enabled,responsible_user_ids"},
                headers=supabase_headers(user["token"])),
            client.get(f"{REST}/dpr_project_pauses",
                params={"select": "project_id,stop_date,resume_date"},
                headers=supabase_headers(user["token"])),
        )
        alloc = ra.json() if ra.status_code == 200 else []
        reports = rr.json() if rr.status_code == 200 else []
        lifecycle_projects = rpj.json() if rpj.status_code == 200 else []
        pause_rows = rpa.json() if rpa.status_code == 200 else []
        by_site, pauses_by_project = {}, {}
        for p in lifecycle_projects:
            if p.get("site_id"):
                by_site.setdefault(p["site_id"], []).append(p)
        for p in pause_rows:
            pauses_by_project.setdefault(p.get("project_id"), []).append(p)

        def site_requires_dpr(site_id, day):
            projects = by_site.get(site_id, [])
            # Preserve the established allocation-based rule until a Site has
            # explicitly been placed under lifecycle control in the directory.
            if not projects:
                return True
            for p in projects:
                assigned = p.get("responsible_user_ids") or []
                if assigned and user["user_id"] not in assigned:
                    continue
                if _project_working_on(p, day, pauses_by_project.get(p.get("id"), [])):
                    return True
            return False
        prepared = {(x.get("site_id"), x.get("report_date")) for x in reports}
        missing_map = {}
        for x in alloc:
            key = (x.get("site_id"), x.get("work_date"))
            if key[0] and key[1] and key not in prepared and site_requires_dpr(key[0], key[1]):
                missing_map[key] = (x.get("sites") or {}).get("site_name") or "Site"
        if isinstance(selected_sites, list):
            selected = set(selected_sites)
            missing_map = {k: v for k, v in missing_map.items() if k[0] in selected}
        missing = [{"site_id": sid, "site_name": name, "date": day,
                    "label": date_cls.fromisoformat(day).strftime("%d/%m/%Y")}
                   for (sid, day), name in sorted(missing_map.items(), key=lambda z: z[0][1], reverse=True)]

        if enabled:
            re = await client.get(f"{REST}/todos",
                params={"user_id": f"eq.{user['user_id']}",
                        "select": "id,source,source_key,done,text"}, headers=supabase_headers(user["token"]))
            all_todos = re.json() if re.status_code == 200 else []
            auto_todos = [x for x in all_todos if x.get("source") == "dpr_missing"
                          or str(x.get("text") or "").endswith("_DPR_Pending")]
            existing = {x.get("source_key"): x for x in auto_todos if x.get("source_key")}
            wanted = {f"{x['site_id']}:{x['date']}": x for x in missing}
            def reminder_text(x):
                return f"{x['site_name']}_{x['label']}_DPR_Pending"

            creates = [client.post(f"{REST}/todos",
                        headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                        json={"user_id": user["user_id"],
                              "text": reminder_text(x),
                              "quadrant": "q1", "done": False, "due_date": x["date"],
                              "source": "dpr_missing", "source_key": key})
                       for key, x in wanted.items() if key not in existing]
            if creates:
                await asyncio.gather(*creates)
            renames = [client.patch(f"{REST}/todos",
                         params={"id": f"eq.{existing[key]['id']}", "user_id": f"eq.{user['user_id']}"},
                         headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
                         json={"text": reminder_text(x), "quadrant": "q1", "due_date": x["date"]})
                       for key, x in wanted.items()
                       if key in existing and existing[key].get("text") != reminder_text(x)]
            if renames:
                await asyncio.gather(*renames)
            stale = [x["id"] for x in auto_todos
                     if x.get("source_key") not in wanted and not x.get("done")]
            if stale:
                # Delete by exact id. PostgREST `in.(uuid,...)` filters can fail
                # for a large historic list and leave unrelated site tasks behind.
                for i in range(0, len(stale), 10):
                    await asyncio.gather(*[client.delete(f"{REST}/todos",
                        params={"id": f"eq.{todo_id}",
                                "user_id": f"eq.{user['user_id']}"},
                        headers=supabase_headers(user["token"]))
                        for todo_id in stale[i:i + 10]])
    return {"enabled": enabled, "from": start, "to": end,
            "count": len(missing), "items": missing}


class CameraWorkItemIn(BaseModel):
    dpr_project_id: str
    name: str
    sort_order: int = 0
    active: bool = True


class CameraActivityIn(BaseModel):
    work_item_id: str
    name: str
    sort_order: int = 0
    active: bool = True


def _camera_manager(user: dict) -> bool:
    return user["role"] in COORDINATOR_ROLES


@app.get("/api/v1/camera/setup")
async def camera_setup(manage: bool = False, user: dict = Depends(get_current_user)):
    """Camera selectors backed by the existing DPR project directory."""
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        headers = supabase_headers(user["token"])
        rp, rw, ra = await asyncio.gather(
            client.get(f"{REST}/dpr_projects", params={"select": "id,title,site_id,location,item_of_work,lifecycle_status,reminder_enabled,sites(site_name)", "order": "title.asc"}, headers=headers),
            client.get(f"{REST}/camera_work_items", params={"select": "*", "order": "sort_order.asc,name.asc"}, headers=headers),
            client.get(f"{REST}/camera_activities", params={"select": "*", "order": "sort_order.asc,name.asc"}, headers=headers),
        )
        if rw.status_code != 200 or ra.status_code != 200:
            raise HTTPException(status_code=503, detail="Camera setup is not ready. Run the Camera V1 Stage 1 migration.")
        projects = rp.json() if rp.status_code == 200 else []
        # Office/manager roles see all. Supervisors only see sites assigned to them.
        if not _camera_manager(user):
            rs = await client.get(f"{REST}/site_supervisors", params={"select": "site_id", "user_id": f"eq.{user['user_id']}"}, headers=headers)
            allowed = {x.get("site_id") for x in (rs.json() if rs.status_code == 200 else [])}
            projects = [p for p in projects if p.get("site_id") in allowed]
        if not (manage and _camera_manager(user)):
            projects = [p for p in projects if p.get("lifecycle_status") == "active"]
        project_ids = {p.get("id") for p in projects}
        work_items = [x for x in rw.json() if x.get("dpr_project_id") in project_ids]
        if not (manage and _camera_manager(user)):
            work_items = [x for x in work_items if x.get("active", True)]
        work_ids = {x.get("id") for x in work_items}
        activities = [x for x in ra.json() if x.get("work_item_id") in work_ids]
        if not (manage and _camera_manager(user)):
            activities = [x for x in activities if x.get("active", True)]
        return {"can_manage": _camera_manager(user), "projects": projects,
                "work_items": work_items, "activities": activities}


async def _camera_write(table: str, body: dict, user: dict, row_id: str | None = None):
    if not _camera_manager(user):
        raise HTTPException(status_code=403, detail="Only managers can maintain camera lists")
    body["name"] = (body.get("name") or "").strip()
    if not body["name"]:
        raise HTTPException(status_code=400, detail="Name is required")
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    async with shared_client() as client:
        headers = {**supabase_headers(user["token"]), "Prefer": "return=representation"}
        if row_id:
            r = await client.patch(f"{REST}/{table}", params={"id": f"eq.{row_id}"}, headers=headers, json=body)
        else:
            body["created_by"] = user["user_id"]
            r = await client.post(f"{REST}/{table}", headers=headers, json=body)
        if r.status_code not in (200, 201, 204):
            detail = "Duplicate name" if r.status_code == 409 else "Could not save camera setup"
            raise HTTPException(status_code=400 if r.status_code == 409 else 500, detail=detail)
        return (r.json() or [{"ok": True}])[0]


@app.post("/api/v1/camera/work-items", status_code=201)
async def add_camera_work_item(body: CameraWorkItemIn, user: dict = Depends(get_current_user)):
    return await _camera_write("camera_work_items", body.dict(), user)


@app.patch("/api/v1/camera/work-items/{row_id}")
async def edit_camera_work_item(row_id: str, body: CameraWorkItemIn, user: dict = Depends(get_current_user)):
    return await _camera_write("camera_work_items", body.dict(), user, row_id)


@app.delete("/api/v1/camera/work-items/{row_id}")
async def delete_camera_work_item(row_id: str, user: dict = Depends(get_current_user)):
    if not _camera_manager(user): raise HTTPException(status_code=403, detail="Only managers can maintain camera lists")
    async with shared_client() as client:
        r = await client.delete(f"{REST}/camera_work_items", params={"id": f"eq.{row_id}"}, headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204): raise HTTPException(status_code=500, detail="Could not delete item")
    return {"ok": True}


@app.post("/api/v1/camera/activities", status_code=201)
async def add_camera_activity(body: CameraActivityIn, user: dict = Depends(get_current_user)):
    return await _camera_write("camera_activities", body.dict(), user)


@app.patch("/api/v1/camera/activities/{row_id}")
async def edit_camera_activity(row_id: str, body: CameraActivityIn, user: dict = Depends(get_current_user)):
    return await _camera_write("camera_activities", body.dict(), user, row_id)


@app.delete("/api/v1/camera/activities/{row_id}")
async def delete_camera_activity(row_id: str, user: dict = Depends(get_current_user)):
    if not _camera_manager(user): raise HTTPException(status_code=403, detail="Only managers can maintain camera lists")
    async with shared_client() as client:
        r = await client.delete(f"{REST}/camera_activities", params={"id": f"eq.{row_id}"}, headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204): raise HTTPException(status_code=500, detail="Could not delete activity")
    return {"ok": True}


class CameraPhotoIn(BaseModel):
    photo_id: str
    project_id: str
    item_of_work_id: str | None = None
    item_of_work_name: str
    item_of_work_source: str
    activity_id: str | None = None
    activity_name: str
    activity_source: str
    capture_source: str
    captured_at: str | None = None
    imported_at: str | None = None
    uploaded_at: str | None = None
    r2_object_key: str
    public_url: str
    file_size: int = 0
    width: int = 1600
    height: int = 1200
    input_format: str | None = None
    output_format: str = "image/jpeg"


class CameraDprLinkIn(BaseModel):
    dpr_id: str
    photo_ids: list[str]


@app.get("/api/v1/camera/photos")
async def list_camera_photos(project_id: str | None = None, photo_date: str | None = None,
                             mine: bool = True, user: dict = Depends(get_current_user)):
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        headers = supabase_headers(user["token"])
        params = {"select": "*,dpr_projects(title,site_id,sites(site_name))", "order": "captured_at.desc.nullslast,created_at.desc", "limit": "500"}
        if project_id: params["project_id"] = f"eq.{project_id}"
        if mine or not _camera_manager(user): params["uploaded_by"] = f"eq.{user['user_id']}"
        if photo_date:
            try: next_day = (date_cls.fromisoformat(photo_date) + timedelta(days=1)).isoformat()
            except ValueError: raise HTTPException(status_code=400, detail="Invalid photo date")
            params["and"] = f"(captured_at.gte.{photo_date}T00:00:00+08:00,captured_at.lt.{next_day}T00:00:00+08:00)"
        r = await client.get(f"{REST}/camera_photos", params=params, headers=headers)
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load Camera photos")
        photos = r.json()
        if not _camera_manager(user):
            rs = await client.get(f"{REST}/site_supervisors", params={"select": "site_id", "user_id": f"eq.{user['user_id']}"}, headers=headers)
            allowed = {x.get("site_id") for x in (rs.json() if rs.status_code == 200 else [])}
            photos = [p for p in photos if (p.get("dpr_projects") or {}).get("site_id") in allowed]
        return photos


@app.post("/api/v1/camera/photos/dpr-link")
async def link_camera_photos_to_dpr(body: CameraDprLinkIn, user: dict = Depends(get_current_user)):
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    wanted = list(dict.fromkeys(body.photo_ids))[:30]
    async with shared_client() as client:
        headers = supabase_headers(user["token"])
        rd = await client.get(f"{REST}/daily_reports", params={"select": "id,site_id", "id": f"eq.{body.dpr_id}", "limit": "1"}, headers=headers)
        reports = rd.json() if rd.status_code == 200 else []
        if not reports: raise HTTPException(status_code=400, detail="Invalid DPR")
        if not _camera_manager(user):
            rs = await client.get(f"{REST}/site_supervisors", params={"select": "site_id", "user_id": f"eq.{user['user_id']}", "site_id": f"eq.{reports[0]['site_id']}", "limit": "1"}, headers=headers)
            if rs.status_code != 200 or not rs.json(): raise HTTPException(status_code=403, detail="DPR site is not assigned to this user")
        old = await client.get(f"{REST}/camera_photos", params={"select": "photo_id", "dpr_id": f"eq.{body.dpr_id}"}, headers=headers)
        old_ids = {x.get("photo_id") for x in (old.json() if old.status_code == 200 else [])}
        for pid in old_ids - set(wanted):
            await client.patch(f"{REST}/camera_photos", params={"photo_id": f"eq.{pid}"}, headers=headers,
                               json={"dpr_status": "available", "dpr_id": None, "updated_at": datetime.now(timezone.utc).isoformat()})
        for pid in wanted:
            r = await client.patch(f"{REST}/camera_photos", params={"photo_id": f"eq.{pid}"}, headers=headers,
                                   json={"dpr_status": "used", "dpr_id": body.dpr_id, "updated_at": datetime.now(timezone.utc).isoformat()})
            if r.status_code not in (200, 204): raise HTTPException(status_code=500, detail="Could not link one or more photos")
    return {"ok": True, "count": len(wanted)}


@app.post("/api/v1/camera/photos", status_code=201)
async def save_camera_photo(body: CameraPhotoIn, user: dict = Depends(get_current_user)):
    """Create one idempotent Photo Library record after the R2 PUT is confirmed."""
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    if body.capture_source not in ("camera", "gallery"):
        raise HTTPException(status_code=400, detail="Invalid capture source")
    if body.item_of_work_source not in ("directory", "manual") or body.activity_source not in ("directory", "manual"):
        raise HTTPException(status_code=400, detail="Invalid directory source")
    key = body.r2_object_key.strip("/").replace("..", "")
    if not key.startswith("site-photos/"):
        raise HTTPException(status_code=400, detail="Invalid Camera storage path")
    async with shared_client() as client:
        headers = supabase_headers(user["token"])
        existing = await client.get(f"{REST}/camera_photos", params={"select": "*", "photo_id": f"eq.{body.photo_id}", "limit": "1"}, headers=headers)
        if existing.status_code == 200 and existing.json():
            return existing.json()[0]
        rp = await client.get(f"{REST}/dpr_projects", params={"select": "id,site_id", "id": f"eq.{body.project_id}", "limit": "1"}, headers=headers)
        rows = rp.json() if rp.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=400, detail="Invalid project")
        if not _camera_manager(user):
            rs = await client.get(f"{REST}/site_supervisors", params={"select": "site_id", "user_id": f"eq.{user['user_id']}", "site_id": f"eq.{rows[0].get('site_id')}", "limit": "1"}, headers=headers)
            if rs.status_code != 200 or not rs.json():
                raise HTTPException(status_code=403, detail="Project is not assigned to this user")
        payload = body.dict()
        payload.update({"uploaded_by": user["user_id"], "r2_object_key": key,
                        "uploaded_at": body.uploaded_at or datetime.now(timezone.utc).isoformat(),
                        "sync_status": "uploaded", "dpr_status": "available"})
        r = await client.post(f"{REST}/camera_photos",
            headers={**headers, "Prefer": "return=representation"}, json=payload)
        if r.status_code not in (200, 201):
            # A repeated request racing the first insert returns the same photo.
            if r.status_code == 409:
                again = await client.get(f"{REST}/camera_photos", params={"select": "*", "photo_id": f"eq.{body.photo_id}", "limit": "1"}, headers=headers)
                if again.status_code == 200 and again.json(): return again.json()[0]
            raise HTTPException(status_code=500, detail="Photo uploaded but its library record could not be saved")
        return (r.json() or [{"photo_id": body.photo_id}])[0]


@app.delete("/api/v1/camera/photos/{photo_id}")
async def delete_camera_photo(photo_id: str, user: dict = Depends(get_current_user)):
    """Delete an authorised, unused Camera photo from R2 and the library."""
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        headers = supabase_headers(user["token"])
        r = await client.get(f"{REST}/camera_photos", params={
            "select": "photo_id,uploaded_by,r2_object_key,dpr_id,dpr_status",
            "photo_id": f"eq.{photo_id}", "limit": "1"
        }, headers=headers)
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=404, detail="Photo not found")
        photo = rows[0]
        if str(photo.get("uploaded_by")) != str(user["user_id"]) and not _camera_manager(user):
            raise HTTPException(status_code=403, detail="You can delete only your own photos")
        if photo.get("dpr_id") or photo.get("dpr_status") == "used":
            raise HTTPException(status_code=409, detail="Remove this photo from the DPR before deleting it")
        key = str(photo.get("r2_object_key") or "").strip("/").replace("..", "")
        if not key.startswith("site-photos/"):
            raise HTTPException(status_code=400, detail="Invalid Camera storage path")
        if not R2_ENABLED:
            raise HTTPException(status_code=503, detail="Photo storage is not configured")
        rr = await client.delete(_r2_presign_delete(key))
        if rr.status_code not in (200, 202, 204, 404):
            raise HTTPException(status_code=502, detail="Could not delete the photo from storage")
        delete_headers = service_headers() if SUPABASE_SERVICE_KEY else headers
        rd = await client.delete(f"{REST}/camera_photos", params={"photo_id": f"eq.{photo_id}"}, headers=delete_headers)
        if rd.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Photo was removed from storage but its library record remains")
    return {"ok": True, "photo_id": photo_id}


class ProjectIn(BaseModel):
    title: str
    to_party: str | None = None
    attention: str | None = None
    location: str | None = None
    item_of_work: str | None = None
    site_id: str | None = None


class ProjectLifecycleIn(ProjectIn):
    project_code: str | None = None
    client_contract: str | None = None
    start_date: str | None = None
    planned_completion_date: str | None = None
    actual_completion_date: str | None = None
    cancelled_date: str | None = None
    lifecycle_status: str = "draft"
    reminder_enabled: bool = True
    responsible_user_ids: list[str] | None = None
    remarks: str | None = None


class ProjectPauseIn(BaseModel):
    stop_date: str
    expected_resume_date: str | None = None
    reason: str | None = None


class ProjectResumeIn(BaseModel):
    resume_date: str


def _project_working_on(project: dict, day: str, pauses: list[dict]) -> bool:
    """Historical reminder eligibility; current status alone must not rewrite history."""
    if project.get("lifecycle_status") in ("draft", "archived"):
        return False
    if project.get("start_date") and day < project["start_date"]:
        return False
    end = project.get("actual_completion_date") or project.get("cancelled_date")
    if end and day > end:
        return False
    for pause in pauses:
        if pause.get("stop_date") and day >= pause["stop_date"] and (
                not pause.get("resume_date") or day < pause["resume_date"]):
            return False
    return bool(project.get("reminder_enabled", True))


@app.get("/api/v1/dpr/projects")
async def list_projects(user: dict = Depends(get_current_user)):
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.get(f"{REST}/dpr_projects",
                             params={"select": "*", "order": "title.asc"},
                             headers=supabase_headers(user["token"]))
        return r.json() if r.status_code == 200 else []


@app.post("/api/v1/dpr/projects", status_code=201)
async def add_project(body: ProjectIn, user: dict = Depends(get_current_user)):
    if user["role"] not in COORDINATOR_ROLES:   # office / managers maintain the directory
        raise HTTPException(status_code=403, detail="Only managers can add projects")
    async with shared_client() as client:
        r = await client.post(
            f"{REST}/dpr_projects",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json={"title": body.title, "to_party": body.to_party, "attention": body.attention,
                  "location": body.location, "item_of_work": body.item_of_work,
                  "site_id": body.site_id, "created_by": user["user_id"]})
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Could not save project ({r.status_code})")
        rows = r.json()
        return rows[0] if rows else {"ok": True}


@app.post("/api/v1/dpr/project-directory", status_code=201)
async def add_lifecycle_project(body: ProjectLifecycleIn, user: dict = Depends(get_current_user)):
    if user["role"] not in COORDINATOR_ROLES:
        raise HTTPException(status_code=403, detail="Only managers can maintain the directory")
    if not body.title.strip() or not body.site_id:
        raise HTTPException(status_code=400, detail="Project name and site are required")
    payload = body.dict()
    payload["responsible_user_ids"] = payload.get("responsible_user_ids") or []
    payload["title"] = body.title.strip()
    payload["created_by"] = user["user_id"]
    async with shared_client() as client:
        r = await client.post(f"{REST}/dpr_projects",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"}, json=payload)
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Could not create work package. Run the lifecycle migration first.")
        return (r.json() or [{"ok": True}])[0]


@app.patch("/api/v1/dpr/project-directory/{project_id}")
async def update_lifecycle_project(project_id: str, body: ProjectLifecycleIn,
                                   user: dict = Depends(get_current_user)):
    if user["role"] not in COORDINATOR_ROLES:
        raise HTTPException(status_code=403, detail="Only managers can maintain the directory")
    payload = body.dict()
    payload["responsible_user_ids"] = payload.get("responsible_user_ids") or []
    if body.lifecycle_status == "completed" and not body.actual_completion_date:
        raise HTTPException(status_code=400, detail="Actual completion date is required")
    if body.lifecycle_status == "cancelled" and not payload.get("cancelled_date"):
        payload["cancelled_date"] = sgt_today()
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    async with shared_client() as client:
        r = await client.patch(f"{REST}/dpr_projects", params={"id": f"eq.{project_id}"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"}, json=payload)
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not update work package")
        return (r.json() or [{"ok": True}])[0]


@app.get("/api/v1/dpr/project-directory")
async def lifecycle_project_directory(user: dict = Depends(get_current_user)):
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        rp, rh = await asyncio.gather(
            client.get(f"{REST}/dpr_projects", params={"select": "*,sites(site_name)", "order": "title.asc"}, headers=supabase_headers(user["token"])),
            client.get(f"{REST}/dpr_project_pauses", params={"select": "*", "order": "stop_date.desc"}, headers=supabase_headers(user["token"]))
        )
        projects = rp.json() if rp.status_code == 200 else []
        histories = rh.json() if rh.status_code == 200 else []
        for p in projects:
            p["pause_history"] = [x for x in histories if x.get("project_id") == p.get("id")]
        return projects


@app.post("/api/v1/dpr/project-directory/{project_id}/stop")
async def stop_lifecycle_project(project_id: str, body: ProjectPauseIn,
                                 user: dict = Depends(get_current_user)):
    if user["role"] not in COORDINATOR_ROLES:
        raise HTTPException(status_code=403, detail="Only managers can stop a work package")
    async with shared_client() as client:
        open_pause = await client.get(f"{REST}/dpr_project_pauses", params={"project_id": f"eq.{project_id}", "resume_date": "is.null", "select": "id"}, headers=supabase_headers(user["token"]))
        if open_pause.status_code == 200 and open_pause.json():
            raise HTTPException(status_code=409, detail="This work package is already stopped")
        r = await client.post(f"{REST}/dpr_project_pauses", headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
            json={"project_id": project_id, "stop_date": body.stop_date, "expected_resume_date": body.expected_resume_date, "reason": body.reason, "stopped_by": user["user_id"]})
        if r.status_code not in (200, 201, 204): raise HTTPException(status_code=500, detail="Could not stop work package")
        await client.patch(f"{REST}/dpr_projects", params={"id": f"eq.{project_id}"}, headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"}, json={"lifecycle_status": "temporarily_stopped", "updated_at": datetime.now(timezone.utc).isoformat()})
        return {"ok": True}


@app.post("/api/v1/dpr/project-directory/{project_id}/resume")
async def resume_lifecycle_project(project_id: str, body: ProjectResumeIn,
                                   user: dict = Depends(get_current_user)):
    if user["role"] not in COORDINATOR_ROLES:
        raise HTTPException(status_code=403, detail="Only managers can resume a work package")
    async with shared_client() as client:
        ro = await client.get(f"{REST}/dpr_project_pauses", params={"project_id": f"eq.{project_id}", "resume_date": "is.null", "select": "id,stop_date", "order": "stop_date.desc", "limit": "1"}, headers=supabase_headers(user["token"]))
        rows = ro.json() if ro.status_code == 200 else []
        if not rows: raise HTTPException(status_code=409, detail="No open stoppage was found")
        if body.resume_date < rows[0]["stop_date"]: raise HTTPException(status_code=400, detail="Resume date cannot be before stop date")
        await client.patch(f"{REST}/dpr_project_pauses", params={"id": f"eq.{rows[0]['id']}"}, headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"}, json={"resume_date": body.resume_date, "resumed_by": user["user_id"], "updated_at": datetime.now(timezone.utc).isoformat()})
        await client.patch(f"{REST}/dpr_projects", params={"id": f"eq.{project_id}"}, headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"}, json={"lifecycle_status": "active", "updated_at": datetime.now(timezone.utc).isoformat()})
        return {"ok": True}


@app.delete("/api/v1/dpr/projects/{project_id}")
async def delete_project(project_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in COORDINATOR_ROLES:   # only managers/office may delete directory entries
        raise HTTPException(status_code=403, detail="Only managers can delete a saved project")
    async with shared_client() as client:
        r = await client.delete(
            f"{REST}/dpr_projects",
            params={"id": f"eq.{project_id}"},
            headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete project")
        return {"ok": True}


# ================= Procurement (Purchase Requisition) =================
PR_ROLES = FULL_ROLES + MANAGER_ROLES + SUPERVISOR_ROLES   # who can raise a PR


class PRDirIn(BaseModel):
    site_name: str
    project_code: str
    project: str | None = None
    pm_hod: str | None = None
    manager_director: str | None = None
    deliver_to: str | None = None


@app.get("/api/v1/pr/directory")
async def pr_directory_list(user: dict = Depends(get_current_user)):
    if user["role"] not in PR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.get(f"{REST}/pr_directory",
                             params={"select": "*", "order": "site_name.asc,project_code.asc"},
                             headers=supabase_headers(user["token"]))
        return r.json() if r.status_code == 200 else []


@app.post("/api/v1/pr/directory", status_code=201)
async def pr_directory_add(body: PRDirIn, user: dict = Depends(get_current_user)):
    if user["role"] not in COORDINATOR_ROLES:
        raise HTTPException(status_code=403, detail="Only managers can edit the PR directory")
    async with shared_client() as client:
        r = await client.post(f"{REST}/pr_directory",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json={"site_name": body.site_name.strip(), "project_code": body.project_code.strip(),
                  "project": body.project, "pm_hod": body.pm_hod,
                  "manager_director": body.manager_director, "deliver_to": body.deliver_to,
                  "created_by": user["user_id"]})
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Could not save directory entry ({r.status_code})")
        rows = r.json()
        return rows[0] if rows else {"ok": True}


@app.delete("/api/v1/pr/directory/{entry_id}")
async def pr_directory_delete(entry_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in COORDINATOR_ROLES:
        raise HTTPException(status_code=403, detail="Only managers can delete a directory entry")
    async with shared_client() as client:
        r = await client.delete(f"{REST}/pr_directory",
                                params={"id": f"eq.{entry_id}"},
                                headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete entry")
        return {"ok": True}


@app.get("/api/v1/pr/next-number")
async def pr_next_number(site_name: str = "", user: dict = Depends(get_current_user)):
    """Next PR No for a given site: each site has its own running sequence.
    Revisions (e.g. ' R1') don't advance the base number. First PR for a site
    returns blank so the user types the starting number once."""
    import re as _re
    if user["role"] not in PR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    params = {"select": "pr_no,created_at", "order": "created_at.desc", "limit": "300"}
    if site_name:
        params["site_name"] = f"eq.{site_name}"
    async with shared_client() as client:
        r = await client.get(f"{REST}/purchase_requisitions", params=params,
                             headers=supabase_headers(user["token"]))
        rows = r.json() if r.status_code == 200 else []
    last = rows[0]["pr_no"] if rows and rows[0].get("pr_no") else ""
    best = None  # (prefix, num, suffix, width)
    for row in rows:
        pr = (row.get("pr_no") or "").strip()
        if not pr:
            continue
        base = _re.sub(r"\s*R\d+\s*$", "", pr, flags=_re.I).strip()   # strip revision
        m = _re.search(r"^(.*?)(\d+)(\D*)$", base)
        if not m:
            continue
        num = int(m.group(2))
        if best is None or num > best[1]:
            best = (m.group(1), num, m.group(3), len(m.group(2)))
    if best is None:
        return {"next": "", "seed": True, "last": last}
    nxt = best[0] + str(best[1] + 1).zfill(best[3]) + best[2]
    return {"next": nxt, "seed": False, "last": last}


class PRIn(BaseModel):
    pr_no: str | None = None
    pr_date: str | None = None
    category: str | None = None
    urgency: str | None = None
    delivery_mode: str | None = None
    deliver_to: str | None = None
    site_name: str | None = None
    project_code: str | None = None
    project: str | None = None
    pm_hod: str | None = None
    manager_director: str | None = None
    requested_by_name: str | None = None
    items: list[dict] = []
    photos: list[dict] = []
    remarks: str | None = None
    status: str | None = "submitted"


@app.get("/api/v1/pr/list")
async def pr_list(user: dict = Depends(get_current_user)):
    if user["role"] not in PR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.get(f"{REST}/purchase_requisitions",
            params={"select": "id,pr_no,pr_date,site_name,project_code,project,requested_by_name,category,created_at",
                    "order": "created_at.desc", "limit": "200"},
            headers=supabase_headers(user["token"]))
        return r.json() if r.status_code == 200 else []


def _pr_num(v):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0.0


@app.get("/api/v1/pr/dashboard")   # NOTE: must be defined before /api/v1/pr/{pr_id}
async def pr_dashboard(month: str = "", user: dict = Depends(get_current_user)):
    if user["role"] not in PR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    params = {"select": "id,pr_no,pr_date,category,urgency,site_name,project,requested_by_name,items,remarks,created_at",
              "order": "created_at.desc", "limit": "500"}
    if month and len(month) == 7:
        y, m = int(month[:4]), int(month[5:7])
        start = f"{y:04d}-{m:02d}-01"
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        params["and"] = f"(pr_date.gte.{start},pr_date.lt.{ny:04d}-{nm:02d}-01)"
    async with shared_client() as client:
        r = await client.get(f"{REST}/purchase_requisitions", params=params,
                             headers=supabase_headers(user["token"]))
        rows = r.json() if r.status_code == 200 else []
    total_value = 0.0
    by_cat = {"asset": 0, "consumable": 0, "rentals": 0}
    by_site, by_month, log, urgent = {}, {}, [], 0
    for p in rows:
        items = p.get("items") or []
        v = sum(_pr_num(it.get("amount")) for it in items)
        total_value += v
        c = (p.get("category") or "").lower()
        if c in by_cat:
            by_cat[c] += 1
        if (p.get("urgency") or "") == "urgent":
            urgent += 1
        s = p.get("site_name") or "—"
        bs = by_site.setdefault(s, {"site": s, "count": 0, "value": 0.0})
        bs["count"] += 1; bs["value"] += v
        mo = (p.get("pr_date") or p.get("created_at") or "")[:7]
        if mo:
            bm = by_month.setdefault(mo, {"month": mo, "count": 0, "value": 0.0})
            bm["count"] += 1; bm["value"] += v
        if len(log) < 200:
            descs = [str(it.get("description") or "").strip() for it in items if str(it.get("description") or "").strip()]
            summ = " · ".join(descs[:3]) or (p.get("remarks") or "")
            log.append({"id": p["id"], "pr_no": p.get("pr_no"), "pr_date": p.get("pr_date"),
                        "site_name": s, "project": p.get("project"), "category": p.get("category"),
                        "urgency": p.get("urgency"), "requested_by_name": p.get("requested_by_name"),
                        "value": round(v, 2), "summary": summ, "lines": descs[:8]})
    return {
        "total_count": len(rows), "total_value": round(total_value, 2), "urgent": urgent,
        "by_category": by_cat,
        "by_site": sorted(by_site.values(), key=lambda x: -x["value"]),
        "by_month": sorted(by_month.values(), key=lambda x: x["month"])[-6:],
        "log": log,
    }


@app.get("/api/v1/pr/{pr_id}")
async def pr_get(pr_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in PR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.get(f"{REST}/purchase_requisitions",
                             params={"id": f"eq.{pr_id}", "select": "*"},
                             headers=supabase_headers(user["token"]))
        rows = r.json() if r.status_code == 200 else []
        return rows[0] if rows else {}


@app.post("/api/v1/pr")
async def pr_save(body: PRIn, user: dict = Depends(get_current_user)):
    if user["role"] not in PR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    payload = {
        "pr_no": (body.pr_no or "").strip(), "pr_date": _nz_date(body.pr_date),
        "category": body.category, "urgency": body.urgency,
        "delivery_mode": body.delivery_mode, "deliver_to": body.deliver_to,
        "site_name": body.site_name, "project_code": body.project_code, "project": body.project,
        "pm_hod": body.pm_hod, "manager_director": body.manager_director,
        "requested_by_name": body.requested_by_name or user.get("name"),
        "items": body.items or [], "photos": body.photos or [], "remarks": body.remarks,
        "status": body.status or "submitted", "created_by": user["user_id"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    async with shared_client() as client:
        r = await client.post(f"{REST}/purchase_requisitions",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json=payload)
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Could not save PR (db {r.status_code}: {r.text[:140]})")
        rows = r.json()
        return rows[0] if rows else {"ok": True}


@app.patch("/api/v1/pr/{pr_id}")
async def pr_update(pr_id: str, body: PRIn, user: dict = Depends(get_current_user)):
    """Edit an existing PR in place (correct a wrongly-raised one)."""
    if user["role"] not in PR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    payload = {
        "pr_no": (body.pr_no or "").strip(), "pr_date": _nz_date(body.pr_date),
        "category": body.category, "urgency": body.urgency,
        "delivery_mode": body.delivery_mode, "deliver_to": body.deliver_to,
        "site_name": body.site_name, "project_code": body.project_code, "project": body.project,
        "pm_hod": body.pm_hod, "manager_director": body.manager_director,
        "requested_by_name": body.requested_by_name, "items": body.items or [],
        "photos": body.photos or [], "remarks": body.remarks,
        "status": body.status or "submitted",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    async with shared_client() as client:
        r = await client.patch(f"{REST}/purchase_requisitions",
            params={"id": f"eq.{pr_id}"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json=payload)
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail=f"Could not update PR ({r.status_code})")
        rows = r.json() if r.text else []
        return rows[0] if rows else {"ok": True}


@app.delete("/api/v1/pr/{pr_id}")
async def pr_delete(pr_id: str, user: dict = Depends(get_current_user)):
    """Delete a PR. Managers can delete any; others only their own."""
    if user["role"] not in PR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        chk = await client.get(f"{REST}/purchase_requisitions",
                               params={"id": f"eq.{pr_id}", "select": "created_by"},
                               headers=supabase_headers(user["token"]))
        rows = chk.json() if chk.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=404, detail="PR not found")
        if user["role"] not in COORDINATOR_ROLES and rows[0].get("created_by") != user["user_id"]:
            raise HTTPException(status_code=403, detail="You can only delete PRs you raised")
        r = await client.delete(f"{REST}/purchase_requisitions",
                                params={"id": f"eq.{pr_id}"},
                                headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete PR")
        return {"ok": True}


@app.get("/api/v1/site-progress")
async def site_progress(site_id: str = "", site_ids: str = "", days: int = 180,
                        limit: int = 500,
                        user: dict = Depends(get_current_user)):
    """Searchable Site Board built directly from saved Daily Progress Reports.

    One or more sites must be selected before DPR data is requested. Only the
    first relevant photo is projected from each DPR JSON array. This keeps the
    response small enough for weak connections and avoids the previous fetch
    failure caused by downloading every manpower and photo object. Supabase RLS
    still limits supervisors to sites they are permitted to read.
    """
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    today = sgt_today()
    days = max(7, min(730, days))
    limit = max(1, min(500, limit))
    requested = site_ids or site_id
    selected_ids = []
    for value in str(requested or "").split(","):
        value = value.strip()
        if not value:
            continue
        if not re.fullmatch(r"[A-Za-z0-9-]{8,80}", value):
            raise HTTPException(status_code=400, detail="Invalid site selection")
        if value not in selected_ids:
            selected_ids.append(value)
    selected_ids = selected_ids[:30]
    if not selected_ids:
        return {"today": today, "days": days, "site_ids": [], "summary": {},
                "trend": [], "reports": [], "partial": False}

    start = (date_cls.fromisoformat(today) - timedelta(days=days - 1)).isoformat()
    site_filter = (f"eq.{selected_ids[0]}" if len(selected_ids) == 1
                   else f"in.({','.join(selected_ids)})")
    common = {"site_id": site_filter,
              "and": f"(report_date.gte.{start},report_date.lte.{today})",
              "order": "report_date.desc", "limit": str(limit)}
    async with shared_client() as client:
        meta = await client.get(
            f"{REST}/daily_reports",
            params={**common,
                    "select": "id,site_id,report_date,location,item_of_work,description,"
                              "prepared_by_name,status,updated_at,sites(site_name)"},
            headers=supabase_headers(user["token"]),
        )
        if meta.status_code != 200:
            raise HTTPException(status_code=503,
                                detail="Daily report data is temporarily unavailable")
        rows = meta.json()

        # Photos are optional. Keep this as a separate, skinny projection so a
        # PostgREST JSON projection issue or slow photo payload can never stop
        # the textual dashboard and search results from loading.
        photos = await client.get(
            f"{REST}/daily_reports",
            params={**common, "select": "id,first_photo:photos->0"},
            headers=supabase_headers(user["token"]),
        )
        partial = photos.status_code != 200
        first_photo_by_id = ({item.get("id"): item.get("first_photo")
                              for item in photos.json()} if not partial else {})

    def relevant_photo(photo):
        if isinstance(photo, str) and photo.strip():
            return {"url": photo.strip(), "caption": ""}
        if isinstance(photo, dict):
            url = photo.get("url") or photo.get("public_url")
            if url:
                return {"url": url, "caption": photo.get("caption") or ""}
        return None

    reports, report_dates, reports_with_photos = [], {}, 0
    for row in rows:
        photo = relevant_photo(first_photo_by_id.get(row.get("id")))
        if photo:
            reports_with_photos += 1
        if row.get("report_date"):
            report_dates[row["report_date"]] = report_dates.get(row["report_date"], 0) + 1
        report = {
            "id": row.get("id"), "site_id": row.get("site_id"),
            "site_name": (row.get("sites") or {}).get("site_name") or "",
            "date": row.get("report_date"),
            "location": row.get("location") or "",
            "item_of_work": row.get("item_of_work") or "",
            "description": row.get("description") or "",
            "prepared_by": row.get("prepared_by_name") or "",
            "status": row.get("status") or "",
            "photo": photo, "updated_at": row.get("updated_at"),
        }
        reports.append(report)

    latest = reports[0] if reports else {}
    return {
        "today": today, "days": days, "site_ids": selected_ids, "partial": partial,
        "summary": {
            "reports": len(reports),
            "reported_days": len({x["date"] for x in reports if x.get("date")}),
            "latest_date": latest.get("date"),
            "selected_sites": len({x["site_id"] for x in reports if x.get("site_id")}),
            "reports_with_photos": reports_with_photos,
        },
        "trend": [{"date": day, "reports": report_dates[day]}
                  for day in sorted(report_dates.keys())[-30:]],
        "reports": reports,
    }


@app.get("/api/v1/home-overview")
async def home_overview(user: dict = Depends(get_current_user)):
    """Cross-module snapshot for the home dashboard: manpower on site, active
    sites, DPRs, open PRs, pending attendance, an activity feed and alerts."""
    today = sgt_today()
    start = (date_cls.fromisoformat(today) - timedelta(days=13)).isoformat()
    async with shared_client() as client:
        rd = await client.get(
            f"{REST}/daily_reports",
            params={"select": "report_date,site_id,manpower,sites(site_name)",
                    "and": f"(report_date.gte.{start},report_date.lte.{today})",
                    "order": "report_date.desc", "limit": "800"},
            headers=supabase_headers(user["token"]))
        reps = rd.json() if rd.status_code == 200 else []
        prs = []
        if user["role"] in PR_ROLES:
            rp = await client.get(
                f"{REST}/purchase_requisitions",
                params={"select": "pr_no,pr_date,site_name,category,created_at",
                        "order": "created_at.desc", "limit": "200"},
                headers=supabase_headers(user["token"]))
            prs = rp.json() if rp.status_code == 200 else []
        try:
            pending_att = len(await _pending_sites(client, "attendance"))
        except Exception:
            pending_att = 0

    sites, feed = {}, []
    for r in reps:
        sid = r.get("site_id"); d = r.get("report_date"); mp = len(r.get("manpower") or [])
        name = (r.get("sites") or {}).get("site_name", "?")
        if sid not in sites:
            sites[sid] = {"name": name, "latest": d, "manpower": mp}
            feed.append({"kind": "dpr", "title": "DPR · " + name,
                         "meta": f"{mp} men · {d}", "date": d})
    manpower_on_site = sum(s["manpower"] for s in sites.values())
    alerts = []
    for s in sites.values():
        try:
            ago = (date_cls.fromisoformat(today) - date_cls.fromisoformat(s["latest"])).days
        except Exception:
            ago = 0
        if ago >= 2:
            alerts.append({"level": "warn", "text": f"{s['name']} — no DPR for {ago} days"})
    if pending_att:
        alerts.append({"level": "info", "text": f"{pending_att} site(s) pending attendance today"})
    for p in prs[:4]:
        feed.append({"kind": "pr", "title": "PR " + (p.get("pr_no") or "") + " raised",
                     "meta": f"{p.get('category') or ''} · {p.get('pr_date') or ''}",
                     "date": p.get("pr_date") or ""})
    feed.sort(key=lambda x: x.get("date") or "", reverse=True)
    return {
        "today": today,
        "manpower_on_site": manpower_on_site,
        "active_sites": len(sites),
        "dprs": len(reps),
        "open_prs": len(prs),
        "pending_attendance": pending_att,
        "feed": feed[:10],
        "alerts": alerts[:6],
    }


# ================= Personal to-do (Eisenhower matrix) =================
class TodoIn(BaseModel):
    text: str
    due_date: date_cls | None = None


class TodoPatch(BaseModel):
    text: str | None = None
    quadrant: str | None = None
    done: bool | None = None
    due_date: date_cls | None = None


@app.get("/api/v1/todos")
async def todos_list(user: dict = Depends(get_current_user)):
    # Reconcile automatic DPR tasks before returning the list. This guarantees
    # stale tasks disappear even when the user opens To-do directly.
    # A reminder scan must never make the user's normal to-do list disappear.
    # It is best-effort and bounded because it can inspect several sites/dates.
    try:
        await asyncio.wait_for(dpr_missing(days=30, user=user), timeout=8.0)
    except Exception:
        pass
    async with shared_client() as client:
        r = await client.get(f"{REST}/todos",
            params={"user_id": f"eq.{user['user_id']}", "order": "created_at.asc",
                    "select": "id,text,quadrant,done,due_date,created_at"},
            headers=supabase_headers(user["token"]))
        return r.json() if r.status_code == 200 else []


@app.post("/api/v1/todos", status_code=201)
async def todos_add(body: TodoIn, user: dict = Depends(get_current_user)):
    txt = (body.text or "").strip()
    if not txt:
        raise HTTPException(status_code=400, detail="Task text required")
    async with shared_client() as client:
        r = await client.post(f"{REST}/todos",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json={"user_id": user["user_id"], "text": txt[:400], "quadrant": "inbox",
                  "due_date": body.due_date.isoformat() if body.due_date else None})
        if r.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Could not add task ({r.status_code})")
        rows = r.json()
        return rows[0] if rows else {"ok": True}


@app.patch("/api/v1/todos/{todo_id}")
async def todos_update(todo_id: str, body: TodoPatch, user: dict = Depends(get_current_user)):
    patch = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if body.text is not None:
        patch["text"] = body.text.strip()[:400]
    if body.quadrant is not None:
        patch["quadrant"] = body.quadrant
    if body.done is not None:
        patch["done"] = body.done
    if "due_date" in body.model_fields_set:
        patch["due_date"] = body.due_date.isoformat() if body.due_date else None
    async with shared_client() as client:
        r = await client.patch(f"{REST}/todos",
            params={"id": f"eq.{todo_id}", "user_id": f"eq.{user['user_id']}"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
            json=patch)
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not update task")
        return {"ok": True}


@app.delete("/api/v1/todos/{todo_id}")
async def todos_delete(todo_id: str, user: dict = Depends(get_current_user)):
    async with shared_client() as client:
        r = await client.delete(f"{REST}/todos",
            params={"id": f"eq.{todo_id}", "user_id": f"eq.{user['user_id']}"},
            headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete task")
        return {"ok": True}


class UploadUrlIn(BaseModel):
    path: str
    content_type: str | None = "image/jpeg"


@app.post("/api/v1/storage/upload-url")
async def storage_upload_url(body: UploadUrlIn, user: dict = Depends(get_current_user)):
    """If R2 is configured, hand the browser a presigned PUT URL + the public URL.
    Otherwise reply configured:false so the frontend falls back to Supabase."""
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    if not R2_ENABLED:
        return {"configured": False}
    key = body.path.strip("/").replace("..", "")
    if not key:
        raise HTTPException(status_code=400, detail="Bad path")
    if key.lower().startswith(("worker-cards/", "worker-certificates/")):
        raise HTTPException(status_code=410, detail="Worker cards and certificates feature has been removed")
    return {"configured": True, "put_url": _r2_presign_put(key),
            "public_url": f"{R2_PUBLIC_BASE}/{key}",
            "content_type": body.content_type or "image/jpeg"}


@app.put("/api/v1/storage/upload")
async def storage_upload(request: Request, path: str, content_type: str = "image/jpeg",
                         user: dict = Depends(get_current_user)):
    """Proxy a photo/signature upload to R2 server-side (no browser→S3 CORS needed).
    Reads still come straight from the public R2 URL, so egress stays on R2."""
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    if not R2_ENABLED:
        raise HTTPException(status_code=501, detail="R2 not configured")
    key = path.strip("/").replace("..", "")
    if not key:
        raise HTTPException(status_code=400, detail="Bad path")
    if key.lower().startswith(("worker-cards/", "worker-certificates/")):
        raise HTTPException(status_code=410, detail="Worker cards and certificates feature has been removed")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty body")
    put_url = _r2_presign_put(key)
    async with shared_client() as client:
        r = await client.put(put_url, content=body, headers={"Content-Type": content_type})
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=502, detail="Photo storage upload failed")
    return {"public_url": f"{R2_PUBLIC_BASE}/{key}"}
