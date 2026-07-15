"""VMMS Backend — Phase 1 v0.2.0 (final)."""
import os

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="VMMS API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()


def supabase_headers():
    headers = {"apikey": SUPABASE_ANON_KEY}
    if SUPABASE_ANON_KEY.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {SUPABASE_ANON_KEY}"
    return headers


@app.get("/")
def root():
    return {"app": "VMMS", "phase": 1, "status": "running"}


@app.get("/api/v1/health")
async def health():
    """Checks the database via Supabase's Auth health endpoint,
    which accepts publishable keys."""
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
