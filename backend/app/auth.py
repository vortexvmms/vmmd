"""Authentication, profile resolution and short-lived identity caching."""
import time

from fastapi import HTTPException, Request

from .db import shared_client, supabase_headers
from .settings import REST, SUPABASE_URL

_USER_CACHE: dict[str, tuple[float, dict]] = {}
_USER_CACHE_TTL = 600


def _cache_get(token: str):
    hit = _USER_CACHE.get(token)
    if hit and hit[0] > time.time():
        user = dict(hit[1])
        user["token"] = token
        return user
    return None


def cache_user(token: str, user: dict):
    _USER_CACHE[token] = (
        time.time() + _USER_CACHE_TTL,
        {key: value for key, value in user.items() if key != "token"},
    )
    if len(_USER_CACHE) > 400:
        now = time.time()
        for key in [key for key, (expiry, _) in _USER_CACHE.items() if expiry <= now]:
            _USER_CACHE.pop(key, None)


def invalidate_users(user_ids) -> None:
    wanted = {str(value) for value in (user_ids or []) if value}
    for token, (_, profile) in list(_USER_CACHE.items()):
        if str(profile.get("user_id")) in wanted:
            _USER_CACHE.pop(token, None)


async def get_current_user(request: Request) -> dict:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not signed in")
    token = authorization.removeprefix("Bearer ").strip()
    cached = _cache_get(token)
    if cached:
        return cached

    async with shared_client() as client:
        response = await client.get(
            f"{SUPABASE_URL}/auth/v1/user", headers=supabase_headers(token)
        )
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Session expired — please log in again")
        auth_user = response.json()
        auth_uid = auth_user.get("id")
        profile_response = await client.get(
            f"{REST}/users",
            params={
                "auth_uid": f"eq.{auth_uid}",
                "select": "id,name,role,status,menu,dpr_reminders,dpr_reminder_sites",
            },
            headers=supabase_headers(token),
        )
        if profile_response.status_code != 200:
            profile_response = await client.get(
                f"{REST}/users",
                params={"auth_uid": f"eq.{auth_uid}", "select": "id,name,role,status"},
                headers=supabase_headers(token),
            )
        profiles = profile_response.json() if profile_response.status_code == 200 else []
        if not profiles:
            raise HTTPException(status_code=403, detail="No VCMS profile is linked to this login")
        profile = profiles[0]
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
    cache_user(token, user)
    return user

