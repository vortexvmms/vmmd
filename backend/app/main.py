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
import time
import json as _json
import asyncio
from datetime import date as date_cls

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="VCMS API", version="0.73.0")  # reconcile dashboard site and KPI hour totals

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
    """Low-cost browser hardening for every API response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(self), microphone=(), geolocation=(), payment=(), usb=()"
    )
    response.headers["Cache-Control"] = "no-store"
    return response

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
# Service-role key — SERVER-SIDE ONLY. Used exclusively for admin-guarded user
# management (create login, reset password). Never sent to the frontend.
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
REST = f"{SUPABASE_URL}/rest/v1"

# ---- Cloudflare R2 photo storage (optional; falls back to Supabase if unset) ----
# Set these in Render env to send new photo uploads to R2 (10 GB free, no egress).
import hashlib as _hl, hmac as _hm, datetime as _dt, urllib.parse as _up
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET = os.environ.get("R2_BUCKET", "").strip()
R2_PUBLIC_BASE = os.environ.get("R2_PUBLIC_BASE", "").strip().rstrip("/")
R2_ENABLED = all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET, R2_BUCKET, R2_PUBLIC_BASE])

def _r2_presign_put(key: str, expires: int = 600) -> str:
    """SigV4 presigned PUT URL for R2 (host-only signed, unsigned payload)."""
    host = f"{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    region, service = "auto", "s3"
    now = _dt.datetime.utcnow()
    amzdate = now.strftime("%Y%m%dT%H%M%SZ"); datestamp = now.strftime("%Y%m%d")
    canon_uri = "/" + R2_BUCKET + "/" + _up.quote(key, safe="/~")
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    q = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{R2_ACCESS_KEY_ID}/{scope}",
        "X-Amz-Date": amzdate,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    canon_qs = "&".join(f"{_up.quote(k, safe='~')}={_up.quote(v, safe='~')}" for k, v in sorted(q.items()))
    canon_req = f"PUT\n{canon_uri}\n{canon_qs}\nhost:{host}\n\nhost\nUNSIGNED-PAYLOAD"
    sts = f"AWS4-HMAC-SHA256\n{amzdate}\n{scope}\n{_hl.sha256(canon_req.encode()).hexdigest()}"
    def _sign(k, m): return _hm.new(k, m.encode(), _hl.sha256).digest()
    k_date = _sign(("AWS4" + R2_SECRET).encode(), datestamp)
    k_sign = _sign(_sign(_sign(k_date, region), service), "aws4_request")
    sig = _hm.new(k_sign, sts.encode(), _hl.sha256).hexdigest()
    return f"https://{host}{canon_uri}?{canon_qs}&X-Amz-Signature={sig}"

# ---- one shared HTTP client to Supabase ----------------------------------
# Every call used to open a brand-new httpx client, which meant a fresh TLS
# handshake to Supabase for each of the ~6 hops in a single attendance save.
# Reusing one kept-alive client keeps the connection open, cutting ~100-300ms
# off every database call — a big latency win on the free tier at zero cost.
# A single AsyncClient is safe for concurrent use across requests.
_HTTP = httpx.AsyncClient(
    timeout=20,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=40,
                        keepalive_expiry=120),
)


class _KeepOpen:
    """Yield the shared client inside `async with` without closing it after."""
    def __init__(self, c): self._c = c
    async def __aenter__(self): return self._c
    async def __aexit__(self, *exc): return False


def shared_client(*_a, **_k):
    """Drop-in for httpx.AsyncClient(...) that returns the shared client."""
    return _KeepOpen(_HTTP)


@app.on_event("shutdown")
async def _close_http():
    await _HTTP.aclose()


def supabase_headers(user_token: str | None = None) -> dict:
    headers = {"apikey": SUPABASE_ANON_KEY}
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
    elif SUPABASE_ANON_KEY.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {SUPABASE_ANON_KEY}"
    return headers


def service_headers() -> dict:
    """Elevated headers for Supabase Auth admin operations (server-side only)."""
    return {"apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json"}


def require_service():
    if not SUPABASE_SERVICE_KEY:
        raise HTTPException(
            status_code=501,
            detail="Admin key not set up on the server yet. Add SUPABASE_SERVICE_ROLE_KEY "
                   "in the backend (Render) environment, then try again.")


# ---------------- Role tiers (Rev 6) ----------------
# FULL       — admin, general_manager, operation_manager, hr_assistant  (everything)
# MANAGER    — main_sup (Site Manager), wshc_lead  (all but workers/sites/allocation/users)
# SUPERVISOR — site_sup, safety_sup, wshc, logistics_sup  (own site attendance/requests)
FULL_ROLES = ("admin", "general_manager", "operation_manager", "hr_assistant")
MANAGER_ROLES = ("main_sup", "wshc_lead")
SUPERVISOR_ROLES = ("site_sup", "safety_sup", "wshc", "logistics_sup")
ATTENDANCE_ROLES = FULL_ROLES + MANAGER_ROLES + SUPERVISOR_ROLES   # who can do attendance / requests
COORDINATOR_ROLES = FULL_ROLES + MANAGER_ROLES                     # who can generate broadcast messages
ALL_ROLES = FULL_ROLES + MANAGER_ROLES + SUPERVISOR_ROLES + ("payroll",)


# --- identity cache -------------------------------------------------------
# Every authenticated request otherwise costs TWO Supabase round-trips just to
# identify the user (verify the JWT, then read the profile row). During
# attendance a supervisor taps dozens of end-time chips in a burst — that was
# ~2 extra network hops per tap on the free tier, which is what made each tap
# feel like the server was "waking up" again. We cache the resolved identity
# per token for a short window so a burst of taps reuses it. Trade-off: a role
# or status change takes up to _USER_CACHE_TTL seconds to take effect.
# The cache is keyed by the login token, which Supabase rotates roughly hourly
# (the app auto-refreshes it), so caching for a token's full life effectively
# means "for the whole session" — a new token after refresh is a fresh lookup.
_USER_CACHE: dict[str, tuple[float, dict]] = {}
_USER_CACHE_TTL = 600  # 10 min: fast for attendance, bounded if invalidation misses


def _cache_get(token: str):
    hit = _USER_CACHE.get(token)
    if hit and hit[0] > time.time():
        u = dict(hit[1]); u["token"] = token
        return u
    return None


def _cache_put(token: str, user: dict):
    _USER_CACHE[token] = (time.time() + _USER_CACHE_TTL,
                          {k: v for k, v in user.items() if k != "token"})
    if len(_USER_CACHE) > 400:                       # opportunistic cleanup
        now = time.time()
        for k in [k for k, (exp, _) in _USER_CACHE.items() if exp <= now]:
            _USER_CACHE.pop(k, None)


def _cache_invalidate_users(user_ids) -> None:
    """Immediately revoke cached role/status/site context for selected profiles."""
    wanted = {str(x) for x in (user_ids or []) if x}
    if not wanted:
        return
    for token, (_, profile) in list(_USER_CACHE.items()):
        if str(profile.get("user_id")) in wanted:
            _USER_CACHE.pop(token, None)


async def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not signed in")
    token = auth.removeprefix("Bearer ").strip()

    cached = _cache_get(token)
    if cached:
        return cached

    async with shared_client() as client:
        r = await client.get(f"{SUPABASE_URL}/auth/v1/user", headers=supabase_headers(token))
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Session expired — please log in again")
        auth_user = r.json()
        auth_uid = auth_user.get("id")

        r2 = await client.get(
            f"{REST}/users",
            params={"auth_uid": f"eq.{auth_uid}", "select": "id,name,role,status,menu,dpr_reminders,dpr_reminder_sites"},
            headers=supabase_headers(token),
        )
        if r2.status_code != 200:   # tolerate the 'menu' column not existing yet
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

    user = {
        "token": token,
        "auth_uid": auth_uid,
        "email": auth_user.get("email"),
        "user_id": profile["id"],
        "name": profile["name"],
        "role": profile["role"],
        "menu": profile.get("menu"),
        "dpr_reminders": bool(profile.get("dpr_reminders", False)),
        "dpr_reminder_sites": profile.get("dpr_reminder_sites"),
    }
    _cache_put(token, user)
    return user


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
    params = {"select": "id,name,role,status,menu,notify_all,notify_requests,dpr_reminders,dpr_reminder_sites", "order": "name.asc"}
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
    notify_all: bool | None = None       # receives EVERY notification (developer)
    notify_requests: bool | None = None  # receives manpower-request notifications (allocator)
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

    if "notify_all" in fields:
        updates["notify_all"] = bool(body.notify_all)
    if "notify_requests" in fields:
        updates["notify_requests"] = bool(body.notify_requests)
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

        # notify the site's supervisors with the request outcome (allocated / not allocated)
        if to_add or to_remove:
            rs = await client.get(f"{REST}/sites", params={"id": f"eq.{body.site_id}", "select": "site_name"},
                                  headers=supabase_headers(user["token"]))
            sname = rs.json()[0]["site_name"] if rs.status_code == 200 and rs.json() else "your site"
            svc = service_headers() if SUPABASE_SERVICE_KEY else supabase_headers(user["token"])
            rq = await client.get(f"{REST}/manpower_requests",
                                  params={"request_date": f"eq.{body.work_date}",
                                          "site_id": f"eq.{body.site_id}", "select": "worker_id"},
                                  headers=svc)
            reqset = {x["worker_id"] for x in (rq.json() if rq.status_code == 200 else [])}
            if reqset:
                got = len(reqset & requested)
                pending = len(reqset - requested)
                msg = (f"{sname} · {body.work_date}: {got} of your {len(reqset)} requested worker(s) allocated" +
                       (f" — {pending} NOT allocated to you." if pending else " — all allocated ✓."))
            else:
                msg = f"{len(requested)} worker(s) allocated to {sname} for {body.work_date}."
            await notify_site_supervisors(client, [body.site_id], "allocation", "Allocation updated",
                                          msg, link=f"attendance.html?date={body.work_date}")
        return {"ok": True, "added": len(to_add), "removed": len(to_remove)}


@app.post("/api/v1/allocations/copy")
async def copy_allocation(body: AllocationCopy, user: dict = Depends(get_current_user)):
    require_allocator(user)
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

        # notify supervisors of every site that received workers
        if copied:
            site_ids = list({a["site_id"] for a in active_rows if a["worker_id"] not in already})
            await notify_site_supervisors(client, site_ids, "allocation", "Manpower allocated",
                                          f"Allocation done for {body.to_date} ({copied} worker(s)).",
                                          link=f"attendance.html?date={body.to_date}")
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

        # notify the allocator (Mani) that a site requested manpower
        rs = await client.get(f"{REST}/sites", params={"id": f"eq.{body.site_id}", "select": "site_name"},
                              headers=supabase_headers(user["token"]))
        sname = rs.json()[0]["site_name"] if rs.status_code == 200 and rs.json() else "A site"
        await notify_allocator(client, "request", "Manpower requested",
                               f"{sname} requested {len(requested)} worker(s) for {body.request_date}.",
                               link=f"allocation.html?date={body.request_date}")
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
            })
        return sorted(out, key=lambda x: (x["site_name"], x["worker_name"]))


@app.patch("/api/v1/attendance/mark")
async def mark_attendance(body: AttendanceMark, user: dict = Depends(get_current_user)):
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    if body.start_time and user["role"] in SUPERVISOR_ROLES:
        raise HTTPException(status_code=403, detail="Start time can only be changed by the Main Supervisor or Administrator")

    async with shared_client() as client:
        # the allocation (RLS scopes site_sup to own sites automatically)
        ra = await client.get(
            f"{REST}/allocations",
            params={"id": f"eq.{body.allocation_id}",
                    "select": "id,work_date,site_id,worker_id,attendance(id,present,start_time,end_time,end_next_day,submitted_at)"},
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

        # "Class" = paid training day. The worker is not on site but the company
        # pays 08:00–17:00 (a normal 8-hour day). Stored as a present, paid day and
        # tagged 'class' so reports can show it distinctly.
        if body.absence_type == "class":
            present, start, end, end_nd = True, "08:00", "17:00", False

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
        if ru.status_code not in (200, 201):
            raise HTTPException(status_code=500,
                detail=f"Could not save attendance (db {ru.status_code}: {ru.text[:160]})")
        if not ru.json():
            raise HTTPException(status_code=500,
                detail="Attendance not saved — the update matched no row (permission / RLS, or the day changed). Reload the day and try again.")

        # split-day: if this worker worked at more than one site today,
        # recalculate the whole day so the 8-hour normal quota is applied once
        try:
            res = await recompute_worker_day(client, user["token"],
                                             alloc["work_date"], alloc["worker_id"], day_type)
            if res:
                normal, ot = res.get(body.allocation_id, (normal, ot))
        except Exception:
            # The individual attendance row is already saved. A secondary
            # split-day recalculation must never turn that success into a false
            # "Failed to fetch" message on the supervisor's phone.
            pass

        try:
            await audit(client, user, "mark_attendance", "attendance", body.allocation_id,
                        {k: att.get(k) for k in ("present", "end_time")} if att else None,
                        {"present": present, "end_time": end, "normal": normal, "ot": ot})
        except Exception:
            pass

        # absence (MC / UL / AL) → notify Operation Manager, Site Manager, HR Assistant
        was_present = att["present"] if att else None
        if not present and was_present is not False:   # newly marked absent
            wname, sname2 = "?", "?"
            try:
                rw = await client.get(f"{REST}/allocations",
                                      params={"id": f"eq.{body.allocation_id}",
                                              "select": "workers(name),sites(site_name)"},
                                      headers=supabase_headers(user["token"]))
                j = rw.json()[0] if rw.status_code == 200 and rw.json() else {}
                wname = (j.get("workers") or {}).get("name", "?")
                sname2 = (j.get("sites") or {}).get("site_name", "?")
            except Exception:
                pass
            code = (absence or "absent").upper()
            try:
                await notify_roles(client, ["operation_manager", "main_sup", "hr_assistant"],
                                   "absence", f"Worker absence — {code}",
                                   f"{wname} marked {code} at {sname2} on {alloc['work_date']}.",
                                   link=f"attendance.html?date={alloc['work_date']}")
            except Exception:
                pass
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
        sel = set(body.allocation_ids) if body.allocation_ids else None
        end_nd = bool(body.end_next_day)
        updated = 0
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
            start = att["start_time"][:5] if att and att["start_time"] else "08:00"
            normal, ot = compute_hours(day_type, start, body.end_time, end_nd)
            payload = {"present": True, "start_time": start, "end_time": body.end_time,
                       "end_next_day": end_nd, "normal_hours": normal, "ot_hours": ot,
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
        try:
            await audit(client, user, "bulk_end", "attendance",
                        f"{body.work_date}:{body.site_id}", None,
                        {"end_time": body.end_time, "workers": updated})
        except Exception:
            pass
        return {"ok": True, "updated": updated}


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


ABSENCE_LABEL = {"mc": "MC", "ul": "UL", "al": "AL"}


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
             f"*SUPERVISOR: {supervisor.upper()}*",
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

        # everything in the selected date's month, up to and including that date.
        # PostgREST caps a single response at ~1000 rows, so a busy month would be
        # truncated (dropping the latest day's allocations). Page through them all.
        month_rows = []
        _off, _page = 0, 1000
        while True:
            rm = await client.get(
                f"{REST}/allocations",
                params={"and": f"(work_date.gte.{month_start},work_date.lte.{today})",
                        "status": "eq.allocated",
                        "select": "work_date,site_id,worker_id,sites(site_name),"
                                  "workers(name,worker_code),"
                                  "attendance(present,submitted_at,normal_hours,ot_hours,absence_type)",
                        "order": "work_date.asc,id.asc", "limit": _page, "offset": _off},
                headers=supabase_headers(user["token"]))
            if rm.status_code != 200:
                break
            batch = rm.json()
            month_rows.extend(batch)
            if len(batch) < _page:
                break
            _off += _page

        month_nh = month_ot = 0.0
        today_mc = today_al = today_ul = 0
        today_by_site: dict[str, dict] = {}
        site_month: dict[str, dict] = {}
        # per-worker leave tally for the month → "who takes the most MC/AL/UL"
        leave_by_worker: dict[str, dict] = {}

        for a in month_rows:
            sname = (a.get("sites") or {}).get("site_name", "?")
            att = a.get("attendance")
            nh = float(att["normal_hours"]) if att and att["present"] else 0.0
            ot = float(att["ot_hours"]) if att and att["present"] else 0.0
            month_nh += nh
            month_ot += ot

            # count each MC / AL / UL day per worker across the month
            if att and not att.get("present"):
                at = att.get("absence_type")
                if at in ("mc", "al", "ul"):
                    w = a.get("workers") or {}
                    code = w.get("worker_code") or a.get("worker_id") or "?"
                    lw = leave_by_worker.setdefault(
                        code, {"name": w.get("name", "?"), "code": code, "mc": 0, "al": 0, "ul": 0})
                    lw[at] += 1

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
                    if not att["present"]:
                        at = att.get("absence_type")
                        if at == "mc": today_mc += 1
                        elif at == "al": today_al += 1
                        elif at == "ul": today_ul += 1

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
                      "attendance(present,start_time,end_time,normal_hours,ot_hours,day_type,submitted_at,absence_type)",
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


# ================= Notifications (Rev 9) =================
# Notifications are created server-side with the service key and routed to the
# right recipients. Every notification also copies to users flagged notify_all
# (the developer). A notification failure never breaks the underlying action.

async def _svc_user_ids(client, params: dict) -> list[str]:
    if not SUPABASE_SERVICE_KEY:
        return []
    p = {"status": "eq.active", "select": "id", **params}
    r = await client.get(f"{REST}/users", params=p, headers=service_headers())
    return [u["id"] for u in (r.json() if r.status_code == 200 else [])]


async def notify(client, recipients, kind, title, body="", link=None):
    """Insert one notification per recipient (deduped) + everyone notify_all,
    and also send a phone Web Push to those same recipients."""
    if not SUPABASE_SERVICE_KEY:
        return
    try:
        ids = set(r for r in (recipients or []) if r)
        ids.update(await _svc_user_ids(client, {"notify_all": "eq.true"}))
        if not ids:
            return
        rows = [{"user_id": uid, "kind": kind, "title": title,
                 "body": body, "link": link} for uid in ids]
        await client.post(f"{REST}/notifications",
                          headers={**service_headers(), "Prefer": "return=minimal"},
                          json=rows)
        await send_web_push(client, list(ids), title, body, link)
    except Exception:
        pass


# ---- Web Push (phone notifications) ----
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@vortex.sg").strip()
PUSH_ENABLED = bool(VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)


async def send_web_push(client, user_ids, title, body="", link=None):
    """Send a Web Push to every device of the given users; prune expired ones."""
    if not (PUSH_ENABLED and SUPABASE_SERVICE_KEY and user_ids):
        return
    try:
        ids = list({u for u in user_ids if u})
        if not ids:
            return
        r = await client.get(f"{REST}/push_subscriptions",
                             params={"user_id": f"in.({','.join(ids)})",
                                     "select": "endpoint,p256dh,auth"},
                             headers=service_headers())
        subs = r.json() if r.status_code == 200 else []
        if not subs:
            return
        payload = _json.dumps({"title": title, "body": body or "", "url": link or "home.html"})

        def _send_one(s):
            from pywebpush import webpush, WebPushException
            try:
                webpush({"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                        data=payload, vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims={"sub": VAPID_SUBJECT}, ttl=3600)
                return None
            except WebPushException as e:
                code = getattr(getattr(e, "response", None), "status_code", None)
                return s["endpoint"] if code in (404, 410) else None
            except Exception:
                return None

        results = await asyncio.gather(*[asyncio.to_thread(_send_one, s) for s in subs])
        dead = [e for e in results if e]
        if dead:
            await client.delete(f"{REST}/push_subscriptions",
                                params={"endpoint": f"in.({','.join(dead)})"},
                                headers=service_headers())
    except Exception:
        pass


async def notify_roles(client, roles, kind, title, body="", link=None):
    ids = await _svc_user_ids(client, {"role": f"in.({','.join(roles)})"})
    await notify(client, ids, kind, title, body, link)


async def notify_site_supervisors(client, site_ids, kind, title, body="", link=None):
    if not SUPABASE_SERVICE_KEY or not site_ids:
        return
    try:
        r = await client.get(f"{REST}/site_supervisors",
                             params={"site_id": f"in.({','.join(site_ids)})", "select": "user_id"},
                             headers=service_headers())
        ids = [u["user_id"] for u in (r.json() if r.status_code == 200 else [])]
        await notify(client, ids, kind, title, body, link)
    except Exception:
        pass


async def notify_allocator(client, kind, title, body="", link=None):
    """Manpower-request notifications go to users flagged notify_requests (the allocator)."""
    ids = await _svc_user_ids(client, {"notify_requests": "eq.true"})
    await notify(client, ids, kind, title, body, link)


@app.get("/api/v1/notifications")
async def list_notifications(user: dict = Depends(get_current_user)):
    async with shared_client() as client:
        r = await client.get(
            f"{REST}/notifications",
            params={"user_id": f"eq.{user['user_id']}", "order": "created_at.desc",
                    "limit": "50",
                    "select": "id,kind,title,body,link,read_at,created_at"},
            headers=supabase_headers(user["token"]))
        rows = r.json() if r.status_code == 200 else []
        unread = sum(1 for x in rows if not x.get("read_at"))
        return {"items": rows, "unread": unread}


@app.get("/api/v1/notifications-count")
async def notification_count(user: dict = Depends(get_current_user)):
    """Tiny startup request for the global bell. Notification bodies are loaded
    only when the user opens the panel, keeping every mobile page responsive."""
    async with shared_client() as client:
        r = await client.get(
            f"{REST}/notifications",
            params={"user_id": f"eq.{user['user_id']}", "read_at": "is.null",
                    "select": "id", "limit": "1"},
            headers={**supabase_headers(user["token"]), "Prefer": "count=exact"})
        if r.status_code not in (200, 206):
            return {"unread": 0}
        cr = r.headers.get("content-range", "0-0/0")
        try:
            unread = int(cr.rsplit("/", 1)[1])
        except Exception:
            unread = len(r.json() or [])
        return {"unread": unread}


@app.post("/api/v1/notifications/read_all")
async def read_all_notifications(user: dict = Depends(get_current_user)):
    async with shared_client() as client:
        await client.patch(
            f"{REST}/notifications",
            params={"user_id": f"eq.{user['user_id']}", "read_at": "is.null"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"},
            json={"read_at": datetime.now(timezone.utc).isoformat()})
        return {"ok": True}


@app.delete("/api/v1/notifications")
async def clear_notifications(user: dict = Depends(get_current_user)):
    async with shared_client() as client:
        await client.delete(
            f"{REST}/notifications",
            params={"user_id": f"eq.{user['user_id']}"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=minimal"})
        return {"ok": True}


# ================= Web Push subscriptions =================
class PushSubIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str | None = None


class PushEp(BaseModel):
    endpoint: str


@app.get("/api/v1/push/pubkey")
async def push_pubkey():
    tbl = None
    if SUPABASE_SERVICE_KEY:
        try:
            async with shared_client() as c:
                r = await c.get(f"{REST}/push_subscriptions",
                                params={"select": "id", "limit": "1"},
                                headers=service_headers())
                tbl = r.status_code
        except Exception:
            tbl = "err"
    return {"enabled": PUSH_ENABLED, "public_key": VAPID_PUBLIC_KEY, "table": tbl}


@app.post("/api/v1/push/subscribe")
async def push_subscribe(body: PushSubIn, user: dict = Depends(get_current_user)):
    async with shared_client() as client:
        # Save with the service role: the backend already authenticated the user and
        # sets user_id explicitly, so this is safe and avoids RLS/token-expiry issues.
        r = await client.post(
            f"{REST}/push_subscriptions",
            params={"on_conflict": "endpoint"},
            headers={**service_headers(),
                     "Prefer": "resolution=merge-duplicates,return=minimal"},
            json={"user_id": user["user_id"], "endpoint": body.endpoint,
                  "p256dh": body.p256dh, "auth": body.auth, "user_agent": body.user_agent})
        if r.status_code not in (200, 201, 204):
            raise HTTPException(status_code=500, detail="Could not save subscription.")
        return {"ok": True}


@app.post("/api/v1/push/unsubscribe")
async def push_unsubscribe(body: PushEp, user: dict = Depends(get_current_user)):
    async with shared_client() as client:
        await client.delete(
            f"{REST}/push_subscriptions",
            params={"endpoint": f"eq.{body.endpoint}", "user_id": f"eq.{user['user_id']}"},
            headers=service_headers())
    return {"ok": True}


@app.post("/api/v1/push/test")
async def push_test(user: dict = Depends(get_current_user)):
    async with shared_client() as client:
        await send_web_push(client, [user["user_id"]], "VCMS test",
                            "Phone notifications are working.", "home.html")
    return {"ok": True}


class BroadcastIn(BaseModel):
    title: str
    body: str | None = ""
    target: str = "all"           # all | role | site
    roles: list[str] | None = None
    site_ids: list[str] | None = None
    link: str | None = None


@app.post("/api/v1/push/broadcast")
async def push_broadcast(body: BroadcastIn, user: dict = Depends(get_current_user)):
    """Admin-only: send a custom notification (bell + phone push) to everyone,
    to selected roles, or to the supervisors of selected sites."""
    if user["role"] not in FULL_ROLES:
        raise HTTPException(status_code=403, detail="Only administrators can send notifications.")
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Message title is required.")
    if not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Service role not configured.")
    async with shared_client() as client:
        ids = set()
        if body.target == "role" and body.roles:
            ids.update(await _svc_user_ids(client, {"role": f"in.({','.join(body.roles)})"}))
        elif body.target == "site" and body.site_ids:
            r = await client.get(f"{REST}/site_supervisors",
                                 params={"site_id": f"in.({','.join(body.site_ids)})",
                                         "select": "user_id"},
                                 headers=service_headers())
            ids.update(u["user_id"] for u in (r.json() if r.status_code == 200 else []))
        else:
            ids.update(await _svc_user_ids(client, {}))   # all active users
        ids = [i for i in ids if i]
        if not ids:
            return {"ok": True, "recipients": 0}
        link = body.link or "home.html"
        text = (body.body or "").strip()
        rows = [{"user_id": uid, "kind": "broadcast", "title": title,
                 "body": text, "link": link} for uid in ids]
        await client.post(f"{REST}/notifications",
                          headers={**service_headers(), "Prefer": "return=minimal"},
                          json=rows)
        await send_web_push(client, ids, title, text, link)
        return {"ok": True, "recipients": len(ids)}


# ================= Scheduled reminders (cron → push) =================
REMINDER_TOKEN = os.environ.get("REMINDER_TOKEN", "").strip()


def _sgt_today():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()


async def _pending_sites(client, mode: str):
    """Site IDs with outstanding submissions today (mode: 'attendance' | 'endtime')."""
    today = _sgt_today()
    r = await client.get(
        f"{REST}/allocations",
        params={"work_date": f"eq.{today}", "status": "eq.allocated",
                "select": "site_id,attendance(present,end_time,submitted_at)"},
        headers=service_headers())
    rows = r.json() if r.status_code == 200 else []
    bad = set()
    for a in rows:
        sid = a.get("site_id")
        att = a.get("attendance")
        if isinstance(att, list):
            att = att[0] if att else None
        if mode == "attendance":
            if not att or not att.get("submitted_at"):
                bad.add(sid)
        else:  # endtime
            if not att or not att.get("submitted_at"):
                bad.add(sid)
            elif att.get("present") and not att.get("end_time"):
                bad.add(sid)
    bad.discard(None)
    return bad


async def _remind_sites(client, site_ids, title, body, link):
    if not site_ids:
        return
    sites = {}
    try:
        r = await client.get(f"{REST}/sites",
                             params={"id": f"in.({','.join(site_ids)})", "select": "id,site_name"},
                             headers=service_headers())
        sites = {s["id"]: s["site_name"] for s in (r.json() if r.status_code == 200 else [])}
    except Exception:
        pass
    for sid in site_ids:
        nm = sites.get(sid, "your site")
        await notify_site_supervisors(client, [sid], "reminder", title, f"{body} — {nm}", link)


@app.post("/api/v1/reminders/attendance")
async def remind_attendance(request: Request):
    if not REMINDER_TOKEN or request.headers.get("x-cron-token") != REMINDER_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    async with shared_client() as client:
        sids = await _pending_sites(client, "attendance")
        await _remind_sites(client, sids, "Attendance reminder",
                            "Please mark & submit this morning's attendance", "attendance.html")
    return {"reminded_sites": len(sids)}


@app.post("/api/v1/reminders/endtime")
async def remind_endtime(request: Request):
    if not REMINDER_TOKEN or request.headers.get("x-cron-token") != REMINDER_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    async with shared_client() as client:
        sids = await _pending_sites(client, "endtime")
        await _remind_sites(client, sids, "End-time reminder",
                            "Please submit today's end-times", "attendance.html")
    return {"reminded_sites": len(sids)}


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
        return rows[0] if rows else {"ok": True}


def _rs_clean(v):
    if isinstance(v, float):
        return int(v) if v.is_integer() else round(v, 1)
    return v


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

    async with shared_client() as client:
        r = await client.get(
            f"{REST}/daily_reports",
            params={"site_id": f"eq.{site_id}",
                    "and": f"(report_date.gte.{start},report_date.lte.{end})",
                    "select": "report_date,project_title,location,item_of_work,manpower,equipment,materials",
                    "order": "report_date.asc"},
            headers=supabase_headers(user["token"]))
        reports = r.json() if r.status_code == 200 else []

    att, mp_pos, mats, plant = {}, {}, {}, {}
    manhours = {d: 0.0 for d in days}
    header = {"project_title": "", "location": "", "item_of_work": ""}

    for rep in reports:
        try:
            d = int(rep["report_date"].split("-")[2])
        except Exception:
            continue
        for k in header:
            if not header[k] and rep.get(k):
                header[k] = rep[k]
        for w in (rep.get("manpower") or []):
            name = (w.get("name") or "").strip()
            role = _rs_norm_role(w.get("role"))
            hrs = float(w.get("total") or 0)
            no = int(w.get("no") or 1)
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
            no = float(e.get("no") or 0) or 1
            key = name.lower()
            pl = plant.setdefault(key, {"name": name, "unit": "Nos", "days": {}, "total": 0.0})
            pl["days"][d] = pl["days"].get(d, 0.0) + no
            pl["total"] += no
        for mt in (rep.get("materials") or []):
            name = " ".join((mt.get("name") or "").split())
            if not name:
                continue
            unit = (mt.get("unit") or "").strip()
            qty = float(mt.get("qty") or 0)
            key = name.lower() + "||" + unit.lower()
            mm = mats.setdefault(key, {"name": name, "unit": unit, "days": {}, "total": 0.0})
            mm["days"][d] = mm["days"].get(d, 0.0) + qty
            mm["total"] += qty

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
    end_d = date_cls.fromisoformat(_sgt_today()) - timedelta(days=1)
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
        ra, rr = await asyncio.gather(
            client.get(f"{REST}/allocations",
                params={"status": "eq.allocated", "and": f"(work_date.gte.{start},work_date.lte.{end})",
                        "select": "work_date,site_id,sites(site_name)"},
                headers=supabase_headers(user["token"])),
            client.get(f"{REST}/daily_reports",
                params={"and": f"(report_date.gte.{start},report_date.lte.{end})",
                        "select": "report_date,site_id"},
                headers=supabase_headers(user["token"])),
        )
        alloc = ra.json() if ra.status_code == 200 else []
        reports = rr.json() if rr.status_code == 200 else []
        prepared = {(x.get("site_id"), x.get("report_date")) for x in reports}
        missing_map = {}
        for x in alloc:
            key = (x.get("site_id"), x.get("work_date"))
            if key[0] and key[1] and key not in prepared:
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


class ProjectIn(BaseModel):
    title: str
    to_party: str | None = None
    attention: str | None = None
    location: str | None = None
    item_of_work: str | None = None
    site_id: str | None = None


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
async def site_progress(days: int = 14, user: dict = Depends(get_current_user)):
    if user["role"] not in DPR_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    days = max(1, min(60, days))
    today = _sgt_today()
    start = (date_cls.fromisoformat(today) - timedelta(days=days - 1)).isoformat()
    params = {"select": "report_date,site_id,item_of_work,description,manpower,photos,prepared_by_name,sites(site_name)",
              "and": f"(report_date.gte.{start},report_date.lte.{today})",
              "order": "report_date.desc", "limit": "1000"}
    async with shared_client() as client:
        r = await client.get(f"{REST}/daily_reports", params=params,
                             headers=supabase_headers(user["token"]))
        rows = r.json() if r.status_code == 200 else []
    sites, trend, feed = {}, {}, []
    for row in rows:
        sid = row.get("site_id"); d = row.get("report_date")
        mp = len(row.get("manpower") or []); ph = len(row.get("photos") or [])
        name = (row.get("sites") or {}).get("site_name", "?")
        if sid not in sites:
            sites[sid] = {"site_id": sid, "site_name": name, "latest_date": d,
                          "item_of_work": row.get("item_of_work"), "manpower": mp, "photos": ph,
                          "activity": (row.get("description") or "")[:180],
                          "prepared_by": row.get("prepared_by_name")}
        trend[d] = trend.get(d, 0) + mp
        if len(feed) < 30:
            feed.append({"date": d, "site_name": name, "item_of_work": row.get("item_of_work"),
                         "manpower": mp, "activity": (row.get("description") or "")[:150]})
    site_list = sorted(sites.values(), key=lambda x: (x["latest_date"] or ""), reverse=True)
    return {
        "today": today, "days": days,
        "active_sites": len(site_list),
        "manpower_latest": sum(s["manpower"] for s in site_list),
        "dprs": len(rows),
        "sites": site_list,
        "trend": [{"date": k, "manpower": trend[k]} for k in sorted(trend.keys())],
        "feed": feed,
    }


@app.get("/api/v1/home-overview")
async def home_overview(user: dict = Depends(get_current_user)):
    """Cross-module snapshot for the home dashboard: manpower on site, active
    sites, DPRs, open PRs, pending attendance, an activity feed and alerts."""
    today = _sgt_today()
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
    await dpr_missing(days=30, user=user)
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


# ---------------- Worker Cards / Training documents ----------------
# Everyone except Operation Manager and General Manager maintains worker cards.
CARD_ROLES = ()  # Feature retired: worker cards/certificates are not accessible


class CardIn(BaseModel):
    worker_id: str
    category: str = "course"          # work_permit | visit_pass | course | other
    label: str | None = None
    image_path: str                   # front image (public R2/Supabase URL)
    back_image_path: str | None = None
    issued_date: str | None = None    # YYYY-MM-DD
    expiry_date: str | None = None
    institute: str | None = None
    cert_no: str | None = None
    position: int | None = None


class CardPatch(BaseModel):
    category: str | None = None
    label: str | None = None
    issued_date: str | None = None
    expiry_date: str | None = None
    institute: str | None = None
    cert_no: str | None = None
    position: int | None = None
    image_path: str | None = None
    back_image_path: str | None = None


@app.get("/api/v1/worker-cards/expiring")
async def worker_cards_expiring(days: int = 90, user: dict = Depends(get_current_user)):
    """Cards that expire within `days` (for the compliance / renewal view)."""
    if user["role"] not in CARD_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    from datetime import date, timedelta
    until = (date.today() + timedelta(days=max(0, days))).isoformat()
    async with shared_client() as client:
        r = await client.get(
            f"{REST}/worker_cards",
            params={"select": "id,worker_id,category,label,image_path,issued_date,expiry_date,"
                              "workers(name,worker_code,fin)",
                    "expiry_date": f"lte.{until}", "order": "expiry_date.asc"},
            headers=supabase_headers(user["token"]))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load expiring cards")
        return [x for x in r.json() if x.get("expiry_date")]


@app.get("/api/v1/worker-cards/matrix")
async def worker_cards_matrix(user: dict = Depends(get_current_user)):
    """All cards with their worker, for the Training Matrix dashboard."""
    if user["role"] not in CARD_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.get(
            f"{REST}/worker_cards",
            params={"select": "id,worker_id,category,label,issued_date,expiry_date,image_path,"
                              "workers(name,worker_code,fin,status)",
                    "order": "created_at.asc"},
            headers=supabase_headers(user["token"]))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load matrix")
        return r.json()


@app.get("/api/v1/worker-cards")
async def list_worker_cards(worker_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in CARD_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.get(
            f"{REST}/worker_cards",
            params={"worker_id": f"eq.{worker_id}",
                    "select": "id,worker_id,category,label,image_path,back_image_path,issued_date,expiry_date,institute,cert_no,position",
                    "order": "position.asc,created_at.asc"},
            headers=supabase_headers(user["token"]))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load cards")
        return r.json()


@app.post("/api/v1/worker-cards", status_code=201)
async def add_worker_card(body: CardIn, user: dict = Depends(get_current_user)):
    if user["role"] not in CARD_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    rec = {"worker_id": body.worker_id, "category": (body.category or "course"),
           "label": (body.label or None), "image_path": body.image_path,
           "back_image_path": body.back_image_path or None,
           "issued_date": body.issued_date or None, "expiry_date": body.expiry_date or None,
           "institute": body.institute or None, "cert_no": body.cert_no or None,
           "position": body.position or 0, "uploaded_by": user["user_id"]}
    async with shared_client() as client:
        r = await client.post(
            f"{REST}/worker_cards",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json=rec)
        if r.status_code not in (200, 201) or not r.json():
            raise HTTPException(status_code=500, detail="Could not save card")
        return r.json()[0]


@app.patch("/api/v1/worker-cards/{card_id}")
async def patch_worker_card(card_id: str, body: CardPatch, user: dict = Depends(get_current_user)):
    if user["role"] not in CARD_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    ch = {}
    for f in ("category", "label", "issued_date", "expiry_date", "institute", "cert_no", "position", "image_path", "back_image_path"):
        v = getattr(body, f)
        if v is not None:
            ch[f] = (v or None) if f in ("label", "issued_date", "expiry_date", "institute", "cert_no", "back_image_path") else v
    if not ch:
        raise HTTPException(status_code=400, detail="Nothing to update")
    async with shared_client() as client:
        r = await client.patch(
            f"{REST}/worker_cards", params={"id": f"eq.{card_id}"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json=ch)
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not update card")
        return (r.json() or [{}])[0]


@app.delete("/api/v1/worker-cards/{card_id}")
async def delete_worker_card(card_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in CARD_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.delete(
            f"{REST}/worker_cards", params={"id": f"eq.{card_id}"},
            headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete card")
        return {"ok": True}


# ---------------- Worker Certificates (full A4 documents) ----------------
class CertIn(BaseModel):
    worker_id: str
    title: str | None = None
    file_path: str
    file_type: str = "image"   # 'pdf' | 'image'


@app.get("/api/v1/worker-certificates")
async def list_worker_certs(worker_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in CARD_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.get(
            f"{REST}/worker_certificates",
            params={"worker_id": f"eq.{worker_id}",
                    "select": "id,worker_id,title,file_path,file_type,created_at",
                    "order": "created_at.desc"},
            headers=supabase_headers(user["token"]))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load certificates")
        return r.json()


@app.post("/api/v1/worker-certificates", status_code=201)
async def add_worker_cert(body: CertIn, user: dict = Depends(get_current_user)):
    if user["role"] not in CARD_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    rec = {"worker_id": body.worker_id, "title": (body.title or None),
           "file_path": body.file_path, "file_type": (body.file_type or "image"),
           "uploaded_by": user["user_id"]}
    async with shared_client() as client:
        r = await client.post(
            f"{REST}/worker_certificates",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json=rec)
        if r.status_code not in (200, 201) or not r.json():
            raise HTTPException(status_code=500, detail="Could not save certificate")
        return r.json()[0]


@app.delete("/api/v1/worker-certificates/{cert_id}")
async def delete_worker_cert(cert_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in CARD_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.delete(
            f"{REST}/worker_certificates", params={"id": f"eq.{cert_id}"},
            headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete certificate")
        return {"ok": True}


# ---------------- Schedule module (Stage 1: planning core + CPM) ----------------
# Everyone signed-in can VIEW; planners (full + manager tier) edit.
SCHED_EDIT_ROLES = FULL_ROLES + MANAGER_ROLES


class SchedSettingsIn(BaseModel):
    name: str | None = None
    data_date: str | None = None
    workdays: list[int] | None = None
    currency: str | None = None


class TaskIn(BaseModel):
    site_id: str
    parent_id: str | None = None
    is_wbs: bool = False
    is_milestone: bool = False
    code: str | None = None
    name: str
    duration_days: int | None = 1
    planned_start: str | None = None
    planned_finish: str | None = None
    constraint_start: str | None = None
    sort_order: int | None = None


class TaskPatch(BaseModel):
    parent_id: str | None = None
    code: str | None = None
    name: str | None = None
    duration_days: int | None = None
    planned_start: str | None = None
    planned_finish: str | None = None
    actual_start: str | None = None
    actual_finish: str | None = None
    percent_complete: float | None = None
    status: str | None = None
    total_float: int | None = None
    is_critical: bool | None = None
    is_milestone: bool | None = None
    constraint_start: str | None = None
    sort_order: int | None = None


class LinkIn(BaseModel):
    site_id: str
    predecessor_id: str
    successor_id: str
    link_type: str = "FS"
    lag_days: int = 0


class HolidayIn(BaseModel):
    site_id: str
    hol_date: str
    label: str | None = None


class BulkDate(BaseModel):
    id: str
    planned_start: str | None = None
    planned_finish: str | None = None
    total_float: int | None = None
    is_critical: bool | None = None


class BulkDatesIn(BaseModel):
    site_id: str
    tasks: list[BulkDate]


@app.get("/api/v1/schedule")
async def get_schedule(site_id: str, user: dict = Depends(get_current_user)):
    async with shared_client() as client:
        h = supabase_headers(user["token"])
        rs = await client.get(f"{REST}/schedule_settings", params={"site_id": f"eq.{site_id}"}, headers=h)
        settings = (rs.json() or [None])[0] if rs.status_code == 200 else None
        if settings is None and user["role"] in SCHED_EDIT_ROLES:
            ins = await client.post(f"{REST}/schedule_settings",
                headers={**h, "Prefer": "return=representation"},
                json={"site_id": site_id, "created_by": user["user_id"], "updated_by": user["user_id"]})
            settings = (ins.json() or [None])[0] if ins.status_code in (200, 201) else {"site_id": site_id, "workdays": [1,2,3,4,5,6]}
        rt = await client.get(f"{REST}/schedule_tasks",
            params={"site_id": f"eq.{site_id}", "select": "*", "order": "sort_order.asc,created_at.asc"}, headers=h)
        rl = await client.get(f"{REST}/schedule_links",
            params={"site_id": f"eq.{site_id}", "select": "*"}, headers=h)
        rh = await client.get(f"{REST}/schedule_holidays",
            params={"site_id": f"eq.{site_id}", "select": "*", "order": "hol_date.asc"}, headers=h)
        return {"settings": settings or {"site_id": site_id, "workdays": [1,2,3,4,5,6]},
                "tasks": rt.json() if rt.status_code == 200 else [],
                "links": rl.json() if rl.status_code == 200 else [],
                "holidays": rh.json() if rh.status_code == 200 else []}


@app.patch("/api/v1/schedule/settings")
async def patch_schedule_settings(site_id: str, body: SchedSettingsIn, user: dict = Depends(get_current_user)):
    if user["role"] not in SCHED_EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    ch = {}
    for f in ("name", "data_date", "workdays", "currency"):
        v = getattr(body, f)
        if v is not None:
            ch[f] = v or None if f in ("name", "data_date") else v
    if not ch:
        raise HTTPException(status_code=400, detail="Nothing to update")
    ch["updated_by"] = user["user_id"]
    async with shared_client() as client:
        h = supabase_headers(user["token"])
        r = await client.patch(f"{REST}/schedule_settings", params={"site_id": f"eq.{site_id}"},
            headers={**h, "Prefer": "return=representation"}, json=ch)
        if r.status_code == 200 and r.json():
            return r.json()[0]
        # settings row may not exist yet → create
        ch["site_id"] = site_id; ch["created_by"] = user["user_id"]
        r2 = await client.post(f"{REST}/schedule_settings", headers={**h, "Prefer": "return=representation"}, json=ch)
        if r2.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Could not save settings")
        return r2.json()[0]


@app.post("/api/v1/schedule/tasks", status_code=201)
async def add_task(body: TaskIn, user: dict = Depends(get_current_user)):
    if user["role"] not in SCHED_EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    rec = {"site_id": body.site_id, "parent_id": body.parent_id or None,
           "is_wbs": body.is_wbs, "is_milestone": body.is_milestone,
           "code": body.code or None, "name": body.name.strip(),
           "duration_days": 0 if body.is_milestone else max(0, body.duration_days or 1),
           "planned_start": body.planned_start or None, "planned_finish": body.planned_finish or None,
           "constraint_start": body.constraint_start or None,
           "sort_order": body.sort_order or 0,
           "created_by": user["user_id"], "updated_by": user["user_id"]}
    async with shared_client() as client:
        r = await client.post(f"{REST}/schedule_tasks",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"}, json=rec)
        if r.status_code not in (200, 201) or not r.json():
            raise HTTPException(status_code=500, detail="Could not add task")
        return r.json()[0]


@app.patch("/api/v1/schedule/tasks/{task_id}")
async def patch_task(task_id: str, body: TaskPatch, user: dict = Depends(get_current_user)):
    if user["role"] not in SCHED_EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    ch = {}
    nullable = ("code", "planned_start", "planned_finish", "actual_start", "actual_finish", "constraint_start", "parent_id")
    for f in ("parent_id", "code", "name", "duration_days", "planned_start", "planned_finish",
              "actual_start", "actual_finish", "percent_complete", "status", "total_float",
              "is_critical", "is_milestone", "constraint_start", "sort_order"):
        v = getattr(body, f)
        if v is not None:
            ch[f] = (v or None) if f in nullable else v
    if not ch:
        raise HTTPException(status_code=400, detail="Nothing to update")
    ch["updated_by"] = user["user_id"]
    async with shared_client() as client:
        r = await client.patch(f"{REST}/schedule_tasks", params={"id": f"eq.{task_id}"},
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"}, json=ch)
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not update task")
        return (r.json() or [{}])[0]


@app.delete("/api/v1/schedule/tasks/{task_id}")
async def delete_task(task_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in SCHED_EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.delete(f"{REST}/schedule_tasks", params={"id": f"eq.{task_id}"},
            headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete task")
        return {"ok": True}


@app.post("/api/v1/schedule/links", status_code=201)
async def add_link(body: LinkIn, user: dict = Depends(get_current_user)):
    if user["role"] not in SCHED_EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    if body.predecessor_id == body.successor_id:
        raise HTTPException(status_code=400, detail="A task cannot depend on itself")
    lt = body.link_type if body.link_type in ("FS", "SS", "FF", "SF") else "FS"
    rec = {"site_id": body.site_id, "predecessor_id": body.predecessor_id,
           "successor_id": body.successor_id, "link_type": lt, "lag_days": body.lag_days or 0}
    async with shared_client() as client:
        r = await client.post(f"{REST}/schedule_links",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"}, json=rec)
        if r.status_code not in (200, 201) or not r.json():
            raise HTTPException(status_code=500, detail="Could not add link")
        return r.json()[0]


@app.delete("/api/v1/schedule/links/{link_id}")
async def delete_link(link_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in SCHED_EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.delete(f"{REST}/schedule_links", params={"id": f"eq.{link_id}"},
            headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete link")
        return {"ok": True}


@app.post("/api/v1/schedule/holidays", status_code=201)
async def add_holiday(body: HolidayIn, user: dict = Depends(get_current_user)):
    if user["role"] not in SCHED_EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.post(f"{REST}/schedule_holidays",
            headers={**supabase_headers(user["token"]), "Prefer": "return=representation"},
            json={"site_id": body.site_id, "hol_date": body.hol_date, "label": body.label or None})
        if r.status_code not in (200, 201) or not r.json():
            raise HTTPException(status_code=500, detail="Could not add holiday")
        return r.json()[0]


@app.delete("/api/v1/schedule/holidays/{hol_id}")
async def delete_holiday(hol_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in SCHED_EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        r = await client.delete(f"{REST}/schedule_holidays", params={"id": f"eq.{hol_id}"},
            headers=supabase_headers(user["token"]))
        if r.status_code not in (200, 204):
            raise HTTPException(status_code=500, detail="Could not delete holiday")
        return {"ok": True}


@app.post("/api/v1/schedule/baseline")
async def set_baseline(site_id: str, user: dict = Depends(get_current_user)):
    """Copy each task's planned dates into its baseline columns."""
    if user["role"] not in SCHED_EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        h = supabase_headers(user["token"])
        rt = await client.get(f"{REST}/schedule_tasks",
            params={"site_id": f"eq.{site_id}", "select": "id,planned_start,planned_finish"}, headers=h)
        if rt.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not read tasks")
        for t in rt.json():
            await client.patch(f"{REST}/schedule_tasks", params={"id": f"eq.{t['id']}"}, headers=h,
                json={"baseline_start": t.get("planned_start"), "baseline_finish": t.get("planned_finish")})
        await client.patch(f"{REST}/schedule_settings", params={"site_id": f"eq.{site_id}"}, headers=h,
            json={"baseline_at": "now()"})
        return {"ok": True}


@app.post("/api/v1/schedule/bulk-dates")
async def bulk_dates(body: BulkDatesIn, user: dict = Depends(get_current_user)):
    """Persist computed planned dates + float/critical after a client recalculation."""
    if user["role"] not in SCHED_EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")
    async with shared_client() as client:
        h = supabase_headers(user["token"])
        for t in body.tasks:
            upd = {}
            if t.planned_start is not None: upd["planned_start"] = t.planned_start or None
            if t.planned_finish is not None: upd["planned_finish"] = t.planned_finish or None
            if t.total_float is not None: upd["total_float"] = t.total_float
            if t.is_critical is not None: upd["is_critical"] = t.is_critical
            if upd:
                await client.patch(f"{REST}/schedule_tasks", params={"id": f"eq.{t.id}"}, headers=h, json=upd)
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
