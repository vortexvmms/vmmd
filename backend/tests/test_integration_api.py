import asyncio
import hashlib
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from app.modules.integration import router as module

KEY = 'test-credential-not-real'
ID = '00000000-0000-0000-0000-000000000001'

@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv('VCMS_INTEGRATION_KEY_HASHES', hashlib.sha256(KEY.encode()).hexdigest())
    monkeypatch.setenv('VCMS_INTEGRATION_SITE_CODES', 'PCS')
    monkeypatch.setenv('VCMS_INTEGRATION_EXPIRES_AT', '2099-01-01T00:00:00Z')
    calls = []
    rows = [dict(record_id=ID,work_date='2026-10-01',site_code='PCS',worker_code='W1',
                 status='present',end_time='19:00',end_next_day=True,fin='EXCLUDED')]
    def db(req):
        assert req.method == 'POST' and req.url.path.endswith('/rpc/integration_attendance_range_v1')
        calls.append(json.loads(req.content))
        return httpx.Response(200,json=rows)
    @asynccontextmanager
    async def context():
        async with httpx.AsyncClient(transport=httpx.MockTransport(db)) as c:
            yield c
    monkeypatch.setattr(module,'shared_client',context)
    monkeypatch.setattr(module,'require_service',lambda: None)
    monkeypatch.setattr(module,'REST','https://example.test/rest/v1')
    app = FastAPI(); app.include_router(module.build_integration_router())
    def get(path='/attendance?from=2026-10-01&to=2026-10-01',key=KEY,method='GET'):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
                return await c.request(method,'/api/integration/v1'+path,headers={'Authorization':'Bearer '+key} if key else {})
        return asyncio.run(run())
    return get,calls,rows

@pytest.mark.parametrize('key',['','wrong'])
def test_denied_without_db(api,key):
    get,calls,_=api
    assert get(key=key).status_code==401
    assert not calls

@pytest.mark.parametrize('setting,value',[
 ('VCMS_INTEGRATION_KEY_HASHES',''),('VCMS_INTEGRATION_KEY_HASHES','bad'),
 ('VCMS_INTEGRATION_EXPIRES_AT',''),('VCMS_INTEGRATION_EXPIRES_AT','2000-01-01T00:00:00Z'),
 ('VCMS_INTEGRATION_EXPIRES_AT','2099-01-01')])
def test_fail_closed(api,monkeypatch,setting,value):
    get,calls,_=api;monkeypatch.setenv(setting,value)
    assert get().status_code==503 and not calls

def test_scope_and_field_allowlist(api):
    get,calls,_=api
    r=get(); assert r.status_code==200
    assert r.headers['cache-control']=='no-store'
    assert calls[0]['p_sites'] is None
    assert 'fin' not in r.text and r.json()['records'][0]['end_next_day'] is True

def test_worker_day(api):
    get,calls,_=api
    assert get('/worker-day?worker_code=W1&date=2026-10-01').status_code==200
    assert calls[0]['p_worker']=='W1'
    assert calls[0]['p_from']==calls[0]['p_to']

@pytest.mark.parametrize('query',[
 'from=2026-10-02&to=2026-10-01', 'from=2026-01-01&to=2026-03-04',
 'from=2026-10-01&to=2026-10-01&cursor=bad'])
def test_bad_ranges_cursors(api,query):
    get,calls,_=api
    assert get('/attendance?'+query).status_code==400 and not calls

def test_paging_filter_binding(api):
    get,calls,rows=api;rows.append({**rows[0],'record_id':'00000000-0000-0000-0000-000000000002'})
    path='/attendance?from=2026-10-01&to=2026-10-01&limit=1'
    r=get(path);assert r.status_code==200
    cursor=r.json()['next_cursor'];assert cursor and r.json()['has_more']
    assert get(path+'&cursor='+cursor).status_code==200
    assert calls[-1]['p_after_id']==ID
    assert get(path+'&site_code=PCS&cursor='+cursor).status_code==400

def test_rotation_revocation(api,monkeypatch):
    get,_,_=api;second='second-test-key'
    monkeypatch.setenv('VCMS_INTEGRATION_KEY_HASHES', hashlib.sha256(KEY.encode()).hexdigest()+','+hashlib.sha256(second.encode()).hexdigest())
    assert get(key=KEY).status_code==200 and get(key=second).status_code==200
    monkeypatch.setenv('VCMS_INTEGRATION_KEY_HASHES',hashlib.sha256(second.encode()).hexdigest())
    assert get(key=KEY).status_code==401

def test_no_write_route_and_limit(api):
    get,calls,_=api
    assert get(method='POST').status_code==405 and not calls
    assert get('/attendance?from=2026-10-01&to=2026-10-01&limit=501').status_code==422

def test_database_filter_violation(api):
    get,_,rows=api;rows[0]['site_code']='OTHER'
    assert get('/attendance?from=2026-10-01&to=2026-10-01&site_code=PCS').status_code==503

def test_rate_limit(api):
    get,_,_=api
    for _ in range(60):assert get().status_code==200
    assert get().status_code==429

def test_existing_user_endpoint_rejects_machine_key(monkeypatch):
    from app import main, auth
    @asynccontextmanager
    async def denied_auth():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(401,json={}))) as c:
            yield c
    monkeypatch.setattr(auth,'shared_client',denied_auth)
    monkeypatch.setattr(auth,'SUPABASE_URL','https://example.test')
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='https://test') as c:
            return await c.get('/api/v1/attendance?date=2026-10-01',headers={'Authorization':'Bearer '+KEY})
    assert asyncio.run(run()).status_code==401


def test_all_sites_including_future_sites(api, monkeypatch):
    get, calls, rows = api
    monkeypatch.delenv('VCMS_INTEGRATION_SITE_CODES', raising=False)
    rows.append({**rows[0], 'site_code': 'FUTURE-SITE'})
    result = get()
    assert result.status_code == 200
    assert {r['site_code'] for r in result.json()['records']} == {'PCS', 'FUTURE-SITE'}
    assert calls[-1]['p_sites'] is None


def test_optional_site_filter(api):
    get, calls, _ = api
    assert get('/attendance?from=2026-10-01&to=2026-10-01&site_code=PCS').status_code == 200
    assert calls[-1]['p_sites'] == ['PCS']
    assert get('/attendance?from=2026-10-01&to=2026-10-01&site_code=*').status_code == 400
