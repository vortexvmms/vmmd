"""
VMMS Backend — Phase 1
FastAPI application with a single health-check endpoint.
Confirms: (1) server is running, (2) database connection works.
"""
import os

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="VMMS API",
    description="Vortex Manpower Management System — internal API",
    version="0.1.0",
)

# Allow the frontend (GitHub Pages) to call this API.
# In Phase 3 this will be restricted to the exact frontend address.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


@app.get("/")
def root():
    return {"app": "VMMS", "phase": 1, "status": "running"}


@app.get("/api/v1/health")
async def health():
    """Health check: server status + database reachability."""
    db_status = "not_configured"
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{SUPABASE_URL}/rest/v1/",
                    headers={"apikey": SUPABASE_ANON_KEY},
                )
                db_status = "connected" if r.status_code in (200, 404) else "error"
        except Exception:
            db_status = "unreachable"
    return {"server": "ok", "database": db_status}
