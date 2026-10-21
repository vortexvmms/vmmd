-- Per-course designation snapshot. Existing records remain explicitly unknown.
-- Compatible with old clients omitting the new JSON key; no row backfill.
-- SECURITY INVOKER, existing grants, site authorization and row locks are retained.
begin;
alter table public.sic_records add column if not exists designation text;
do $$ begin
 if not exists(select 1 from pg_constraint where conrelid='public.sic_records'::regclass and conname='sic_designation_text') then
  alter table public.sic_records add constraint sic_designation_text check(designation is null or (designation=btrim(designation) and char_length(designation) between 1 and 120));
 end if;
end $$;
comment on column public.sic_records.designation is 'Primary designation recorded for this SIC/site. Null means not specified; this is not competency verification.';
create or replace function public.sic_save(p_data jsonb,p_id uuid default null,p_renew uuid default null,p_expected timestamptz default null) returns public.sic_records language plpgsql security invoker set search_path='' as $$
declare r public.sic_records; prior public.sic_records; wid uuid:=(p_data->>'worker_id')::uuid; sid uuid:=(p_data->>'site_id')::uuid; designation_value text;
begin
 if not public.sic_can_manage(sid) then raise insufficient_privilege using message='You cannot manage SIC at this site'; end if;
 if p_data ? 'designation' then
  if jsonb_typeof(p_data->'designation') not in ('string','null') then raise invalid_parameter_value using message='Designation must be text'; end if;
  designation_value:=nullif(btrim(p_data->>'designation'),'');
  if char_length(designation_value)>120 then raise invalid_parameter_value using message='Designation must be at most 120 characters'; end if;
 end if;
 perform pg_advisory_xact_lock(hashtextextended(wid::text || sid::text,0));
 if p_id is not null then
  select * into prior from public.sic_records where id=p_id for update;
  if not found or prior.updated_at is distinct from p_expected then raise exception 'This record changed. Refresh and try again.'; end if;
  if not prior.is_current or prior.archived then raise exception 'Historical records cannot be edited'; end if;
  if prior.worker_id<>wid or prior.site_id<>sid then raise exception 'Worker and site cannot be changed'; end if;
  if p_data ? 'designation' and designation_value is null and prior.designation is not null then raise invalid_parameter_value using message='Designation cannot be cleared'; end if;
  update public.sic_records set designation=case when p_data ? 'designation' then designation_value else designation end,fin=p_data->>'fin',sic_date=(p_data->>'sic_date')::date,validity_months=(p_data->>'validity_months')::int,expiry_date=(p_data->>'expiry_date')::date,override_reason=coalesce(p_data->>'override_reason',''),remarks=coalesce(p_data->>'remarks','') where id=p_id returning * into r;
 else
  -- Missing key keeps old clients compatible during rollout. New clients send it.
  if p_data ? 'designation' and designation_value is null then raise invalid_parameter_value using message='Select a designation for this SIC entry'; end if;
  if p_renew is not null then
   select * into prior from public.sic_records where id=p_renew for update;
   if not found or not prior.is_current or prior.archived or prior.worker_id<>wid or prior.site_id<>sid or prior.updated_at is distinct from p_expected then raise exception 'Renewal record changed. Refresh and try again.'; end if;
   if (p_data->>'sic_date')::date<=prior.sic_date then raise exception 'Renewal SIC date must be later than the previous SIC date'; end if;
   update public.sic_records set is_current=false where id=p_renew;
  end if;
  insert into public.sic_records(worker_id,site_id,name,fin,site_name,sic_date,validity_months,expiry_date,override_reason,remarks,designation)
  values(wid,sid,'pending',p_data->>'fin','pending',(p_data->>'sic_date')::date,(p_data->>'validity_months')::int,(p_data->>'expiry_date')::date,coalesce(p_data->>'override_reason',''),coalesce(p_data->>'remarks',''),designation_value) returning * into r;
 end if;return r;
end $$;
notify pgrst,'reload schema';
commit;
