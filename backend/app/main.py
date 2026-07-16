"""
VMMS Backend — Phase 3  ·  v0.3.0
Adds authentication: verifies the user's Supabase login token on
every protected endpoint and looks up their VMMS role.

Auth flow:
  1. Frontend logs the user in directly with Supabase Auth
     (email + password) and receives an access token.
  2. Frontend sends that token to this API as:  Authorization: Bearer <token>
  3. This API asks Supabase "who owns this token?" and then reads
     the user's role from the public.users table (RLS lets a user
     read only their own row).
"""
import os

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="VMMS API", version="0.3.0")

# Only the VMMS website (and local testing) may call this API.
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


def supabase_headers(user_token: str | None = None) -> dict:
    headers = {"apikey": SUPABASE_ANON_KEY}
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
    elif SUPABASE_ANON_KEY.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {SUPABASE_ANON_KEY}"
    return headers


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency: validates the bearer token and returns
    {auth_uid, email, user_id, name, role}. 401 if anything fails."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not signed in")
    token = auth.removeprefix("Bearer ").strip()

    async with httpx.AsyncClient(timeout=10) as client:
        # 1) Is the token valid? Ask Supabase Auth.
        r = await client.get(
            f"{SUPABASE_URL}/auth/v1/user", headers=supabase_headers(token)
        )
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Session expired — please log in again")
        auth_user = r.json()
        auth_uid = auth_user.get("id")

        # 2) What is this person's VMMS role? Read their own users row.
        r2 = await client.get(
            f"{SUPABASE_URL}/rest/v1/users",
            params={"auth_uid": f"eq.{auth_uid}", "select": "id,name,role,status"},
            headers=supabase_headers(token),
        )
        rows = r2.json() if r2.status_code == 200 else []
        if not rows:
            raise HTTPException(
                status_code=403,
                detail="Login exists but no VMMS profile/role is linked yet — ask the administrator",
            )
        profile = rows[0]
        if profile.get("status") != "active":
            raise HTTPException(status_code=403, detail="Account is deactivated")

    return {
        "auth_uid": auth_uid,
        "email": auth_user.get("email"),
        "user_id": profile["id"],
        "name": profile["name"],
        "role": profile["role"],
    }


@app.get("/")
def root():
    return {"app": "VMMS", "phase": 3, "status": "running"}


@app.get("/api/v1/health")
async def health():
    detail = {}
    db_status = "not_configured"
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{SUPABASE_URL}/auth/v1/health", headers=supabase_headers()
                )
                detail["status_code"] = r.status_code
                db_status = "connected" if r.status_code == 200 else "error"
        except Exception as e:
            detail["exception"] = type(e).__name__
            db_status = "unreachable"
    return {"server": "ok", "database": db_status, "diag": detail}


@app.get("/api/v1/me")
async def me(user: dict = Depends(get_current_user)):
    """Who am I? Used by the home screen after login."""
    return {"name": user["name"], "role": user["role"], "email": user["email"]}
