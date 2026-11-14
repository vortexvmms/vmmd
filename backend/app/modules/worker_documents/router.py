"""Scoped worker cards and certificates; new originals use immutable private storage."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal
from urllib.parse import quote, unquote, urlsplit
from uuid import UUID, uuid4

import hashlib
import struct
import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from ...core.roles import ATTENDANCE_ROLES
from . import masking
from ..private_image_writes import store_card_image, clear_card_image_receipt

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
    r2_presign_delete: Callable | None = None
    private_image_url: Callable | None = None


class Details(BaseModel):
    model_config = ConfigDict(extra='forbid')
    updated_at: str
    category: Literal['course', 'work_permit', 'visit_pass', 'other'] = 'course'
    label: str | None = Field(default=None, max_length=200)
    institute: str | None = Field(default=None, max_length=200)
    cert_no: str | None = Field(default=None, max_length=200)
    issued_date: date | None = None
    expiry_date: date | None = None
    no_expiry: bool | None = None
    title: str | None = Field(default=None, max_length=200)


class DeleteCard(BaseModel):
    model_config = ConfigDict(extra='forbid')
    updated_at: str
    confirmation: Literal['DELETE']


class ConfirmCleanup(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmation: Literal['DELETE']


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


def legacy_url(path, r2_base, supabase_host=None):
    """Only historical card hosts/paths; no redirects or user credentials forwarded."""
    url = urlsplit(path)
    r2 = urlsplit(r2_base)
    return (url.scheme == 'https' and not url.username and not url.password and not url.query and not url.fragment and
            ((url.netloc == r2.netloc and bool(r2.netloc) and url.path.startswith(('/worker-cards/', '/worker-certificates/'))) or
             (url.netloc in ('lqnbdemtgkermhaqfboh.supabase.co', supabase_host) and url.path.startswith('/storage/v1/object/public/dpr-photos/worker-cards/'))))


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

    def require_delete(user):
        if user['role'] not in ('admin', 'hr_assistant'):
            raise HTTPException(403, 'Only Admin and HR can permanently delete cards')

    async def delete_rpc(user, resource, payload):
        async with ctx.shared_client() as client:
            r = await client.post(f'{ctx.rest_url}/rpc/{resource}', json=payload,
                                 headers=ctx.supabase_headers(user['token']))
        if not r.is_success:
            try:
                code = r.json().get('code')
            except ValueError:
                code = None
            status = 409 if code == '40001' else 404 if code == 'P0002' else 403 if r.status_code in (401, 403) else 503
            message = ('This card changed. Refresh before deleting it.' if status == 409 else
                       'Card or deletion receipt not found.' if status == 404 else
                       'Card deletion could not finish. Refresh and try again.')
            raise HTTPException(status, message)
        result = r.json()
        # PostgREST can represent a composite result as a one-row array.
        if isinstance(result, list):
            if len(result) != 1:
                raise HTTPException(503, 'Deletion receipt could not be read. Refresh and try again.')
            result = result[0]
        return result

    async def cleanup_card(user, receipt):
        # The receipt commits atomically with removal; failed files stay queued for retry.
        for path in list(receipt['pending_paths']):
            try:
                worker = receipt['worker_id']
                if re.fullmatch(re.escape(worker) + r'/[0-9a-f-]{36}\.(jpg|png|pdf)', path):
                    bucket, key = 'worker-cards', path
                else:
                    url = urlsplit(path)
                    if url.query or url.fragment or '%' in path or '..' in url.path.split('/'):
                        raise ValueError('Unsafe file location')
                    if url.scheme == 'https' and url.netloc in ('lqnbdemtgkermhaqfboh.supabase.co', urlsplit(ctx.rest_url).netloc) and url.path.startswith('/storage/v1/object/public/dpr-photos/worker-cards/'+worker+'/'):
                        bucket, key = 'dpr-photos', url.path.removeprefix('/storage/v1/object/public/dpr-photos/')
                    elif url.scheme == 'https' and url.netloc == urlsplit(ctx.r2_public_base).netloc and re.fullmatch('/worker-cards/'+re.escape(worker)+r'/[A-Za-z0-9_.-]+',url.path):
                        if not ctx.r2_presign_delete:
                            raise ValueError('R2 cleanup is not configured')
                        async with ctx.shared_client() as client:
                            removed = await client.delete(ctx.r2_presign_delete(url.path.lstrip('/')), follow_redirects=False)
                        if not removed.is_success:
                            raise ValueError('R2 cleanup failed')
                        bucket = None
                    else:
                        raise ValueError('Unsupported historical location')
                if bucket:
                    async with ctx.shared_client() as client:
                        if ctx.private_image_url and not key.lower().endswith('.pdf'):
                            if bucket == 'worker-cards':
                                await clear_card_image_receipt(client, ctx.rest_url, bucket, key)
                            deleted = await client.delete(ctx.private_image_url(bucket, key, 'DELETE'), follow_redirects=False)
                            if not deleted.is_success and deleted.status_code != 404:
                                raise ValueError('Private R2 cleanup failed')
                        removed = await client.request('DELETE',f'{storage}/object/{bucket}',
                            headers=ctx.supabase_headers(user['token']),json={'prefixes':[key]})
                    if not removed.is_success:
                        raise ValueError('Private storage cleanup failed')
                receipt = await delete_rpc(user,'worker_card_cleanup_done',{'p_id':receipt['record_id'],'p_path':path})
            except (httpx.RequestError, ValueError, RuntimeError, HTTPException):
                # Never return secrets, signed URLs or paths in a failure response.
                continue
        return {'deleted':True,'record_id':receipt['record_id'],
                'cleanup_pending':bool(receipt['pending_paths']),
                'pending_files':len(receipt['pending_paths']),
                'retained_shared':receipt['retained_shared']}

    @router.delete('/cards/{record_id}')
    async def delete_card(record_id: UUID, body: DeleteCard, user: dict = Depends(ctx.get_current_user)):
        require_delete(user)
        receipt = await delete_rpc(user,'worker_card_delete',{'p_id':str(record_id),
            'p_updated_at':body.updated_at,'p_confirmation':body.confirmation})
        return await cleanup_card(user,receipt)

    @router.get('/card-deletions/pending')
    async def pending_deletions(worker_id: UUID, user: dict = Depends(ctx.get_current_user)):
        require_delete(user)
        return await db(user,'worker_card_deletions',params={'worker_id':f'eq.{worker_id}',
            'completed_at':'is.null','select':'record_id,title,deleted_at','order':'deleted_at.asc'})

    @router.post('/card-deletions/{record_id}/retry')
    async def retry_deletion(record_id: UUID, body: ConfirmCleanup, user: dict = Depends(ctx.get_current_user)):
        require_delete(user)
        rows = await db(user,'worker_card_deletions',params={'record_id':f'eq.{record_id}','limit':'1'})
        if not rows:
            raise HTTPException(404,'Deletion receipt not found')
        return await cleanup_card(user,rows[0])

    async def read_file(request):
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_FILE:
                raise HTTPException(413, 'Files must be 20 MB or smaller')
            data.extend(chunk)
        raw = bytes(data)
        return raw, file_type(raw)

    @router.post('/mask-preview')
    async def mask_preview(worker_id: UUID, request: Request, page: int = 0,
                           user: dict = Depends(ctx.get_current_user)):
        require(user); await accessible(user, worker_id)
        data, mime = await read_file(request)
        result = await run_in_threadpool(masking.process, masking.prepare, data, mime, page)
        return Response(json.dumps(result), media_type='application/json', headers={'Cache-Control': 'no-store'})

    @router.get('/workers')
    async def workers(search: str = '', offset: int = 0, user: dict = Depends(ctx.get_current_user)):
        """Return scoped workers with a masked FIN suffix for card printing."""
        require(user)
        if len(search) > 200 or not 0 <= offset <= 100000:
            raise HTTPException(400, 'Invalid worker search')
        rows = await db(user, 'rpc/worker_documents_workers', 'POST', payload={'p_search': search, 'p_offset': offset})
        if not rows:
            return []
        # Query only workers already authorised by the scoped directory RPC.
        ids = ','.join(str(UUID(r['id'])) for r in rows)
        identities = await db(user, 'workers', params={'select': 'id,fin', 'id': f'in.({ids})'})
        suffixes = {}
        for identity in identities:
            value = re.sub(r'[^A-Z0-9]', '', str(identity.get('fin') or '').upper())
            suffixes[identity['id']] = value[-4:] if len(value) >= 4 else None
        return [{**r, 'fin_last4': suffixes.get(r['id'])} for r in rows]

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
        if body.no_expiry and body.expiry_date:
            raise HTTPException(422, 'A card marked No expiry cannot have an expiry date')
        if body.issued_date and body.expiry_date and body.expiry_date < body.issued_date:
            raise HTTPException(422, 'Expiry date must be on or after the issue date')
        fields = ('category', 'label', 'institute', 'cert_no', 'issued_date', 'expiry_date') if kind == 'cards' else ('title',)
        payload = {key: value for key, value in body.model_dump(mode='json').items() if key in fields}
        if kind == 'cards':
            if body.no_expiry is not None:
                payload['no_expiry'] = body.no_expiry
                if body.no_expiry:
                    payload['expiry_date'] = None
            elif body.expiry_date is not None:
                payload['no_expiry'] = False
        if kind == 'cards' and all(old.get(key) == value for key, value in payload.items()):
            return old
        rows = await db(user, table(kind), 'PATCH', params={'id': f'eq.{record_id}', 'updated_at': f'eq.{body.updated_at}'}, payload=payload)
        if not rows:
            raise HTTPException(409, 'This document changed. Refresh before editing again.')
        async with ctx.shared_client() as client:
            await ctx.audit(client, user, 'update', table(kind), str(record_id), old, rows[0])
        return rows[0]

    @router.get('/card-import/capabilities')
    async def card_import_capabilities(user: dict = Depends(ctx.get_current_user)):
        require(user)
        return {'retry_safe': True}

    @router.post('/{kind}/upload', status_code=201)
    async def upload(kind: str, worker_id: UUID, request: Request, record_id: UUID | None = None,
                     side: Literal['front', 'back'] = 'front', updated_at: str | None = None,
                     import_id: UUID | None = None,
                     user: dict = Depends(ctx.get_current_user)):
        require(user); table(kind); await accessible(user, worker_id)
        if import_id and (kind != 'cards' or (record_id and record_id != import_id)):
            raise HTTPException(422, 'Invalid card import reference')
        old = await row(user, kind, record_id) if record_id else None
        if import_id and not record_id:
            records = await db(user, 'worker_cards', params={'id': f'eq.{import_id}', 'limit': '1'})
            old = records[0] if records else None
        if old and old['worker_id'] != str(worker_id):
            raise HTTPException(409, 'Document belongs to a different worker')
        if side == 'back' and (not old or kind != 'cards'):
            raise HTTPException(422, 'Save the front of a card before adding its back')
        data, mime = await read_file(request)
        if kind == 'cards' and mime == 'application/pdf':
            raise HTTPException(415, 'Card sides must be JPG or PNG. Upload PDFs under Certificates.')
        plan = request.headers.get('X-Document-Masking')
        field = 'file_path' if kind == 'certificates' else 'back_image_path' if side == 'back' else 'image_path'
        if import_id:
            digest = hashlib.sha256(import_id.bytes + side.encode() + b'\0' + data)
            digest.update(b'\0')
            digest.update((plan or '').encode())
            object_id = UUID(bytes=digest.digest()[:16], version=4)
            key = f'{worker_id}/{object_id}.png'
            if old and old.get(field) == key:
                return old
        if old and not updated_at:
            raise HTTPException(409 if import_id else 422, 'Refresh the document before replacing a file')
        data, mime = await run_in_threadpool(masking.process, masking.apply, data, mime, plan, MAX_FILE)
        if not import_id:
            extension = {'image/jpeg': 'jpg', 'image/png': 'png', 'application/pdf': 'pdf'}[mime]
            key = f'{worker_id}/{uuid4()}.{extension}'
        async with ctx.shared_client() as client:
            if ctx.private_image_url and mime.startswith('image/'):
                await store_card_image(client, ctx.private_image_url, ctx.rest_url, user['auth_uid'],
                                       'worker-cards', key, mime, bytes(data), retry=bool(import_id))
            else:
                r = await client.post(f'{storage}/object/worker-cards/{key}', headers={**ctx.supabase_headers(user['token']), 'Content-Type': mime, 'x-upsert': 'false'}, content=bytes(data))
                if not r.is_success:
                    try:
                        error = r.json()
                    except ValueError:
                        error = {}
                    duplicate = r.status_code in (400, 409) and isinstance(error, dict) and error.get('error') in ('Duplicate', 'AlreadyExists')
                    if not (import_id and duplicate):
                        raise HTTPException(503, 'Private storage upload failed. Please try again.')
        payload = {field: key}
        if kind == 'certificates':
            payload['file_type'] = 'pdf' if mime == 'application/pdf' else 'image'
        if old:
            rows = await db(user, table(kind), 'PATCH', params={'id': f'eq.{record_id}', 'updated_at': f'eq.{updated_at}'}, payload=payload)
        else:
            payload.update(worker_id=str(worker_id), uploaded_by=user['user_id'])
            if import_id:
                payload['id'] = str(import_id)
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
        private_object = None
        if path.startswith(record['worker_id'] + '/') and '..' not in path:
            if re.fullmatch(r'[^/]+/[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png|webp)', path, re.IGNORECASE):
                private_object = ('worker-cards', path)
            url = f'{storage}/object/authenticated/worker-cards/{quote(path, safe="/")}'
            headers = ctx.supabase_headers(user['token'])
        elif legacy_url(path, ctx.r2_public_base, urlsplit(ctx.rest_url).netloc):
            url, headers = path, {}
            if urlsplit(path).netloc in ('lqnbdemtgkermhaqfboh.supabase.co', urlsplit(ctx.rest_url).netloc):
                # Storage was migrated with its original bucket/object keys.
                # Resolve old links against the active project, after row scope.
                key = unquote(urlsplit(path).path.removeprefix('/storage/v1/object/public/dpr-photos/'))
                if not key.startswith('worker-cards/' + record['worker_id'] + '/') or '..' in key.split('/'):
                    raise HTTPException(422, 'Invalid historical file location')
                url = f'{storage}/object/public/dpr-photos/{quote(key, safe="/")}'
                private_object = ('dpr-photos', key)
            if urlsplit(path).netloc == urlsplit(ctx.r2_public_base).netloc and ctx.r2_presign_get:
                key = unquote(urlsplit(path).path).lstrip('/')
                if '..' in key.split('/'):
                    raise HTTPException(422, 'Invalid historical file location')
                url = ctx.r2_presign_get(key)
        else:
            raise HTTPException(422, 'This historical file location is not supported. Upload a replacement original.')

        async def read_original(client, source, source_headers):
            data = bytearray()
            async with client.stream('GET', source, headers=source_headers, follow_redirects=False) as r:
                if r.status_code != 200:
                    return None
                async for chunk in r.aiter_bytes():
                    if len(data) + len(chunk) > MAX_FILE:
                        raise HTTPException(413, 'Original file exceeds 20 MB')
                    data.extend(chunk)
            return bytes(data)

        try:
            async with ctx.shared_client() as client:
                data = None
                if private_object and ctx.private_image_url:
                    data = await read_original(client, ctx.private_image_url(*private_object, 'GET'), {})
                if data is None:
                    data = await read_original(client, url, headers)
                if data is None:
                    raise HTTPException(502, 'Original file is unavailable. The saved record is retained; upload a replacement if available.')
        except httpx.RequestError:
            raise HTTPException(502, 'Original file is temporarily unavailable. The saved record is retained.')
        return Response(bytes(data), media_type=file_type(bytes(data)), headers={'Cache-Control': 'no-store', 'Content-Disposition': 'inline'})
    return router


