"""Site defaults, historical snapshots and shared daily OT allowance."""
from datetime import timedelta
import pytest
from fastapi import HTTPException
from app import main

PCS=dict(effective_from='2026-10-05',start_time='07:00',lunch_start='11:30',lunch_end='12:00',end_time='16:30',weekday_basic_hours=8,saturday_basic_hours=4,saturday_rule='first_hours',lunch_rule='overlap')

@pytest.mark.parametrize('day,expected',[('WD',(8,1)),('SAT',(4,5)),('SUN',(0,9)),('PH',(0,9))])
def test_pcs_full_shift(day,expected):
    assert main.compute_hours(day,'07:00','16:30',False,PCS)==expected

@pytest.mark.parametrize('end,expected',[('11:30',4.5),('11:45',4.5),('12:00',4.5),('16:30',9)])
def test_actual_lunch_overlap(end,expected):
    assert main.worked_hours('07:00',end,False,PCS)==expected


def test_saturday_first_hours_even_after_noon():
    assert main.compute_hours('SAT','13:00','18:00',False,PCS)==(4,1)
    assert main.compute_hours('SAT','13:00','18:00',False)==(0,5)


def test_default_schedule_matches_current_engine():
    defaults={**PCS,'start_time':'08:00','lunch_start':'12:00','lunch_end':'13:00','end_time':'17:00','lunch_rule':'full_break','saturday_rule':'before_noon'}
    for day in ('WD','SAT','SUN','PH'):
        for start,end,overnight in [('08:00','12:00',False),('08:00','12:30',False),('08:00','17:00',False),('13:00','18:00',False),('20:00','06:00',True)]:
            assert main.compute_hours(day,start,end,overnight,defaults)==main.compute_hours(day,start,end,overnight)


def test_versions_and_existing_attendance_never_inherit_new_settings():
    site={'work_schedules':[PCS,{**PCS,'effective_from':'2026-11-01','start_time':'06:00'}]}
    assert main.site_schedule(site,'2026-10-04')=={}
    assert main.site_schedule(site,'2026-10-05')['start_time']=='07:00'
    assert main.site_schedule(site,'2026-11-01')['start_time']=='06:00'
    allocation={'sites':site,'work_date':'2026-10-05','attendance':{'id':'old','work_schedule':{}}}
    assert main.attendance_schedule(allocation)=={}
    allocation['attendance']=None
    assert main.attendance_schedule(allocation)==PCS
    assert main.SiteCreate(site_code='NEW',site_name='NEW').work_schedule is None


def test_split_site_day_never_gets_two_basic_allowances():
    segments=[dict(start='07:00',end='11:30',end_next_day=False,schedule=PCS),dict(start='13:00',end='18:00',end_next_day=False,schedule={})]
    assert main.compute_day('WD',segments)==[(4.5,0),(3.5,1.5)]
    assert main.compute_day('SAT',segments)==[(4,0.5),(0,5)]


def test_setting_rejects_retroactive_change():
    today=main.datetime.now(main.timezone(main.timedelta(hours=8))).date()
    schedule=main.WorkSchedule(**{**PCS,'effective_from':today-timedelta(days=1)})
    with pytest.raises(HTTPException):main.merge_site_schedule([],schedule)
    schedule=main.WorkSchedule(**{**PCS,'effective_from':today})
    assert len(main.merge_site_schedule([PCS],schedule))>=1


def test_new_attendance_uses_site_policy_and_snapshots_it(monkeypatch):
    import asyncio, json, httpx
    row={'id':'a1','work_date':'2026-10-05','worker_id':'w1','site_id':'s1','sites':{'work_schedules':[PCS]},'attendance':None}
    writes=[]
    def transport(req):
        if req.url.path.endswith('/allocations'):return httpx.Response(200,json=[row])
        if req.url.path.endswith('/public_holidays'):return httpx.Response(200,json=[])
        if req.url.path.endswith('/attendance') and req.method=='POST':
            payload=json.loads(req.content);writes.append(payload);return httpx.Response(201,json=[{'id':'t1',**payload}])
        raise AssertionError(str(req.url))
    client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
    class Context:
        async def __aenter__(self):return client
        async def __aexit__(self,*args):pass
    async def unlocked(*args):return False
    async def no_audit(*args):pass
    monkeypatch.setattr(main,'REST','https://test.supabase.co/rest/v1')
    monkeypatch.setattr(main,'shared_client',Context)
    monkeypatch.setattr(main,'month_locked',unlocked)
    monkeypatch.setattr(main,'audit',no_audit)
    result=asyncio.run(main.mark_attendance(main.AttendanceMark(allocation_id='a1',present=True,shift_type='day',start_time='07:00',end_time='16:30'),{'role':'site_sup','token':'test','user_id':'u1'}))
    assert (result['normal_hours'],result['ot_hours'])==(8,1)
    assert writes[0]['start_time']=='07:00' and writes[0]['work_schedule']==PCS


def test_bulk_end_keeps_site_policy_and_recalculates_workers_concurrently(monkeypatch):
    import asyncio, json, httpx
    rows=[{'id':str(i),'worker_id':'w'+str(i),'attendance':{'id':'t'+str(i),'present':True,'submitted_at':None,'start_time':'07:00','work_schedule':PCS}} for i in range(3)]
    writes=[];active=0;max_active=0
    def transport(req):
        payload=json.loads(req.content);writes.append(payload);return httpx.Response(200,json=[payload])
    client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
    class Context:
        async def __aenter__(self):return client
        async def __aexit__(self,*args):pass
    async def load(*args):return rows
    async def unlocked(*args):return False
    async def daytype(*args):return 'WD'
    async def audit(*args):pass
    async def recompute(*args):
        nonlocal active,max_active
        assert len(writes)==3  # shared daily quotas must see every saved segment
        active+=1;max_active=max(max_active,active)
        await asyncio.sleep(.01)
        active-=1
        return {}
    for name,value in [('REST','https://test.supabase.co/rest/v1'),('shared_client',Context),('_load_day',load),('month_locked',unlocked),('get_day_type',daytype),('audit',audit),('recompute_worker_day',recompute)]:monkeypatch.setattr(main,name,value)
    result=asyncio.run(main.bulk_end(main.BulkEnd(work_date='2026-10-05',site_id='s1',end_time='16:30'),{'role':'site_sup','token':'test','user_id':'u1'}))
    assert result['updated']==3 and result['ok']
    assert all((p['normal_hours'],p['ot_hours'])==(8,1) for p in writes)
    assert max_active==3
