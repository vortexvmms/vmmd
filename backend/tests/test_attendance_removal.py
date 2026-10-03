import asyncio
import json
import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app import main
A='40000000-0000-0000-0000-000000000001'
REV='2026-10-01T00:00:00Z'
def body(**changes):return main.AttendanceRemoval(**dict(allocation_id=A,reason='not_scheduled',allocation_updated_at=REV,attendance_updated_at=REV,**changes))
def user(role='admin',token='test'):return dict(role=role,token=token,user_id='u1')
@pytest.fixture
def db(monkeypatch):
 calls=[];state={'visible':True,'error':None}
 def transport(req):
  calls.append(req)
  if req.url.path.endswith('/allocations'):return httpx.Response(200,json=[{'id':A}] if state['visible'] else [])
  if req.url.path.endswith('/rpc/remove_attendance_day'):
   if state['error']:return httpx.Response(400,json=state['error'])
   return httpx.Response(200,json={'ok':True,'work_date':'2026-10-03'})
  raise AssertionError(str(req.url))
 client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
 class Context:
  async def __aenter__(self):return client
  async def __aexit__(self,*args):pass
 monkeypatch.setattr(main,'REST','https://test.supabase.co/rest/v1');monkeypatch.setattr(main,'shared_client',Context);monkeypatch.setattr(main,'require_service',lambda:None)
 return calls,state

def test_scoped_read_then_atomic_removal(db):
 result=asyncio.run(main.remove_attendance_day(body(),user()));assert result['ok']
 calls,_=db;assert len(calls)==2
 assert calls[0].headers['Authorization']=='Bearer test'
 data=json.loads(calls[1].content);assert data['p_allocation_id']==A and data['p_reason']=='not_scheduled'
 assert data['p_user_id']=='u1' and data['p_attendance_updated_at'].startswith('2026-10-01')

def test_outside_site_never_calls_service_rpc(db):
 db[1]['visible']=False
 with pytest.raises(HTTPException) as e:asyncio.run(main.remove_attendance_day(body(),user()))
 assert e.value.status_code==404 and len(db[0])==1

def test_payroll_role_denied_before_database(db):
 with pytest.raises(HTTPException) as e:asyncio.run(main.remove_attendance_day(body(),user('payroll')))
 assert e.value.status_code==403 and not db[0]

@pytest.mark.parametrize('code,status',[('42501',403),('40001',409),('P0002',404),('XX000',503)])
def test_database_rejections_are_not_false_success(db,code,status):
 db[1]['error']={'code':code,'message':'Cannot remove'}
 with pytest.raises(HTTPException) as e:asyncio.run(main.remove_attendance_day(body(),user()))
 assert e.value.status_code==status

@pytest.mark.parametrize('reason',['absent','female','',None])
def test_explicit_reason_required(reason):
 with pytest.raises(ValidationError):main.AttendanceRemoval(allocation_id=A,reason=reason,allocation_updated_at=REV)

@pytest.mark.parametrize('site,expected_hours',[('s1',8),('s2',14)])
def test_resource_summary_removes_cancelled_dpr_hours_and_overlays_remaining_site(monkeypatch,site,expected_hours):
 # Prepared DPRs are retained; only the corrected day gets a live hours overlay.
 reports=[{'id':'r1','report_date':'2026-10-03','project_title':'QA'}, {'id':'r2','report_date':'2026-10-02','project_title':'QA'}]
 def transport(req):
  path=req.url.path;p=req.url.params
  if path.endswith('/daily_reports'):
   field=p.get('select','').split(',')[-1]
   if field in ('manpower','equipment','materials'):
    return httpx.Response(200,json=[{'id':r['id'],field:[{'name':'Extra Worker','role':'Worker','total':8,'no':1}] if field=='manpower' else []} for r in reports])
   return httpx.Response(200,json=reports)
  if path.endswith('/dpr_projects'):return httpx.Response(200,json=[])
  if path.endswith('/allocations'):
   if p.get('status')=='eq.cancelled':return httpx.Response(200,json=[{'work_date':'2026-10-03','site_id':'s1','worker_id':'w1','workers':{'name':'Extra Worker'}}])
   assert p.get('status')=='eq.allocated'
   return httpx.Response(200,json=[{'id':'a2','work_date':'2026-10-03','worker_id':'w1','workers':{'name':'Extra Worker','trade':'Worker'}}] if site=='s2' else [])
  if path.endswith('/attendance'):return httpx.Response(200,json=[{'allocation_id':'a2','present':True,'normal_hours':0,'ot_hours':6}])
  raise AssertionError(str(req.url))
 client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
 monkeypatch.setattr(main.httpx,'AsyncClient',lambda **kw:client)
 monkeypatch.setattr(main,'REST','https://test.supabase.co/rest/v1')
 result=asyncio.run(main.resource_summary(site,'2026-10',user()))
 assert result['manpower']['manhours_total']==expected_hours
 assert result['attendance'][0]['days']['2']==8
 if site=='s1':assert '3' not in result['attendance'][0]['days']
 else:assert result['attendance'][0]['days']['3']==6
