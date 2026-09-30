"""Run against a disposable PostgreSQL database with the migration applied."""
import json
import os
import subprocess
from pathlib import Path
import pytest

DB=os.environ.get('LIFTING_TEST_DB_URL')
pytestmark=pytest.mark.skipif(not DB,reason='Disposable lifting database not configured')
UID='10000000-0000-0000-0000-000000000001'
M1='20000000-0000-0000-0000-000000000001';M2='20000000-0000-0000-0000-000000000002'
DOC='30000000-0000-0000-0000-000000000001';CHART='30000000-0000-0000-0000-000000000002';GDOC='30000000-0000-0000-0000-000000000003'
G='40000000-0000-0000-0000-000000000001';I='50000000-0000-0000-0000-000000000001'


def run(sql,ok=True):
    r=subprocess.run(['psql',DB,'-X','-q','-A','-t','-v','ON_ERROR_STOP=1'],input=sql,text=True,capture_output=True)
    if ok: assert r.returncode==0,r.stderr
    else: assert r.returncode!=0,'Expected rejection'
    return r.stdout.strip() if ok else r.stderr


def setup(role='admin'):
    return f"""begin;
    insert into users values('{UID}','{UID}','QA User','{role}','active');
    insert into lifting_machines(id,machine_id,lm_number,vehicle_number,equipment,swl_kg,examination_date,certificate_expiry,serial_number) values('{M1}','LC1','LM563989N','XE1807Y','Crane',10400,'2026-05-28','2030-05-27','serial'),('{M2}','LC2','LM999999N','XD9950T','Crane',8000,'2026-05-28','2030-05-27','serial2');
    insert into lifting_gear_certificates(id,lg_number,gear_type,swl_kg,examination_date,certificate_expiry,renewal_months,renewal_reason) values('{G}','LG2511S023-024','Webbing sling',3000,current_date,'2030-05-27',12,'Site acceptance');
    insert into lifting_gear_items(id,certificate_id,marking,current_machine_id) values('{I}','{G}','S023','{M1}');
    insert into lifting_documents(id,kind,original_filename,object_key,mime_type,file_size,checksum,machine_id,gear_certificate_id,verified,created_by) values
    ('{DOC}','lm','lm.pdf','originals/lm','application/pdf',100,'hash','{M1}',null,true,'{UID}'),
    ('{CHART}','load_chart','chart.pdf','originals/chart','application/pdf',100,'hash','{M1}',null,true,'{UID}'),
    ('{GDOC}','lg','lg.pdf','originals/lg','application/pdf',100,'hash',null,'{G}',true,'{UID}');
    update lifting_machines set current_document_id='{DOC}' where id='{M1}';
    update lifting_gear_certificates set current_document_id='{GDOC}' where id='{G}';
    set local role authenticated;set local request.jwt.claim.sub='{UID}';
    """


def test_move_and_stale_holder_rejected():
    assert 'borrow' in run(setup()+f"select lifting_move('{I}','{M1}','{M2}','borrow','Issuer','Receiver','QA');select current_machine_id from lifting_gear_items;rollback;")
    error=run(setup()+f"select lifting_move('{I}','{M2}','{M1}','return','Issuer','Receiver','QA');rollback;",False)
    assert 'Holder changed' in error


@pytest.mark.parametrize('role',['site_sup','safety_sup','wshc','payroll'])
def test_unauthorised_mutations_and_payroll_reads(role):
    assert 'Not authorised' in run(setup(role)+f"select lifting_move('{I}','{M1}','{M2}','borrow','A','B','');rollback;",False)
    if role=='payroll': assert run(setup(role)+"select count(*) from lifting_machines;rollback;")=='0'
    else: assert run(setup(role)+"select count(*) from lifting_machines;rollback;")=='2'
    assert 'permission denied' in run(setup(role)+f"update lifting_gear_items set current_machine_id='{M2}' where id='{I}';rollback;",False)


def test_renewal_preserves_old_document_and_checks_identifiers():
    nd='30000000-0000-0000-0000-000000000009'
    pre=setup().split('set local role')[0]+f"insert into lifting_documents(id,kind,original_filename,object_key,mime_type,file_size,checksum,created_by) values('{nd}','lm','renewal.pdf','originals/new','application/pdf',100,'hash','{UID}');set local role authenticated;set local request.jwt.claim.sub='{UID}';"
    data={'confirmed':True,'machine_id':'LC1','lm_number':'LM563989N','vehicle_number':'XE1807Y','serial_number':'serial','examination_date':'2027-05-28','certificate_expiry':'2031-05-27','swl_kg':10400,'equipment':'Crane'}
    result=run(pre+f"select lifting_review('{nd}','{json.dumps(data)}','{M1}');select count(*) from lifting_machines;select count(*) from lifting_documents where machine_id='{M1}' and kind='lm';rollback;")
    assert result.endswith('2\n2')
    data['vehicle_number']='OTHER'
    assert 'identifiers conflict' in run(pre+f"select lifting_review('{nd}','{json.dumps(data)}','{M1}');rollback;",False)


def test_shared_certificate_two_independent_items():
    nd='30000000-0000-0000-0000-000000000009'
    pre=setup().split('set local role')[0]+f"insert into lifting_documents(id,kind,original_filename,object_key,mime_type,file_size,checksum,created_by) values('{nd}','lg','two.pdf','originals/two','application/pdf',100,'hash','{UID}');set local role authenticated;set local request.jwt.claim.sub='{UID}';"
    data={'confirmed':True,'lg_number':'LG2511S025-026','gear_type':'Webbing sling','markings':['S025','S026'],'swl_kg':3000,'examination_date':'2026-01-01','certificate_expiry':'2030-01-01','renewal_months':6,'renewal_reason':'Site requirement'}
    assert run(pre+f"select lifting_review('{nd}','{json.dumps(data)}',null);select count(*) from lifting_gear_items where certificate_id=(select id from lifting_gear_certificates where lg_number='LG2511S025-026');rollback;").endswith('\n2')


def test_frozen_pack_survives_movement_and_validates_new_selection():
    freeze=f"select lifting_freeze_pack('{M1}',array['{I}']::uuid[],array['{DOC}','{CHART}','{GDOC}']::uuid[],'[\"lm_log\",\"lg_log\",\"{DOC}\",\"{CHART}\",\"{GDOC}\"]',false);"
    text=run(setup()+freeze+f"select lifting_move('{I}','{M1}','{M2}','borrow','A','B','');select snapshot->'items'->0->>'current_machine_id' from lifting_packs;rollback;")
    assert text.endswith(M1)
    assert 'Gear selection changed' in run(setup()+f"select lifting_move('{I}','{M1}','{M2}','borrow','A','B','');"+freeze+'rollback;',False)
    assert 'Missing, expired' in run(setup()+f"select lifting_freeze_pack('{M2}',array[]::uuid[],array[]::uuid[],'[\"lm_log\",\"lg_log\"]',false);rollback;",False)


def test_originals_and_packs_cannot_be_overwritten():
    assert 'permission denied' in run(setup()+f"update lifting_documents set checksum='changed' where id='{DOC}';rollback;",False)
    assert 'permission denied' in run(setup()+"delete from lifting_packs;rollback;",False)


def test_concurrent_movement_only_one_holder_wins():
    # Commit disposable fixtures, then roll them back through the test owner cleanup.
    run(setup().replace('begin;','')+"reset role;")
    first=subprocess.Popen(['psql',DB,'-X','-q','-A','-t','-v','ON_ERROR_STOP=1'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    import time
    first.stdin.write(f"begin;set local role authenticated;set local request.jwt.claim.sub='{UID}';select lifting_move('{I}','{M1}','{M2}','borrow','A','B','');select pg_sleep(1);commit;\n");first.stdin.close();time.sleep(.3)
    error=run(f"begin;set local role authenticated;set local request.jwt.claim.sub='{UID}';select lifting_move('{I}','{M1}',null,'return','A','B','');commit;",False)
    first.wait(timeout=5);assert first.returncode==0;assert 'Holder changed' in error
    assert run(f"select current_machine_id from lifting_gear_items where id='{I}'")==M2
    run('delete from lifting_movements;delete from lifting_packs;update lifting_machines set current_document_id=null;update lifting_gear_certificates set current_document_id=null;delete from lifting_documents;delete from lifting_gear_items;delete from lifting_gear_certificates;delete from lifting_machines;delete from users;')
