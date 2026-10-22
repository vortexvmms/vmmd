"""Private worker portraits. Browser sends a cropped JPEG; server validates and re-encodes."""
from __future__ import annotations
from uuid import UUID, uuid4
from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from ..worker_documents.router import WorkerDocumentsContext
from ...core.roles import ATTENDANCE_ROLES, FULL_ROLES

MAX_FILE = 2 * 1024 * 1024


def portrait(data: bytes) -> bytes:
    try:
        with Image.open(BytesIO(data)) as im:
            if im.format not in ('JPEG', 'PNG', 'WEBP') or im.width * im.height > 16000000:
                raise ValueError('Invalid image')
            im = ImageOps.exif_transpose(im)
            im = ImageOps.fit(im.convert('RGB'), (480, 480))
            out = BytesIO()
            im.save(out, format='JPEG', quality=85, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(415, 'Use a valid JPG, PNG or WebP portrait up to 16 megapixels')


def build_worker_photos_router(ctx: WorkerDocumentsContext):
    router = APIRouter(prefix='/api/v1/worker-photos', tags=['worker-photos'])
    storage = ctx.rest_url.removesuffix('/rest/v1') + '/storage/v1'

    async def worker(user, worker_id, manage=False):
        if user['role'] not in (FULL_ROLES if manage else ATTENDANCE_ROLES):
            raise HTTPException(403, 'Only management can change worker photos' if manage else 'Worker photos are unavailable for this role')
        async with ctx.shared_client() as client:
            if not manage:
                access = await client.post(f'{ctx.rest_url}/rpc/worker_documents_can_access',
                    json={'p_worker': str(worker_id)}, headers=ctx.supabase_headers(user['token']))
                if not access.is_success or access.json() is not True:
                    raise HTTPException(404, 'Worker photo is outside your current site allocations')
            r = await client.get(f'{ctx.rest_url}/workers', params={'id': f'eq.{worker_id}', 'select': 'id,photo_path,updated_at'}, headers=ctx.supabase_headers(user['token']))
        if not r.is_success:
            raise HTTPException(503, 'Could not load worker photo')
        rows = r.json()
        if not rows:
            raise HTTPException(404, 'Worker not found')
        return rows[0]

    async def attach(user, old, path):
        async with ctx.shared_client() as client:
            r = await client.patch(f'{ctx.rest_url}/workers',
                params={'id': f'eq.{old["id"]}', 'updated_at': f'eq.{old["updated_at"]}'},
                json={'photo_path': path}, headers={**ctx.supabase_headers(user['token']), 'Prefer': 'return=representation'})
            if not r.is_success:
                raise HTTPException(503, 'Photo could not be attached. Refresh before trying again.')
            rows = r.json()
            if not rows:
                raise HTTPException(409, 'Worker changed on another device. Refresh before trying again.')
            await ctx.audit(client, user, 'worker_photo', 'workers', str(old['id']), old, rows[0])
        return {'worker_id': old['id'], 'photo_path': rows[0].get('photo_path')}

    @router.post('/{worker_id}')
    async def upload(worker_id: UUID, request: Request, user: dict = Depends(ctx.get_current_user)):
        old = await worker(user, worker_id, manage=True)
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_FILE:
                raise HTTPException(413, 'Photo must be 2 MB or smaller')
            data.extend(chunk)
        raw = await run_in_threadpool(portrait, bytes(data))
        key = f'{worker_id}/{uuid4()}.jpg'
        async with ctx.shared_client() as client:
            r = await client.post(f'{storage}/object/worker-photos/{key}', content=raw,
                headers={**ctx.supabase_headers(user['token']), 'Content-Type': 'image/jpeg', 'x-upsert': 'false'})
        if not r.is_success:
            raise HTTPException(503, 'Photo upload failed. Please try again.')
        # Immutable keys preserve the previous photo if attaching this upload fails.
        return await attach(user, old, key)

    @router.delete('/{worker_id}')
    async def remove(worker_id: UUID, user: dict = Depends(ctx.get_current_user)):
        return await attach(user, await worker(user, worker_id, manage=True), None)

    @router.get('/{worker_id}')
    async def download(worker_id: UUID, user: dict = Depends(ctx.get_current_user)):
        row = await worker(user, worker_id)
        path = row.get('photo_path')
        if not path or not path.startswith(f'{worker_id}/') or '..' in path:
            raise HTTPException(404, 'No profile photo')
        async with ctx.shared_client() as client:
            r = await client.get(f'{storage}/object/authenticated/worker-photos/{path}', headers=ctx.supabase_headers(user['token']))
        if not r.is_success:
            raise HTTPException(404, 'Photo is unavailable')
        return Response(r.content, media_type='image/jpeg', headers={'Cache-Control': 'private, no-store'})
    return router
