-- Run after the SIC migration inside a transaction, then ROLLBACK.
-- Uses existing worker/site IDs only as references; never alters their data.
select set_config('sic.test_admin',(select auth_uid::text from public.users where role='admin' and status='active' and auth_uid is not null limit 1),true);
select set_config('sic.test_worker',(select id::text from public.workers order by id limit 1),true);
select set_config('sic.test_site',(select id::text from public.sites order by id limit 1),true);
select set_config('request.jwt.claim.sub',current_setting('sic.test_admin'),true);
set local role authenticated;
do $$
declare r public.sic_records; n public.sic_records; data jsonb; passed int:=0;
begin
 data:=jsonb_build_object('worker_id',current_setting('sic.test_worker'),'site_id',current_setting('sic.test_site'),'fin','SIC-TEST-ONLY','sic_date','2025-01-01','validity_months',12,'expiry_date','2025-12-31');
 r:=public.sic_save(data);passed:=passed+1;
 if not exists(select 1 from public.sic_audit where record_id=r.id and action='created' and actor=auth.uid()) then raise exception 'Audit missing'; end if;passed:=passed+1;
 begin perform public.sic_save(data);raise exception 'Duplicate accepted';exception when unique_violation then passed:=passed+1;end;
 begin perform public.sic_save(data||'{"sic_date":"2026-01-01","expiry_date":"2026-12-30"}'::jsonb,null,r.id,r.updated_at);raise exception 'Override accepted without reason';exception when raise_exception then if SQLERRM='Override accepted without reason' then raise;end if;passed:=passed+1;end;
 if not exists(select 1 from public.sic_records where id=r.id and is_current) then raise exception 'Failed renewal superseded current record';end if;passed:=passed+1;
 n:=public.sic_save(data||'{"sic_date":"2026-01-01","expiry_date":"2026-12-31"}'::jsonb,null,r.id,r.updated_at);
 if (select count(*) from public.sic_records where worker_id=r.worker_id and site_id=r.site_id and is_current)<>1 or (select is_current from public.sic_records where id=r.id) then raise exception 'Renewal history invalid'; end if;passed:=passed+1;
 begin perform public.sic_save(data||'{"sic_date":"2026-01-01","expiry_date":"2026-12-31"}'::jsonb,n.id,null,'2000-01-01'::timestamptz);raise exception 'Stale edit accepted';exception when raise_exception then if SQLERRM='Stale edit accepted' then raise;end if;passed:=passed+1;end;
 begin insert into public.sic_audit(record_id,action) values(n.id,'forged');raise exception 'Audit spoof accepted';exception when insufficient_privilege then passed:=passed+1;end;
 begin insert into public.sic_attachments(record_id,object_key,filename,mime_type,file_size) values(n.id,n.id::text||'/'||gen_random_uuid()::text,'missing.pdf','application/pdf',20);raise exception 'Missing object accepted';exception when insufficient_privilege then passed:=passed+1;end;
 perform set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000099',true);
 if exists(select 1 from public.sic_records) then raise exception 'Unregistered account can read';end if;passed:=passed+1;
 begin perform public.sic_save(data);raise exception 'Unregistered account can write';exception when insufficient_privilege then passed:=passed+1;end;
 perform set_config('request.jwt.claim.sub',current_setting('sic.test_admin'),true);
 raise notice 'SIC checks passed: %',passed;
end $$;
reset role;
select '11 SIC database checks passed; transaction will roll back' as result;
