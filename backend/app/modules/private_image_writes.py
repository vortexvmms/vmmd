"""Confirm a private R2 write before a card record can reference its image."""
import httpx
from fastapi import HTTPException

from ..db import require_service, service_headers


async def store_card_image(client, sign, rest_url, uploader, bucket, key, mime, data, *, retry=False):
    require_service()
    try:
        upload = await client.put(
            sign(bucket, key, "PUT"), content=data, follow_redirects=False,
            headers={"Content-Type": mime, "Cache-Control": "private, no-store", "If-None-Match": "*"},
        )
        if retry and upload.status_code == 412:
            previous = await client.get(sign(bucket, key, "GET"), follow_redirects=False)
            if not previous.is_success or previous.content != data:
                raise HTTPException(409, "A different image already uses this reference")
        elif not upload.is_success:
            raise HTTPException(503, "Private image upload failed")
        receipt = await client.post(
            f"{rest_url}/private_r2_image_receipts", params={"on_conflict": "bucket_id,object_key,uploader"},
            headers={**service_headers(), "Prefer": "resolution=ignore-duplicates,return=minimal"},
            json={"bucket_id": bucket, "object_key": key, "uploader": uploader},
        )
    except httpx.RequestError as error:
        raise HTTPException(503, "Private image upload could not be confirmed") from error
    if not receipt.is_success:
        raise HTTPException(503, "Private image upload could not be confirmed")


async def clear_card_image_receipt(client, rest_url, bucket, key):
    require_service()
    receipt = await client.delete(
        f"{rest_url}/private_r2_image_receipts",
        params={"bucket_id": f"eq.{bucket}", "object_key": f"eq.{key}"},
        headers=service_headers(),
    )
    if not receipt.is_success:
        raise HTTPException(503, "Private image receipt could not be removed")
