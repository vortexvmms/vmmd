from contextlib import asynccontextmanager
from datetime import date
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.equipment.router import EquipmentContext, build_equipment_router, _period_bounds
from app.modules.equipment import operations


def fixture(monkeypatch, responses, role="admin"):
    monkeypatch.setattr(operations,"require_service",lambda:None)
    monkeypatch.setattr(operations,"service_headers",lambda:{"apikey":"server-only","Authorization":"Bearer server-only"})
    calls=[]
    def respond(request):
        calls.append(request)
        path=request.url.path.rsplit('/',1)[-1]
        value=responses.get(path,[])
        if callable(value):value=value(request)
        return httpx.Response(200,json=value)
    transport=httpx.MockTransport(respond)
    @asynccontextmanager
    async def client():
        async with httpx.AsyncClient(transport=transport) as c:yield c
    async def user():return {"user_id":str(uuid4()),"token":"staff-token","role":role}
    async def audit(*args):pass
    app=FastAPI();app.include_router(build_equipment_router(EquipmentContext(user,client,"https://db.test/rest/v1",lambda token:{"Authorization":"Bearer "+token},audit,"https://files.test")))
    return TestClient(app),calls


def test_invalid_link_is_rejected_without_directory_disclosure(monkeypatch):
    c,calls=fixture(monkeypatch,{})
    r=c.get('/api/v1/equipment/tipper/driver/setup',headers={'X-Tipper-Link':'x'*43})
    assert r.status_code==403
    assert not any(x.url.path.endswith('tipper_drivers') for x in calls)


def test_common_portal_exposes_only_names_not_phones_tokens_or_prices(monkeypatch):
    c,calls=fixture(monkeypatch,{"tipper_portal_links":[{"id":str(uuid4())}],"tipper_drivers":[{"id":str(uuid4()),"name":"Driver One"}]})
    r=c.get('/api/v1/equipment/tipper/driver/setup',headers={'X-Tipper-Link':'x'*43})
    assert r.status_code==200 and r.json()['choose_driver']
    assert 'server-only' not in r.text and 'phone' not in r.text and 'token_hash' not in r.text
    driver_request=next(x for x in calls if x.url.path.endswith('tipper_drivers'))
    assert driver_request.url.params['select']=='id,name'


def test_individual_driver_status_scoped_to_driver_and_no_documents(monkeypatch):
    d,l=str(uuid4()),str(uuid4())
    c,calls=fixture(monkeypatch,{"tipper_driver_links":[{"id":l,"driver_id":d}],"tipper_drivers":[{"id":d,"name":"One"}],"tipper_submissions":[{"trip_date":"2026-09-30","status":"approved","trip":[{"trip_date":"2026-09-30"}]},{"trip_date":"2026-10-01","status":"pending"}]})
    r=c.get('/api/v1/equipment/tipper/driver/status',headers={'X-Tipper-Link':'x'*43})
    assert r.status_code==200
    assert r.json()[1]['approved']==1 and r.json()[0]['pending']==1
    req=next(x for x in calls if x.url.path.endswith('tipper_submissions'))
    assert req.url.params['driver_id']=='eq.'+d and req.url.params['select']=='trip_date,status,trip:tipper_trips(trip_date)'
    assert 'source_image' not in r.text


def test_driver_cannot_read_staff_reports_or_generate_links(monkeypatch):
    c,calls=fixture(monkeypatch,{},role='site_sup')
    assert c.post('/api/v1/equipment/tipper/portal-link').status_code==403
    assert c.get('/api/v1/equipment/tipper/export/xlsx?month=2026-09').status_code==403
    assert not calls


def test_wrong_driver_cannot_confirm_another_submission(monkeypatch):
    d,l=str(uuid4()),str(uuid4())
    c,calls=fixture(monkeypatch,{"tipper_driver_links":[{"id":l,"driver_id":d}],"tipper_drivers":[{"id":d,"name":"One"}],"tipper_submissions":[]})
    r=c.post('/api/v1/equipment/tipper/driver/submissions/'+str(uuid4())+'/confirm',headers={'X-Tipper-Link':'x'*43},json={'site_rule_id':str(uuid4()),'trip_date':'2026-09-30','do_no':'DO1','truck_no':'XF1','checked':True})
    assert r.status_code==404
    request=next(x for x in calls if x.url.path.endswith('tipper_submissions'))
    assert request.url.params['driver_id']=='eq.'+d and request.url.params['link_id']=='eq.'+l


def test_quality_warning_cannot_bypass_driver_review(monkeypatch):
    d,l,s=str(uuid4()),str(uuid4()),str(uuid4())
    c,_=fixture(monkeypatch,{"tipper_driver_links":[{"id":l,"driver_id":d}],"tipper_drivers":[{"id":d,"name":"One"}],"tipper_submissions":[{"id":s,"status":"draft","quality_warnings":["cropped numbers"]}]})
    r=c.post('/api/v1/equipment/tipper/driver/submissions/'+s+'/confirm',headers={'X-Tipper-Link':'x'*43},json={'site_rule_id':str(uuid4()),'trip_date':'2026-09-30','do_no':'DO1','truck_no':'XF1','checked':True})
    assert r.status_code==422 and 'Retake' in r.json()['detail']


def test_date_range_includes_last_work_day_and_rejects_invalid_range():
    assert _period_bounds(None,'2026-09-01','2026-09-30')==('2026-09-01','2026-10-01')
    assert _period_bounds('2026-09')==('2026-09-01','2026-10-01')
    from fastapi import HTTPException
    with pytest.raises(HTTPException):_period_bounds(None,'2026-09-30','2026-09-01')
