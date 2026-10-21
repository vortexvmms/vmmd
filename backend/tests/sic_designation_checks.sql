-- Execute in a transaction and ROLLBACK. No directory data is changed.
select set_config('request.jwt.claim.sub',(select auth_uid::text from public.users where role='admin' and status='active' and auth_uid is not null limit 1),true);
select set_config('sic.designation_worker',w.id::text,true),set_config('sic.designation_site',s.id::text,true)
from public.workers w cross join public.sites s
where not exists(select 1 from public.sic_records r where r.worker_id=w.id and r.site_id=s.id)
order by w.id,s.id limit 1;
set local role authenticated;
do $$
declare data jsonb; r public.sic_records; n public.sic_records; passed integer:=0;
begin
 data:=jsonb_build_object('worker_id',current_setting('sic.designation_worker'),'site_id',current_setting('sic.designation_site'),'fin','DSG-QA-'||left(replace(gen_random_uuid()::text,'-',''),20),'sic_date','2024-01-01','validity_months',12,'expiry_date','2024-12-31');
 -- An old client omitting the key keeps working and remains explicitly unknown.
 r:=public.sic_save(data);if r.designation is not null then raise exception 'Legacy designation was invented';end if;passed:=passed+1;
 r:=public.sic_save(data||jsonb_build_object('designation',null),r.id,null,r.updated_at);if r.designation is not null then raise exception 'Legacy edit requires a fabricated designation';end if;passed:=passed+1;
 r:=public.sic_save(data||jsonb_build_object('designation','Welder'),r.id,null,r.updated_at);if r.designation<>'Welder' then raise exception 'Designation not saved';end if;passed:=passed+1;
 r:=public.sic_save(data,r.id,null,r.updated_at);if r.designation<>'Welder' then raise exception 'Old client cleared saved designation';end if;passed:=passed+1;
 begin perform public.sic_save(data||jsonb_build_object('designation',''),r.id,null,r.updated_at);raise exception 'Blank designation accepted';exception when invalid_parameter_value then passed:=passed+1;end;
 begin perform public.sic_save(data||jsonb_build_object('designation',jsonb_build_array('Welder')),r.id,null,r.updated_at);raise exception 'Array designation accepted';exception when invalid_parameter_value then passed:=passed+1;end;
 begin perform public.sic_save(data||jsonb_build_object('designation',repeat('x',121)),r.id,null,r.updated_at);raise exception 'Oversize designation accepted';exception when invalid_parameter_value then passed:=passed+1;end;
 data:=data||jsonb_build_object('sic_date','2025-01-01','expiry_date','2025-12-31');
 begin perform public.sic_save(data||jsonb_build_object('designation',null),null,r.id,r.updated_at);raise exception 'New entry accepted without designation';exception when invalid_parameter_value then passed:=passed+1;end;
 if not exists(select 1 from public.sic_records where id=r.id and is_current and designation='Welder') then raise exception 'Rejected renewal changed the previous course';end if;passed:=passed+1;
 n:=public.sic_save(data||jsonb_build_object('designation','Rigger & Signalman'),null,r.id,r.updated_at);
 if n.designation<>'Rigger & Signalman' or not exists(select 1 from public.sic_records where id=r.id and not is_current and designation='Welder') then raise exception 'Renewal overwrote designation history';end if;passed:=passed+1;
 n:=public.sic_save(data||jsonb_build_object('designation','Specialist Technician'),n.id,null,n.updated_at);if n.designation<>'Specialist Technician' then raise exception 'Custom designation lost';end if;passed:=passed+1;
 if not exists(select 1 from public.sic_audit where record_id=n.id and after_data->>'designation'='Specialist Technician') then raise exception 'Designation missing from audit evidence';end if;passed:=passed+1;
 perform set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000099',true);
 if exists(select 1 from public.sic_records where id=n.id) then raise exception 'Unregistered account read designation';end if;passed:=passed+1;
 begin perform public.sic_save(data||jsonb_build_object('designation','Driver'),n.id,null,n.updated_at);raise exception 'Unregistered account updated designation';exception when insufficient_privilege then passed:=passed+1;end;
 raise notice 'SIC designation checks passed: %',passed;
end $$;
reset role;
do $$ begin
 if (select prosecdef from pg_proc where oid='public.sic_save(jsonb,uuid,uuid,timestamptz)'::regprocedure) then raise exception 'SIC save gained definer authority';end if;
 if has_function_privilege('anon','public.sic_save(jsonb,uuid,uuid,timestamptz)','execute') or not has_function_privilege('authenticated','public.sic_save(jsonb,uuid,uuid,timestamptz)','execute') then raise exception 'SIC save grants changed';end if;
 if not (select relrowsecurity from pg_class where oid='public.sic_records'::regclass) then raise exception 'SIC row security disabled';end if;
end $$;
select 'SIC designation checks passed; transaction must roll back' as result;
