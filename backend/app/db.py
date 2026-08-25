"""Supabase HTTP transport with shared connection pooling."""
from __future__ import annotations

import httpx
from fastapi import HTTPException

from .settings import SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY

_HTTP = httpx.AsyncClient(
    timeout=20,
    limits=httpx.Limits(
        max_keepalive_connections=20,
        max_connections=40,
        keepalive_expiry=120,
    ),
)


class _KeepOpen:
    def __init__(self, client):
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, *_exc):
        return False


def shared_client(*_args, **_kwargs):
    return _KeepOpen(_HTTP)


async def close_http_client():
    await _HTTP.aclose()


def supabase_headers(user_token: str | None = None) -> dict:
    headers = {"apikey": SUPABASE_ANON_KEY}
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
    elif SUPABASE_ANON_KEY.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {SUPABASE_ANON_KEY}"
    return headers


def service_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def require_service():
    if not SUPABASE_SERVICE_KEY:
        raise HTTPException(
            status_code=501,
            detail="Administrator service is not configured. Contact the system administrator.",
        )
