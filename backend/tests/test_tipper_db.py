import os
from pathlib import Path
from uuid import uuid4
import pytest

psycopg=pytest.importorskip("psycopg")
URL=os.environ.get("TIPPER_TEST_DB_URL")
pytestmark=pytest.mark.skipif(not URL,reason="Disposable tipper database required")


@pytest.fixture
def db():
    with psycopg.connect(URL,autocommit=False) as c:
        yield c
        c.rollback()


def foundation(c):
    u=str(uuid4());c.execute("insert into users(id,auth_uid,name,role) values(%s,%s,'Admin','admin')",(u,u))
    client=c.execute("select id from tipper_clients limit 1").fetchone()[0]
    provider=c.execute("select id from tipper_providers limit 1").fetchone()[0]
    wt=c.execute("select id from tipper_work_types where name='Day Work'").fetchone()[0]
    return u,client,provider,wt


def test_old_amount_untouched_and_database_recalculates_new_hours(db):
    u,c,p,w=foundation(db)
    q="""insert into tipper_trips(client_id,provider_id,work_type_id,trip_sheet_no,trip_date,do_no,truck_no,pickup_location,delivery_location,material_type,quantity,transport_rate,created_by,billing_mode,start_time,end_time,break_minutes,ot_rate)
        values(%s,%s,%s,%s,'2026-09-30','DO1','XF1','','','',%s,100,%s,%s,%s,%s,%s,%s) returning transport_amount,billed_amount,normal_hours,ot_hours,total_hours"""
    old=db.execute(q,(c,p,w,"old",7.5,u,"legacy",None,None,0,None)).fetchone()
    assert old[:2]==(750,750)
    day=db.execute(q,(c,p,w,"day",9,u,"day","07:00","20:00",60,120)).fetchone()
    assert day[1:]==(1240,10,2,12)
    night=db.execute(q,(c,p,w,"night",9,u,"night","19:00","07:00",0,120)).fetchone()
    assert night[1:]==(1240,10,2,12)


def test_public_cannot_read_driver_tokens_or_submissions_and_rpc_service_only(db):
    for table in ["tipper_driver_links","tipper_portal_links","tipper_submissions","tipper_rate_rules"]:
        assert db.execute("select has_table_privilege('anon',%s,'SELECT')",(table,)).fetchone()[0] is False
    assert db.execute("select has_function_privilege('authenticated','tipper_approve_submission(uuid,jsonb,uuid)','EXECUTE')").fetchone()[0] is False
    assert db.execute("select has_function_privilege('service_role','tipper_approve_submission(uuid,jsonb,uuid)','EXECUTE')").fetchone()[0] is True


def test_private_originals_stay_hidden_even_with_generic_storage_policy(db):
    db.execute("grant usage on schema storage to authenticated")
    db.execute("grant select on storage.objects to authenticated")
    db.execute("create policy generic_storage_read on storage.objects for select to authenticated using(true)")
    db.execute("insert into storage.objects(bucket_id,name) values('tipper-trip-sheets-private','private.pdf'),('other-bucket','unaffected.pdf')")
    db.execute("set local role authenticated")
    assert db.execute("select name from storage.objects").fetchall()==[('unaffected.pdf',)]
    db.execute("reset role")


def test_approval_atomic_idempotent_and_work_date_preserved(db):
    from psycopg.types.json import Jsonb
    u,c,p,w=foundation(db)
    d=db.execute("insert into tipper_drivers(name) values('Driver Test') returning id").fetchone()[0]
    link=db.execute("insert into tipper_driver_links(driver_id,token_hash,created_by) values(%s,'hash',%s) returning id",(d,u)).fetchone()[0]
    s=db.execute("insert into tipper_submissions(driver_id,link_id,file_hash,source_image_key,source_image_url,source_mime,original_name,trip_date,status) values(%s,%s,'file','tipper-trip-sheets/test.pdf','https://files.example/test.pdf','application/pdf','test.pdf','2026-09-30','pending') returning id",(d,link)).fetchone()[0]
    data={"client_id":str(c),"provider_id":str(p),"work_type_id":str(w),"trip_sheet_no":"APPROVE1","trip_date":"2026-09-30","do_no":"DO1","truck_no":"XF1","quantity":1,"unit_type":"hour","transport_rate":100,"site_name":"Site A","billing_mode":"night","start_time":"19:00","end_time":"07:00","break_minutes":0,"ot_rate":120,"rate_snapshot":{}}
    result=db.execute("select tipper_approve_submission(%s,%s,%s)",(s,Jsonb(data),u)).fetchone()[0]
    again=db.execute("select tipper_approve_submission(%s,%s,%s)",(s,Jsonb(data),u)).fetchone()[0]
    assert result['id']==again['id'] and result['billed_amount']==1240 and result['trip_date']=='2026-09-30'
    assert db.execute("select status from tipper_submissions where id=%s",(s,)).fetchone()[0]=='approved'
    assert db.execute("select count(*) from tipper_trips where submission_id=%s",(s,)).fetchone()[0]==1
    assert result['source_image_key']=='tipper-trip-sheets/test.pdf'
