from datetime import date
from uuid import UUID, uuid4

import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from ...auth import get_current_user
from ...db import shared_client, supabase_headers
from ...settings import PRIVATE_IMAGES_R2_ENABLED, REST
from ...storage import private_image_url
from ..report_images import image_mime

router = APIRouter(prefix="/api/v1/store", tags=["store"])
ARCHIVE_ROLES = {"admin", "general_manager", "operation_manager"}


class AssetDetails(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(max_length=30)
    brand: str = Field(default="", max_length=70)
    model: str = Field(default="", max_length=70)
    serial_number: str = Field(default="", max_length=70)
    registration_number: str = Field(default="", max_length=35)
    equipment_type: str = Field(default="", max_length=70)
    ownership: str = Field(default="", max_length=40)
    lm_reference: str = Field(default="", max_length=60)
    meter_reading: str = Field(default="", max_length=40)
    condition: str = Field(default="Unverified", max_length=30)
    notes: str = Field(default="", max_length=500)
    purchase_date: date | None = None
    last_maintenance: date | None = None
    last_calibration: date | None = None
    last_repair: date | None = None


class AssetCreate(BaseModel):
    id: UUID
    site: UUID | None
    quantity: int = Field(ge=1, le=9999)
    asset: AssetDetails


class MovementCreate(BaseModel):
    id: UUID
    asset: UUID
    from_site: UUID | None
    to_site: UUID | None
    quantity: int = Field(ge=1, le=9999)
    date: date
    handed_over: str = Field(default="", max_length=100)
    received: UUID
    requested: UUID | None = None
    notes: str = Field(default="", max_length=500)


async def call_store(function: str, payload: dict, user: dict):
    try:
        async with shared_client() as client:
            response = await client.post(
                f"{REST}/rpc/{function}", json=payload, headers=supabase_headers(user["token"]),
            )
    except httpx.RequestError as error:
        raise HTTPException(503, detail="Store data is temporarily unavailable.") from error
    if response.is_success:
        return response.json()
    try:
        failure = response.json()
    except ValueError:
        failure = {}
    code = failure.get("code")
    if code == "42501":
        raise HTTPException(403, detail=failure.get("message", "Store access denied."))
    if code == "23505":
        raise HTTPException(409, detail="That code, name or submission reference already exists.")
    if code == "22023":
        raise HTTPException(422, detail=failure.get("message", "Check the submitted values."))
    if code in {"23502", "23514"}:
        raise HTTPException(422, detail="Check the equipment description, asset code and category.")
    raise HTTPException(503, detail="Store data is temporarily unavailable.")


@router.get("/register")
async def register(user: dict = Depends(get_current_user)):
    data = await call_store("store_register", {}, user)
    extras = await call_store("store_extras", {}, user)
    return {
        **data, **extras,
        "photos_enabled": PRIVATE_IMAGES_R2_ENABLED,
        "can_archive": user["role"] in ARCHIVE_ROLES,
    }


@router.get("/movements")
async def movements(
    date_from: date, date_to: date, page: int = Query(0, ge=0, le=1000),
    location: str = Query("", max_length=40), movement_type: str = Query("", max_length=30),
    search: str = Query("", max_length=150),
    user: dict = Depends(get_current_user),
):
    rows = await call_store(
        "store_movement_log",
        {"p_from": date_from.isoformat(), "p_to": date_to.isoformat(), "p_page": page,
         "p_location": location, "p_type": movement_type, "p_search": search.strip()},
        user,
    )
    return {"rows": rows[:50], "has_more": len(rows) > 50}


@router.post("/assets", status_code=201)
async def add_asset(item: AssetCreate, user: dict = Depends(get_current_user)):
    payload = {f"p_{field}": value for field, value in item.model_dump(mode="json").items()}
    return {"id": await call_store("store_add_asset", payload, user)}


@router.post("/assets/{asset_id}/archive")
async def archive_asset(asset_id: UUID, user: dict = Depends(get_current_user)):
    return {"id": await call_store("store_archive_asset", {"p_id": str(asset_id)}, user)}


@router.post("/movements", status_code=201)
async def add_movement(item: MovementCreate, user: dict = Depends(get_current_user)):
    fields = item.model_dump(mode="json")
    fields["from"] = fields.pop("from_site")
    fields["to"] = fields.pop("to_site")
    payload = {f"p_{field}": value for field, value in fields.items()}
    return {"id": await call_store("store_move_asset", payload, user)}


class DriverSave(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=100)
    active: bool = True


class ReminderSave(BaseModel):
    id: UUID
    asset: UUID
    kind: str = Field(min_length=1, max_length=100)
    due: date
    assignee: UUID | None = None
    status: str = Field(default="Open", max_length=30)
    reference: str = Field(default="", max_length=300)


class ReminderCompletion(BaseModel):
    completion: UUID
    done: date
    next: date | None = None
    reference: str = Field(default="", max_length=300)


@router.post("/drivers")
async def save_driver(item: DriverSave, user: dict = Depends(get_current_user)):
    payload = {f"p_{field}": value for field, value in item.model_dump(mode="json").items()}
    return {"id": await call_store("store_save_driver", payload, user)}


@router.post("/reminders")
async def save_reminder(item: ReminderSave, user: dict = Depends(get_current_user)):
    payload = {f"p_{field}": value for field, value in item.model_dump(mode="json").items()}
    return {"id": await call_store("store_save_reminder", payload, user)}


@router.post("/reminders/{reminder_id}/complete")
async def complete_reminder(reminder_id: UUID, item: ReminderCompletion, user: dict = Depends(get_current_user)):
    payload = {f"p_{field}": value for field, value in item.model_dump(mode="json").items()}
    return {"id": await call_store("store_complete_reminder", {"p_id": str(reminder_id), **payload}, user)}


PHOTO_LIMIT = 5 * 1024 * 1024


def photo_target(asset: UUID | None, movement: UUID | None):
    if (asset is None) == (movement is None):
        raise HTTPException(422, detail="Choose one asset or movement.")
    return {"p_asset": str(asset) if asset else None, "p_movement": str(movement) if movement else None}


@router.get("/photos")
async def list_photos(asset: UUID | None = None, movement: UUID | None = None, user: dict = Depends(get_current_user)):
    return await call_store("store_photo_list", photo_target(asset, movement), user)


@router.put("/photos/{photo_id}", status_code=201)
async def upload_photo(
    photo_id: UUID, request: Request, asset: UUID | None = None, movement: UUID | None = None,
    user: dict = Depends(get_current_user),
):
    if not PRIVATE_IMAGES_R2_ENABLED:
        raise HTTPException(503, detail="Private photo storage is unavailable.")
    target = photo_target(asset, movement)
    if movement and user["role"] == "site_sup":
        raise HTTPException(403, detail="Movement photos are uploaded by logistics or coordinators.")
    existing = await call_store("store_photo_list", target, user)
    if any(row["id"] == str(photo_id) for row in existing):
        return {"id": str(photo_id)}
    if len(existing) >= 4:
        raise HTTPException(422, detail="Each record can have up to four photos.")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > PHOTO_LIMIT:
            raise HTTPException(413, detail="Use an image up to 5 MB.")
        data.extend(chunk)
    mime = image_mime(data)
    if not mime:
        raise HTTPException(415, detail="Use a JPEG, PNG or WebP image.")
    key = f"assets/{asset}/{photo_id}" if asset else f"movements/{movement}/{photo_id}"
    async with shared_client() as client:
        try:
            response = await client.put(
                private_image_url("store", key, "PUT"), content=bytes(data),
                headers={"Content-Type": mime, "Cache-Control": "private, no-store", "If-None-Match": "*"},
                follow_redirects=False,
            )
        except httpx.RequestError as error:
            raise HTTPException(502, detail="Photo upload failed. Retry this photo.") from error
        if not response.is_success and response.status_code != 412:
            raise HTTPException(502, detail="Photo upload failed. Retry this photo.")
    try:
        return {"id": await call_store("store_photo_attach", {"p_id": str(photo_id), **target, "p_mime": mime}, user)}
    except HTTPException as error:
        if error.status_code == 409:
            latest = await call_store("store_photo_list", target, user)
            if any(row["id"] == str(photo_id) for row in latest):
                return {"id": str(photo_id)}
        # A timeout can occur after the receipt commits. Keep the object for a retry.
        if response.is_success and error.status_code in {403, 422}:
            try:
                async with shared_client() as client:
                    await client.delete(private_image_url("store", key, "DELETE"), follow_redirects=False)
            except httpx.RequestError:
                pass
        raise


@router.get("/photos/{photo_id}")
async def get_photo(photo_id: UUID, user: dict = Depends(get_current_user)):
    if not PRIVATE_IMAGES_R2_ENABLED:
        raise HTTPException(503, detail="Private photo storage is unavailable.")
    record = await call_store("store_photo_read", {"p_id": str(photo_id)}, user)
    data = bytearray()
    try:
        async with shared_client() as client:
            async with client.stream("GET", private_image_url("store", record["key"], "GET"), follow_redirects=False) as photo:
                if photo.status_code != 200:
                    raise HTTPException(404, detail="Photo not found.")
                async for chunk in photo.aiter_bytes():
                    if len(data) + len(chunk) > PHOTO_LIMIT:
                        raise HTTPException(413, detail="Photo exceeds the download limit.")
                    data.extend(chunk)
    except httpx.RequestError as error:
        raise HTTPException(502, detail="Photo could not be loaded.") from error
    if image_mime(data) != record["mime"]:
        raise HTTPException(415, detail="Photo format does not match the saved record.")
    return Response(bytes(data), media_type=record["mime"], headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


@router.put("/assets/{asset_id}")
async def edit_asset(asset_id: UUID, asset: AssetDetails, user: dict = Depends(get_current_user)):
    params = {"p_id": str(asset_id), "p_asset": asset.model_dump(mode="json")}
    return {"id": await call_store("store_edit_asset", params, user)}


class CountConfirmation(BaseModel):
    id: UUID
    site: UUID | None
    quantities: dict[UUID, int]


@router.post("/counts", status_code=201)
async def confirm_count(count: CountConfirmation, user: dict = Depends(get_current_user)):
    params = {f"p_{field}": value for field, value in count.model_dump(mode="json").items()}
    return await call_store("store_confirm_count", params, user)
