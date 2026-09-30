import asyncio
from copy import deepcopy

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app import main


def row(id='a1', date='2026-09-30', start='08:00', end='19:00', **extra):
    return dict(id=id, work_date=date, site_id='s1', worker_id=id,
                sites={'site_name':'LOGISTICS'}, workers={'name':id,'worker_code':id},
                attendance=dict(id='att-'+id,present=True,start_time=start,end_time=end,
                    end_next_day=False,submitted_at=None,absence_type=None,shift_type='day',
                    partial_leave_type=None,leave_portion=None,leave_value=0,
                    normal_hours=8,ot_hours=2,day_type='WD',**extra))


@pytest.fixture
def db(monkeypatch):
    records=[row(),row('a2'),row('tomorrow','2026-10-01',start=None)]
    writes=[];audits=[]
    def transport(req):
        import json
        p=req.url.path;params=req.url.params
        if p.endswith('/allocations'):
            result=records
            for key in ('id','work_date','worker_id','site_id'):
                if params.get(key):result=[r for r in result if r[key]==params[key][3:]]
            # The fake enforces the same visibility boundary as a scoped RLS read.
            if req.headers.get('Authorization')=='Bearer outside':result=[]
            return httpx.Response(200,json=deepcopy(result))
        if p.endswith('/public_holidays'):return httpx.Response(200,json=[])
        if p.endswith('/attendance') and req.method=='PATCH':
            body=json.loads(req.content);writes.append((params['id'],body))
            for r in records:
                if r['attendance']['id']==params['id'][3:]:
                    r['attendance'].update(body)
                    return httpx.Response(200,json=[deepcopy(r['attendance'])])
            return httpx.Response(200,json=[])
        raise AssertionError(str(req.url))
    client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
    class Context:
        async def __aenter__(self):return client
        async def __aexit__(self,*args):pass
    async def unlocked(*args):return False
    async def audit(*args):audits.append(args)
    monkeypatch.setattr(main,'REST','https://test.supabase.co/rest/v1')
    monkeypatch.setattr(main,'shared_client',Context)
    monkeypatch.setattr(main,'month_locked',unlocked)
    monkeypatch.setattr(main,'audit',audit)
    return records,writes,audits


def user(role='main_sup',token='test'):return dict(role=role,token=token,user_id='u1')
def run(coro):return asyncio.run(coro)


def test_individual_persistence_and_date_default(db):
    records,writes,audits=db
    result=run(main.mark_attendance(main.AttendanceMark(allocation_id='a1',start_time='07:00'),user()))
    assert result['normal_hours']==8 and result['ot_hours']==3
    assert records[0]['attendance']['start_time']=='07:00'
    assert records[0]['attendance']['end_time']=='19:00'
    assert records[1]['attendance']['start_time']=='08:00'
    assert records[2]['attendance']['start_time'] is None
    assert run(main.day_sheet('2026-10-01',user=user()))[0]['start_time']=='08:00'
    assert run(main.day_sheet('2026-09-30',user=user()))[0]['start_time']=='07:00'
    assert audits[0][-2]['start_time']=='08:00'
    assert audits[0][-1]['start_time']=='07:00'


def test_bulk_same_save_path(db):
    result=run(main.attendance_batch(main.AttendanceBatchIn(changes=[main.AttendanceMark(allocation_id=id,start_time='06:30') for id in ('a1','a2')]),user()))
    assert result['ok']
    assert all(r['ot_hours']==3.5 for r in result['results'])
    assert len(db[1])==2


@pytest.mark.parametrize('role',['site_sup','safety_sup','logistics_sup','wshc','payroll'])
def test_custom_start_permissions(db,role):
    with pytest.raises(HTTPException) as exc:
        run(main.mark_attendance(main.AttendanceMark(allocation_id='a1',start_time='07:00'),user(role)))
    assert exc.value.status_code==403
    assert not db[1]


def test_scope_and_payroll_lock(db,monkeypatch):
    with pytest.raises(HTTPException) as exc:
        run(main.mark_attendance(main.AttendanceMark(allocation_id='a1',start_time='07:00'),user(token='outside')))
    assert exc.value.status_code==404
    async def locked(*args):return True
    monkeypatch.setattr(main,'month_locked',locked)
    with pytest.raises(HTTPException) as exc:
        run(main.mark_attendance(main.AttendanceMark(allocation_id='a1',start_time='07:00'),user()))
    assert exc.value.status_code==403
    assert not db[1]
    assert run(main.mark_attendance(main.AttendanceMark(allocation_id='a1',start_time='07:00'),user('admin')))['ok']


def test_submitted_reason_and_partial_bulk(db):
    db[0][1]['attendance']['submitted_at']='2026-09-30T20:00:00Z'
    result=run(main.attendance_batch(main.AttendanceBatchIn(changes=[main.AttendanceMark(allocation_id=id,start_time='07:00') for id in ('a1','a2')]),user()))
    assert result['results'][0]['ok'] and not result['results'][1]['ok']
    assert db[0][1]['attendance']['start_time']=='08:00'
    assert run(main.mark_attendance(main.AttendanceMark(allocation_id='a2',start_time='07:00',edit_reason='Early work'),user()))['ok']
    assert db[2][-1][-1]['edit_reason']=='Early work'


@pytest.mark.parametrize('time',['25:00','07:61','7:00','07:00:00','',None])
def test_invalid_times(time):
    with pytest.raises(ValidationError):main.AttendanceMark(allocation_id='a1',start_time=time)


@pytest.mark.parametrize('day,expected',[('WD',(8,3)),('SAT',(4,7)),('SUN',(0,11)),('PH',(0,11))])
def test_existing_hours_rules(day,expected):
    assert main.compute_hours(day,'07:00','19:00',False)==expected
    assert main.compute_hours('WD','07:00','12:00',False)==(5,0)
    assert main.compute_hours('WD','20:00','06:00',True)==(8,2)


def test_historical_null_split_day(db):
    db[0][0]['attendance']['start_time']=None
    db[0][0]['attendance']['end_time']='12:00'
    db[0][1]['worker_id']='a1'
    db[0][1]['attendance']['start_time']='13:00'
    result=run(main.mark_attendance(main.AttendanceMark(allocation_id='a2',start_time='13:00'),user()))
    assert result['normal_hours']==4 and result['ot_hours']==2
    assert db[0][0]['attendance']['start_time'] is None


def test_submitted_partial_leave_start_edit_preserves_leave_and_end(db):
    att = db[0][0]['attendance']
    att.update(partial_leave_type='al', leave_portion='second_half', leave_value=0.5,
               submitted_at='2026-09-23T20:00:00Z')
    result = run(main.mark_attendance(main.AttendanceMark(allocation_id='a1',
                    start_time='11:00', edit_reason='Actual work began at 11 AM'), user()))
    assert result['normal_hours'] == 7 and result['ot_hours'] == 0
    assert att['start_time'] == '11:00' and att['end_time'] == '19:00'
    assert att['partial_leave_type'] == 'al' and att['leave_portion'] == 'second_half'
    assert att['leave_value'] == 0.5 and att['submitted_at'] == '2026-09-23T20:00:00Z'
