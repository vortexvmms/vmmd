"""Private image storage shared by DPR and purchase requests."""
import re
import uuid
from urllib.parse import unquote, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..auth import get_current_user
from ..core.roles import ATTENDANCE_ROLES, SUPERVISOR_ROLES
from ..db import shared_client, supabase_headers
from ..settings import PRIVATE_IMAGES_R2_ENABLED, REST, SUPABASE_URL
from ..storage import private_image_url

router = APIRouter(prefix="/api/v1/report-images", tags=["report images"])
MARKER = "vcms-report-image:"
LEGACY_PREFIX = "/storage/v1/object/public/dpr-photos/"
SITE = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
PHOTO = r"[A-Za-z0-9_-]+\.(?:png|jpe?g|webp)"
KEY = re.compile(rf"(?:(?P<site>{SITE})/\d{{4}}-\d\d-\d\d/|signatures/(?P<signature_site>{SITE})/|pr/[A-Za-z0-9_-]+/){PHOTO}")


def image_key(reference: str):
    if reference.startswith(MARKER):
        return reference[len(MARKER):], None
    target = urlsplit(reference)
    allowed = {urlsplit(SUPABASE_URL).netloc, "lqnbdemtgkermhaqfboh.supabase.co"}
    if (target.scheme != "https" or target.netloc not in allowed or target.query
            or target.fragment or not target.path.startswith(LEGACY_PREFIX)):
        raise HTTPException(400, "Use a saved VCMS report image")
    return unquote(target.path[len(LEGACY_PREFIX):]), SUPABASE_URL + target.path


async def check_access(client, user, key):
    if user["role"] not in ATTENDANCE_ROLES:
        raise HTTPException(403, "Report images are unavailable for this role")
    match = KEY.fullmatch(key)
    if not match:
        raise HTTPException(400, "Invalid report image path")
    site = match["site"] or match["signature_site"]
    if site and user["role"] in SUPERVISOR_ROLES:
        allowed = await client.post(f"{REST}/rpc/my_site_ids", json={}, headers=supabase_headers(user["token"]))
        if not allowed.is_success:
            raise HTTPException(503, "Could not verify report image access")
        if site not in allowed.json():
            raise HTTPException(404, "Report image is outside your site allocations")


def image_mime(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.put("")
async def upload_image(request: Request, path: str, user: dict = Depends(get_current_user)):
    if not PRIVATE_IMAGES_R2_ENABLED:
        raise HTTPException(503, "Private report image storage is unavailable")
    async with shared_client() as client:
        await check_access(client, user, path)
        limit = (2 if path.startswith("signatures/") else 20) * 1024 * 1024
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > limit:
                raise HTTPException(413, "Report image exceeds the upload limit")
            data.extend(chunk)
        mime = image_mime(data)
        if not mime:
            raise HTTPException(415, "Use a JPEG, PNG or WebP image")
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime]
        key = f"{path.rsplit('/', 1)[0]}/{uuid.uuid4()}.{extension}"
        try:
            uploaded = await client.put(
                private_image_url("dpr-photos", key, "PUT"), content=bytes(data),
                headers={"Content-Type": mime, "Cache-Control": "private, no-store", "If-None-Match": "*"},
                follow_redirects=False,
            )
        except httpx.RequestError as error:
            raise HTTPException(502, "Report image upload failed") from error
        if not uploaded.is_success:
            raise HTTPException(502, "Report image upload failed")
    return {"reference": MARKER + key}


@router.get("")
async def read_image(ref: str, user: dict = Depends(get_current_user)):
    key, legacy = image_key(ref)
    async with shared_client() as client:
        await check_access(client, user, key)
        sources = []
        if PRIVATE_IMAGES_R2_ENABLED:
            sources.append(private_image_url("dpr-photos", key, "GET"))
        if legacy:
            sources.append(legacy)
        limit = (2 if key.startswith("signatures/") else 20) * 1024 * 1024
        for source in sources:
            try:
                async with client.stream("GET", source, follow_redirects=False) as image:
                    if image.status_code != 200:
                        continue
                    data = bytearray()
                    async for chunk in image.aiter_bytes():
                        if len(data) + len(chunk) > limit:
                            raise HTTPException(413, "Report image exceeds the download limit")
                        data.extend(chunk)
                    mime = image_mime(data)
                    if mime:
                        return Response(bytes(data), media_type=mime, headers={"Cache-Control": "private, no-store"})
            except httpx.RequestError:
                continue
    raise HTTPException(404, "Report image unavailable")
