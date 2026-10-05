"""Transactional cancellation tests against an isolated PostgreSQL database."""
import json
import os
import subprocess
import pytest
DB=os.environ.get('ATTENDANCE_REMOVAL_TEST_DB_URL')
pytestmark=pytest.mark.skipif(not DB,reason='Disposable attendance database not configured')
U='10000000-0000-0000-0000-000000000001'
W='20000000-0000-0000-0000-000000000001'
S='30000000-0000-0000-0000-000000000001'
S2='30000000-0000-0000-0000-000000000002'
A='40000000-0000-0000-0000-000000000001'
A2='40000000-0000-0000-0000-000000000002'
T='50000000-0000-0000-0000-000000000001'
T2='50000000-0000-0000-0000-000000000002'
REV='2026-10-01 00:00:00+00'
def run(sql,ok=True):
 r=subprocess.run(['psql',DB,'-X','-q','-A','-t','-v','ON_ERROR_STOP=1'],input=sql,text=True,capture_output=True)
 if ok:assert r.returncode==0,r.stderr
 else:assert r.returncode!=0,'Expected rejection'
 return r.stdout.strip() if ok else r.stderr

def setup(role='admin',day='2026-10-02',marked=True,split=False):
 sql=f"""begin;
 insert into users(id,name,role,status) values('{U}','QA','{role}','active');
 insert into workers(id,name,worker_code) values('{W}','Test Worker','QA01');
 insert into sites(id,site_name,site_code) values('{S}','Test site','QA1'),('{S2}','Other site','QA2');
 insert into allocations(id,work_date,worker_id,site_id,updated_at) values('{A}','{day}','{W}','{S}','{REV}');
 """
 if marked:sql+=f"""insert into attendance(id,allocation_id,present,start_time,end_time,normal_hours,ot_hours,day_type,submitted_at,updated_at) values('{T}','{A}',true,'08:00','12:00',4,0,'WD',now(),'{REV}');"""
 if split:sql+=f"""insert into allocations(id,work_date,worker_id,site_id,updated_at) values('{A2}','{day}','{W}','{S2}','{REV}');
 insert into attendance(id,allocation_id,present,start_time,end_time,normal_hours,ot_hours,day_type,updated_at) values('{T2}','{A2}',true,'13:00','19:00',4,2,'WD','{REV}');"""
 return sql

def remove(marked=True,revision=REV):return f"select remove_attendance_day('{A}','{U}','not_scheduled','{revision}',"+(f"'{REV}'" if marked else 'null')+");"

def test_retained_record_audit_and_no_absence():
 out=run(setup()+remove()+f"select jsonb_build_object('status',(select status from allocations where id='{A}'),'attendance',(select row_to_json(t) from attendance t where id='{T}'),'audits',(select count(*) from audit_log where action='remove_attendance_day')); rollback;").splitlines()
 d=json.loads(out[-1]);assert d['status']=='cancelled' and d['audits']==1
 assert d['attendance']['present'] and d['attendance']['normal_hours']==4 and d['attendance']['submitted_at']
 assert d['attendance']['absence_type'] is None

@pytest.mark.parametrize('day,expected',[('2026-10-02',(6,0)),('2026-10-03',(0,6)),('2026-10-04',(0,6))])
def test_remaining_single_site_hours_recalculated(day,expected):
 out=run(setup(day=day,split=True)+remove()+f"select jsonb_build_array(normal_hours,ot_hours) from attendance where id='{T2}'; rollback;").splitlines()
 assert json.loads(out[-1])==list(expected)

def test_public_holiday_remaining_site_is_all_overtime():
 out=run(setup(split=True)+"insert into public_holidays(holiday_date,description) values('2026-10-02','QA holiday');"+remove()+f"select jsonb_build_array(normal_hours,ot_hours) from attendance where id='{T2}'; rollback;").splitlines()
 assert json.loads(out[-1])==[0,6]

def test_unmarked_and_idempotent_removal():
 out=run(setup(marked=False)+remove(False)+remove(False)+"select count(*) from audit_log where action='remove_attendance_day'; rollback;").splitlines()
 assert json.loads(out[-2])['already_removed'] and out[-1]=='1'

@pytest.mark.parametrize('role',['admin','site_sup'])
def test_payroll_lock_blocks_every_role(role):
 sql=setup(role)+f"insert into site_supervisors(site_id,user_id) values('{S}','{U}');insert into month_locks(month) values('2026-10-01');"+remove()
 assert 'Month closed' in run(sql,False)

def test_outside_site_and_payroll_role_denied():
 assert 'Not your site' in run(setup('site_sup')+remove(),False)
 assert 'Not allowed' in run(setup('payroll')+remove(),False)

def test_stale_review_and_cancelled_phone_write_denied():
 assert 'Attendance changed' in run(setup()+remove(revision='2026-09-01'),False)
 assert 'removed from this day' in run(setup()+remove()+f"update attendance set end_time='17:00' where id='{T}';",False)

def test_audit_failure_rolls_back_cancellation():
 sql=setup()+"create function fail_audit() returns trigger language plpgsql as $$ begin raise exception 'Audit unavailable'; end $$; create trigger fail_audit before insert on audit_log for each row execute function fail_audit();"+f"""
 do $$ begin
  perform remove_attendance_day('{A}','{U}','not_scheduled','{REV}','{REV}');
 exception when others then null; end $$;
 select status from allocations where id='{A}'; rollback;"""
 assert run(sql).splitlines()[-1]=='allocated'

def test_rpc_is_not_callable_by_browser_roles():
 out=run("select has_function_privilege('anon','public.remove_attendance_day(uuid,uuid,text,timestamptz,timestamptz)','EXECUTE'),has_function_privilege('authenticated','public.remove_attendance_day(uuid,uuid,text,timestamptz,timestamptz)','EXECUTE');")
 assert out=='f|f'


@pytest.mark.parametrize('day,expected',[('2026-10-05',[8,1]),('2026-10-10',[4,5]),('2026-10-11',[0,9])])
def test_site_snapshot_survives_removal_recalculation(day,expected):
 from test_site_work_schedules import PCS
 policy=json.dumps(PCS)
 sql=setup(day=day,split=True)+f"update attendance set start_time='07:00',end_time='16:30',work_schedule='{policy}'::jsonb where id='{T2}';"+remove()+f"select jsonb_build_array(normal_hours,ot_hours) from attendance where id='{T2}'; rollback;"
 assert json.loads(run(sql).splitlines()[-1])==expected
