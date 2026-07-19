"""
VMMS Backend — Phase 4  ·  v0.4.0
Adds the Worker Master API:
  GET    /api/v1/workers            list + search + filter (all roles)
  POST   /api/v1/workers            create (admin only)
  PATCH  /api/v1/workers/{id}       edit name/status (admin; main_sup may change status only)
Every create/update is written to the audit log.
"""
import os

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="VMMS API", version="0.4.0")

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
    return {"app": "VMMS", "phase": 4, "status": "running"}


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
