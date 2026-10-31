"""Read-only, explicitly scoped attendance export. No user-auth fallback."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
from collections import deque
from datetime import date, datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ...db import require_service, service_headers, shared_client
from ...settings import REST

logger = logging.getLogger(__name__)
CODE = re.compile(r"^[A-Za-z0-9_. -]{1,100}$")
FIELDS = ('record_id', 'work_date', 'worker_code', 'worker_name', 'site_code',
          'site_name', 'status', 'start_time', 'end_time', 'end_next_day',
          'shift_type', 'normal_hours', 'ot_hours', 'day_type', 'submitted_at', 'updated_at')


def build_integration_router():
    router = APIRouter(prefix='/api/integration/v1', tags=['integration'])
    windows = {}

    async def authenticate(request: Request):
        hashes = [s.strip() for s in os.getenv('VCMS_INTEGRATION_KEY_HASHES', '').split(',') if s.strip()]
        sites = sorted(set(s.strip() for s in os.getenv('VCMS_INTEGRATION_SITE_CODES', '').split(',') if s.strip()))
        expiry = os.getenv('VCMS_INTEGRATION_EXPIRES_AT', '')
        try:
            expires = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            valid = expires.tzinfo is not None and expires > datetime.now(timezone.utc)
        except ValueError:
            valid = False
        if not hashes or any(not re.fullmatch('[0-9a-f]{64}', s) for s in hashes) or not sites or any(not CODE.fullmatch(s) for s in sites) or not valid:
            raise HTTPException(503, 'Integration is not configured or has expired')
        header = request.headers.get('authorization', '')
        if not header.startswith('Bearer ') or len(header) > 512:
            raise HTTPException(401, 'Invalid integration credential')
        digest = hashlib.sha256(header[7:].encode()).hexdigest()
        matches = [hmac.compare_digest(digest, expected) for expected in hashes]
        if not any(matches):
            raise HTTPException(401, 'Invalid integration credential')
        # One bounded window per configured key; rotations never grow state indefinitely.
        for key in list(windows):
            if key not in hashes:
                del windows[key]
        now = time.monotonic()
        window = windows.setdefault(digest, deque())
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= 60:
            raise HTTPException(429, 'Integration rate limit exceeded', headers={'Retry-After': '60'})
        window.append(now)
        return sites

    async def export(request, response, sites, start, end, site_code, worker_code, cursor, limit):
        if end < start or (end - start).days >= 62:
            raise HTTPException(400, 'Use an inclusive range of 1 to 62 days')
        if site_code is not None and site_code not in sites:
            raise HTTPException(403, 'Site is outside integration scope')
        if worker_code is not None and not CODE.fullmatch(worker_code):
            raise HTTPException(400, 'Invalid worker code')
        scope = [str(start), str(end), site_code, worker_code, sites]
        after_date = after_id = None
        if cursor:
            try:
                if len(cursor) > 4096:
                    raise ValueError()
                value = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
                if value['scope'] != scope:
                    raise ValueError()
                after_date = date.fromisoformat(value['date']).isoformat()
                after_id = str(UUID(value['id']))
            except (ValueError, KeyError, TypeError):
                raise HTTPException(400, 'Invalid cursor or changed filters')
        require_service()
        payload = dict(p_from=str(start), p_to=str(end), p_sites=[site_code] if site_code else sites,
                       p_worker=worker_code, p_after_date=after_date, p_after_id=after_id, p_limit=limit + 1)
        started = time.monotonic()
        try:
            async with shared_client() as client:
                result = await client.post(f'{REST}/rpc/integration_attendance_range_v1',
                                          headers=service_headers(), json=payload, timeout=15)
            if result.status_code != 200:
                raise ValueError()
            rows = result.json()
            if not isinstance(rows, list) or len(rows) > limit + 1 or any(not isinstance(row, dict) for row in rows):
                raise ValueError()
            # Defence in depth against accidental widening in the database function.
            if any(row.get('site_code') not in payload['p_sites'] for row in rows):
                raise ValueError()
            records = [{field: row.get(field) for field in FIELDS} for row in rows[:limit]]
        except (httpx.HTTPError, ValueError):
            logger.warning('integration_read database_failure path=%s', request.url.path)
            raise HTTPException(503, 'Attendance service unavailable')
        next_cursor = None
        if len(rows) > limit:
            last = records[-1]
            value = dict(scope=scope, date=last['work_date'], id=last['record_id'])
            next_cursor = base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode().rstrip('=')
        response.headers['Cache-Control'] = 'no-store'
        logger.info('integration_read path=%s from=%s to=%s rows=%d duration_ms=%d',
                    request.url.path, start, end, len(records), (time.monotonic() - started) * 1000)
        return dict(records=records, next_cursor=next_cursor, has_more=next_cursor is not None,
                    server_time=datetime.now(timezone.utc).isoformat())

    @router.get('/attendance')
    async def attendance(request: Request, response: Response, from_: date = Query(alias='from'),
                         to: date = Query(), site_code: str | None = None,
                         cursor: str | None = None, limit: int = Query(200, ge=1, le=500),
                         sites: list = Depends(authenticate)):
        return await export(request, response, sites, from_, to, site_code, None, cursor, limit)

    @router.get('/worker-day')
    async def worker_day(request: Request, response: Response, worker_code: str, date: date,
                         cursor: str | None = None, limit: int = Query(200, ge=1, le=500),
                         sites: list = Depends(authenticate)):
        return await export(request, response, sites, date, date, None, worker_code, cursor, limit)

    return router
