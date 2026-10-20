"""Scoped worker cards and certificates; new originals use immutable private storage."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal
from urllib.parse import quote, unquote, urlsplit
from uuid import UUID, uuid4

import struct

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ...core.roles import ATTENDANCE_ROLES

MAX_FILE = 20 * 1024 * 1024
TABLES = {'cards': 'worker_cards', 'certificates': 'worker_certificates'}


@dataclass(frozen=True)
class WorkerDocumentsContext:
    get_current_user: Callable
    shared_client: Callable
    rest_url: str
    supabase_headers: Callable
    audit: Callable
    r2_public_base: str
    r2_presign_get: Callable | None = None


class Details(BaseModel):
    model_config = ConfigDict(extra='forbid')
    updated_at: str
    category: Literal['course', 'work_permit', 'visit_pass', 'other'] = 'course'
    label: str | None = Field(default=None, max_length=200)
    institute: str | None = Field(default=None, max_length=200)
    cert_no: str | None = Field(default=None, max_length=200)
    issued_date: date | None = None
    expiry_date: date | None = None
    title: str | None = Field(default=None, max_length=200)


def image_dimensions(data, mime):
    # Inspect dimensions before decoding compressed pixels into memory.
    if mime == 'image/png':
        if len(data) < 33 or data[12:16] != b'IHDR':
            raise ValueError('Missing PNG header')
        return struct.unpack('>II', data[16:24])
    index = 2
    while index < len(data):
        if data[index] != 0xff:
            raise ValueError('Invalid JPEG marker')
        while index < len(data) and data[index] == 0xff:
            index += 1
        marker = data[index]; index += 1
        if marker in (0xd9, 0xda):
            break
        if marker == 0x01 or 0xd0 <= marker <= 0xd7:
            continue
        length = int.from_bytes(data[index:index+2], 'big')
        if length < 2 or index + length > len(data):
            raise ValueError('Invalid JPEG segment')
        if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf):
            if length < 8:
                raise ValueError('Invalid JPEG frame')
            height, width = struct.unpack('>HH', data[index+3:index+7])
            return width, height
        index += length
    raise ValueError('Missing JPEG dimensions')


def file_type(data):
    mime = ('application/pdf' if data.startswith(b'%PDF-') else
            'image/jpeg' if data.startswith(b'\xff\xd8\xff') else
            'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else None)
    if not mime:
        raise HTTPException(415, 'Use a PDF, JPG or PNG file')
    import fitz
    try:
        if mime != 'application/pdf':
            width, height = image_dimensions(data, mime)
            if not 1 <= width * height <= 25000000:
                raise ValueError('Invalid or oversized image')
            image = fitz.Pixmap(data)
            del image
        with fitz.open(stream=data, filetype={'application/pdf': 'pdf', 'image/jpeg': 'jpeg', 'image/png': 'png'}[mime]) as doc:
            if doc.is_encrypted or not 1 <= doc.page_count <= 150:
                raise ValueError('Unreadable document')
    except Exception:
        raise HTTPException(400, 'File could not be read. Use an unlocked PDF with at most 150 pages, or a valid JPG / PNG up to 25 megapixels')
    return mime


def legacy_url(path, r2_base):
    """Only historical card hosts/paths; no redirects or user credentials forwarded."""
    url = urlsplit(path)
    r2 = urlsplit(r2_base)
    return (url.scheme == 'https' and not url.username and not url.password and not url.query and not url.fragment and
            ((url.netloc == r2.netloc and bool(r2.netloc) and url.path.startswith(('/worker-cards/', '/worker-certificates/'))) or
             (url.netloc == 'lqnbdemtgkermhaqfboh.supabase.co' and url.path.startswith('/storage/v1/object/public/dpr-photos/worker-cards/'))))


def build_worker_documents_router(ctx: WorkerDocumentsContext):
    router = APIRouter(prefix='/api/v1/worker-documents', tags=['worker-documents'])
    storage = ctx.rest_url.removesuffix('/rest/v1') + '/storage/v1'

    def require(user):
        if user['role'] not in ATTENDANCE_ROLES:
            raise HTTPException(403, 'Worker cards are not available for this role')

    def table(kind):
        if kind not in TABLES:
            raise HTTPException(404, 'Unknown document type')
        return TABLES[kind]

    async def db(user, resource, method='GET', params=None, payload=None):
        async with ctx.shared_client() as client:
            r = await client.request(method, f'{ctx.rest_url}/{resource}', params=params, json=payload,
                headers={**ctx.supabase_headers(user['token']), 'Prefer': 'return=representation'})
        if not r.is_success:
            raise HTTPException(403 if r.status_code in (401, 403) else 503, 'Worker documents could not be accessed. Refresh and try again.')
        return r.json() if r.content else []

    async def accessible(user, worker):
        if not await db(user, 'rpc/worker_documents_can_access', 'POST', payload={'p_worker': str(worker)}):
            raise HTTPException(404, 'Worker is not available in your current site allocations')

    async def row(user, kind, record):
        rows = await db(user, table(kind), params={'id': f'eq.{record}', 'limit': '1'})
        if not rows:
            raise HTTPException(404, 'Document not found or outside your current site allocations')
        return rows[0]

    @router.get('/workers')
    async def workers(search: str = '', offset: int = 0, user: dict = Depends(ctx.get_current_user)):
        require(user)
        if len(search) > 200 or not 0 <= offset <= 100000:
            raise HTTPException(400, 'Invalid worker search')
        return await db(user, 'rpc/worker_documents_workers', 'POST', payload={'p_search': search, 'p_offset': offset})

    @router.get('/{kind}')
    async def listing(kind: str, worker_id: UUID, user: dict = Depends(ctx.get_current_user)):
        require(user); await accessible(user, worker_id)
        result = []
        for offset in range(0, 10000, 1000):
            rows = await db(user, table(kind), params={'worker_id': f'eq.{worker_id}', 'order': 'created_at.asc,id.asc', 'limit': '1000', 'offset': str(offset)})
            result.extend(rows)
            if len(rows) < 1000:
                return result
        raise HTTPException(413, 'Too many documents for this worker. Contact management.')

    @router.patch('/{kind}/{record_id}')
    async def edit(kind: str, record_id: UUID, body: Details, user: dict = Depends(ctx.get_current_user)):
        require(user); old = await row(user, kind, record_id)
        if body.issued_date and body.expiry_date and body.expiry_date < body.issued_date:
            raise HTTPException(422, 'Expiry date must be on or after the issue date')
        fields = ('category', 'label', 'institute', 'cert_no', 'issued_date', 'expiry_date') if kind == 'cards' else ('title',)
        payload = {key: value for key, value in body.model_dump(mode='json').items() if key in fields}
        rows = await db(user, table(kind), 'PATCH', params={'id': f'eq.{record_id}', 'updated_at': f'eq.{body.updated_at}'}, payload=payload)
        if not rows:
            raise HTTPException(409, 'This document changed. Refresh before editing again.')
        async with ctx.shared_client() as client:
            await ctx.audit(client, user, 'update', table(kind), str(record_id), old, rows[0])
        return rows[0]

    @router.post('/{kind}/upload', status_code=201)
    async def upload(kind: str, worker_id: UUID, request: Request, record_id: UUID | None = None,
                     side: Literal['front', 'back'] = 'front', updated_at: str | None = None,
                     user: dict = Depends(ctx.get_current_user)):
        require(user); table(kind); await accessible(user, worker_id)
        old = await row(user, kind, record_id) if record_id else None
        if old and old['worker_id'] != str(worker_id):
            raise HTTPException(409, 'Document belongs to a different worker')
        if old and not updated_at:
            raise HTTPException(422, 'Refresh the document before replacing a file')
        if side == 'back' and (not old or kind != 'cards'):
            raise HTTPException(422, 'Save the front of a card before adding its back')
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_FILE:
                raise HTTPException(413, 'Files must be 20 MB or smaller')
            data.extend(chunk)
        mime = file_type(bytes(data))
        if kind == 'cards' and mime == 'application/pdf':
            raise HTTPException(415, 'Card sides must be JPG or PNG. Upload PDFs under Certificates.')
        extension = {'image/jpeg': 'jpg', 'image/png': 'png', 'application/pdf': 'pdf'}[mime]
        key = f'{worker_id}/{uuid4()}.{extension}'
        async with ctx.shared_client() as client:
            r = await client.post(f'{storage}/object/worker-cards/{key}', headers={**ctx.supabase_headers(user['token']), 'Content-Type': mime, 'x-upsert': 'false'}, content=bytes(data))
            if not r.is_success:
                raise HTTPException(503, 'Private storage upload failed. Please try again.')
        field = 'file_path' if kind == 'certificates' else 'back_image_path' if side == 'back' else 'image_path'
        payload = {field: key}
        if kind == 'certificates':
            payload['file_type'] = 'pdf' if mime == 'application/pdf' else 'image'
        if old:
            rows = await db(user, table(kind), 'PATCH', params={'id': f'eq.{record_id}', 'updated_at': f'eq.{updated_at}'}, payload=payload)
        else:
            payload.update(worker_id=str(worker_id), uploaded_by=user['user_id'])
            rows = await db(user, table(kind), 'POST', payload=payload)
        # Keep immutable originals on any ambiguous save; never auto-delete a potentially referenced upload.
        if not rows:
            raise HTTPException(409, 'This document changed. Refresh before replacing its file.')
        async with ctx.shared_client() as client:
            await ctx.audit(client, user, 'update' if old else 'create', table(kind), str(rows[0]['id']), old, rows[0])
        return rows[0]

    @router.get('/{kind}/{record_id}/file')
    async def download(kind: str, record_id: UUID, side: Literal['front', 'back'] = 'front', user: dict = Depends(ctx.get_current_user)):
        require(user); record = await row(user, kind, record_id)
        path = record.get('file_path' if kind == 'certificates' else 'back_image_path' if side == 'back' else 'image_path')
        if not path:
            raise HTTPException(404, 'No file attached on this side')
        if path.startswith(record['worker_id'] + '/') and '..' not in path:
            url = f'{storage}/object/authenticated/worker-cards/{quote(path, safe="/")}'
            headers = ctx.supabase_headers(user['token'])
        elif legacy_url(path, ctx.r2_public_base):
            url, headers = path, {}
            if urlsplit(path).netloc == urlsplit(ctx.r2_public_base).netloc and ctx.r2_presign_get:
                key = unquote(urlsplit(path).path).lstrip('/')
                if '..' in key.split('/'):
                    raise HTTPException(422, 'Invalid historical file location')
                url = ctx.r2_presign_get(key)
        else:
            raise HTTPException(422, 'This historical file location is not supported. Upload a replacement original.')
        data = bytearray()
        try:
            async with ctx.shared_client() as client:
                async with client.stream('GET', url, headers=headers, follow_redirects=False) as r:
                    if r.status_code != 200:
                        raise HTTPException(502, 'Original file is unavailable. The saved record is retained; upload a replacement if available.')
                    async for chunk in r.aiter_bytes():
                        if len(data) + len(chunk) > MAX_FILE:
                            raise HTTPException(413, 'Original file exceeds 20 MB')
                        data.extend(chunk)
        except httpx.RequestError:
            raise HTTPException(502, 'Original file is temporarily unavailable. The saved record is retained.')
        return Response(bytes(data), media_type=file_type(bytes(data)), headers={'Cache-Control': 'no-store', 'Content-Disposition': 'inline'})
    return router
