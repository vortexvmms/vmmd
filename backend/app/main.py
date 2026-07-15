"""VMMS Backend — Phase 1 (supports both old and new Supabase key styles)."""
import os

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="VMMS API", version="0.1.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()


def supabase_headers():
    """New-style keys (sb_publishable_...) use only the apikey header.
    Legacy keys (eyJ...) also send an Authorization bearer."""
    headers = {"apikey": SUPABASE_ANON_KEY}
    if SUPABASE_ANON_KEY.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {SUPABASE_ANON_KEY}"
    return headers


@app.get("/")
def root():
    return {"app": "VMMS", "phase": 1, "status": "running"}


@app.get("/api/v1/health")
async def health():
    detail = {}
    detail["url_set"] = bool(SUPABASE_URL)
    detail["url_looks_right"] = SUPABASE_URL.startswith("https://") and SUPABASE_URL.endswith(".supabase.co")
    detail["key_set"] = bool(SUPABASE_ANON_KEY)
    detail["key_prefix"] = SUPABASE_ANON_KEY[:15] if SUPABASE_ANON_KEY else ""

    db_status = "not_configured"
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{SUPABASE_URL}/rest/v1/", headers=supabase_headers())
                detail["supabase_status_code"] = r.status_code
                db_status = "connected" if r.status_code in (200, 404, 406) else "error"
        except Exception as e:
            detail["exception"] = type(e).__name__
            db_status = "unreachable"
    return {"server": "ok", "database": db_status, "diag": detail}
