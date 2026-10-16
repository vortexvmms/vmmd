-- SIC uses VCMS's existing active-user and assigned-site helpers.
-- Additive migration; rollback frontend navigation to hide without deleting records.
begin;
create function public.sic_can_read(p_site uuid) returns boolean language sql stable security invoker set search_path='' as $$
 select coalesce(public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead') or (public.my_role() in ('site_sup','safety_sup','wshc','logistics_sup') and p_site in (select public.my_site_ids())),false)
$$;
create function public.sic_can_manage(p_site uuid) returns boolean language sql stable security invoker set search_path='' as $$
 select public.sic_can_read(p_site) and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','safety_sup','wshc')
$$;
create table public.sic_records (
 id uuid primary key default gen_random_uuid(), worker_id uuid not null references public.workers(id), site_id uuid not null references public.sites(id),
 name text not null check(length(name) between 1 and 250), fin text not null check(length(fin) between 1 and 30), site_name text not null,
 sic_date date not null, validity_months integer check(validity_months between 1 and 120), expiry_date date not null,
 override_reason text not null default '' check(length(override_reason)<=1000), remarks text not null default '' check(length(remarks)<=2000),
 is_current boolean not null default true, archived boolean not null default false,
 created_by uuid not null default auth.uid(), created_at timestamptz not null default now(), updated_by uuid not null default auth.uid(), updated_at timestamptz not null default now(),
 check(expiry_date>=sic_date), unique(worker_id,site_id,sic_date)
);
create unique index sic_one_current_worker on public.sic_records(worker_id,site_id) where is_current and not archived;
create unique index sic_one_current_fin on public.sic_records(lower(fin),site_id) where is_current and not archived;
create unique index sic_unique_course on public.sic_records(lower(fin),site_id,sic_date);
create index sic_site_expiry on public.sic_records(site_id,expiry_date) where is_current and not archived;
create index sic_worker_history on public.sic_records(worker_id,site_id,sic_date desc);
create table public.sic_attachments (
 id uuid primary key default gen_random_uuid(), record_id uuid not null references public.sic_records(id),
 object_key text not null unique, filename text not null check(length(filename) between 1 and 240),
 mime_type text not null check(mime_type in ('application/pdf','image/jpeg','image/png')), file_size integer not null check(file_size between 1 and 20971520),
 created_by uuid not null default auth.uid(), created_at timestamptz not null default now(),
 check(object_key ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}$'), check(split_part(object_key,'/',1)=record_id::text)
);
create index sic_attachment_record on public.sic_attachments(record_id);
create table public.sic_audit (
 id uuid primary key default gen_random_uuid(), record_id uuid not null references public.sic_records(id),
 action text not null, actor uuid not null default auth.uid(), happened_at timestamptz not null default now(), before_data jsonb, after_data jsonb
);
create index sic_audit_record on public.sic_audit(record_id,happened_at desc);
create table public.sic_site_settings(site_id uuid primary key references public.sites(id),validity_months integer not null default 12 check(validity_months between 1 and 120));
alter table public.sic_records enable row level security;
alter table public.sic_attachments enable row level security;
alter table public.sic_audit enable row level security;
alter table public.sic_site_settings enable row level security;
grant select,insert,update on public.sic_records to authenticated;
grant select,insert on public.sic_attachments,public.sic_audit to authenticated;
grant select,insert,update on public.sic_site_settings to authenticated;
revoke all on public.sic_records,public.sic_attachments,public.sic_audit,public.sic_site_settings from anon;
create policy sic_read on public.sic_records for select to authenticated using(public.sic_can_read(site_id));
create policy sic_insert on public.sic_records for insert to authenticated with check(public.sic_can_manage(site_id) and created_by=auth.uid() and updated_by=auth.uid());
create policy sic_update on public.sic_records for update to authenticated using(public.sic_can_manage(site_id)) with check(public.sic_can_manage(site_id) and updated_by=auth.uid());
create policy sic_attachment_read on public.sic_attachments for select to authenticated using(exists(select 1 from public.sic_records r where r.id=record_id));
create policy sic_attachment_insert on public.sic_attachments for insert to authenticated with check(created_by=auth.uid() and exists(select 1 from public.sic_records r where r.id=record_id and public.sic_can_manage(r.site_id)) and exists(select 1 from storage.objects o where o.bucket_id='sic-cards' and o.name=object_key));
create policy sic_audit_read on public.sic_audit for select to authenticated using(exists(select 1 from public.sic_records r where r.id=record_id));
create policy sic_audit_trigger_insert on public.sic_audit for insert to authenticated with check(actor=auth.uid() and pg_trigger_depth()>0 and exists(select 1 from public.sic_records r where r.id=record_id and public.sic_can_manage(r.site_id)));
create policy sic_settings_read on public.sic_site_settings for select to authenticated using(public.sic_can_read(site_id));
create policy sic_settings_insert on public.sic_site_settings for insert to authenticated with check(public.sic_can_manage(site_id));
create policy sic_settings_update on public.sic_site_settings for update to authenticated using(public.sic_can_manage(site_id)) with check(public.sic_can_manage(site_id));
create function public.sic_stamp() returns trigger language plpgsql security invoker set search_path='' as $$
begin
 if TG_OP='UPDATE' then
  if new.worker_id<>old.worker_id or new.site_id<>old.site_id then raise exception 'Worker and site cannot be changed. Create a separate SIC record.'; end if;
  new.created_at:=old.created_at;new.created_by:=old.created_by;
 end if;
 select w.name into new.name from public.workers w where w.id=new.worker_id;
 select s.site_name into new.site_name from public.sites s where s.id=new.site_id;
 new.fin:=upper(trim(new.fin));new.updated_by:=auth.uid();new.updated_at:=now();
 if TG_OP='INSERT' then new.created_by:=auth.uid();new.created_at:=now(); end if;
 if new.sic_date>(now() at time zone 'Asia/Singapore')::date then raise exception 'SIC date cannot be in the future'; end if;
 if new.validity_months is not null and new.expiry_date<>((new.sic_date+make_interval(months=>new.validity_months))::date-1) and trim(new.override_reason)='' then raise exception 'Explain the expiry date override'; end if;
 if new.validity_months is null and trim(new.override_reason)='' then raise exception 'Enter the reason or card reference for a custom expiry date'; end if;
 return new;
end $$;
create trigger sic_record_stamp before insert or update on public.sic_records for each row execute function public.sic_stamp();
create function public.sic_audit_change() returns trigger language plpgsql security invoker set search_path='' as $$
begin
 if TG_TABLE_NAME='sic_records' then
  insert into public.sic_audit(record_id,action,before_data,after_data) values(new.id,case when TG_OP='INSERT' then 'created' when new.archived and not old.archived then 'archived' when not new.is_current and old.is_current then 'superseded' else 'edited' end,case when TG_OP='UPDATE' then to_jsonb(old) end,to_jsonb(new));
 else
  insert into public.sic_audit(record_id,action,after_data) values(new.record_id,'card_uploaded',to_jsonb(new));
 end if;return new;
end $$;
create trigger sic_record_audit after insert or update on public.sic_records for each row execute function public.sic_audit_change();
create trigger sic_attachment_audit after insert on public.sic_attachments for each row execute function public.sic_audit_change();
-- Row lock serializes renewals. Any insert/validation failure rolls back superseding.
create function public.sic_save(p_data jsonb,p_id uuid default null,p_renew uuid default null,p_expected timestamptz default null) returns public.sic_records language plpgsql security invoker set search_path='' as $$
declare r public.sic_records; prior public.sic_records; wid uuid:=(p_data->>'worker_id')::uuid; sid uuid:=(p_data->>'site_id')::uuid;
begin
 if not public.sic_can_manage(sid) then raise insufficient_privilege using message='You cannot manage SIC at this site'; end if;
 perform pg_advisory_xact_lock(hashtextextended(wid::text || sid::text,0));
 if p_id is not null then
  select * into prior from public.sic_records where id=p_id for update;
  if not found or prior.updated_at is distinct from p_expected then raise exception 'This record changed. Refresh and try again.'; end if;
  if not prior.is_current or prior.archived then raise exception 'Historical records cannot be edited'; end if;
  if prior.worker_id<>wid or prior.site_id<>sid then raise exception 'Worker and site cannot be changed'; end if;
  update public.sic_records set fin=p_data->>'fin',sic_date=(p_data->>'sic_date')::date,validity_months=(p_data->>'validity_months')::int,expiry_date=(p_data->>'expiry_date')::date,override_reason=coalesce(p_data->>'override_reason',''),remarks=coalesce(p_data->>'remarks','') where id=p_id returning * into r;
 else
  if p_renew is not null then
   select * into prior from public.sic_records where id=p_renew for update;
   if not found or not prior.is_current or prior.archived or prior.worker_id<>wid or prior.site_id<>sid or prior.updated_at is distinct from p_expected then raise exception 'Renewal record changed. Refresh and try again.'; end if;
   if (p_data->>'sic_date')::date<=prior.sic_date then raise exception 'Renewal SIC date must be later than the previous SIC date'; end if;
   update public.sic_records set is_current=false where id=p_renew;
  end if;
  insert into public.sic_records(worker_id,site_id,name,fin,site_name,sic_date,validity_months,expiry_date,override_reason,remarks)
  values(wid,sid,'pending',p_data->>'fin','pending',(p_data->>'sic_date')::date,(p_data->>'validity_months')::int,(p_data->>'expiry_date')::date,coalesce(p_data->>'override_reason',''),coalesce(p_data->>'remarks','')) returning * into r;
 end if;return r;
end $$;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values('sic-cards','sic-cards',false,20971520,array['application/pdf','image/jpeg','image/png']);
create policy sic_storage_read on storage.objects for select to authenticated using(bucket_id='sic-cards' and exists(select 1 from public.sic_records r where r.id::text=split_part(name,'/',1)));
create policy sic_storage_insert on storage.objects for insert to authenticated with check(bucket_id='sic-cards' and name ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}$' and exists(select 1 from public.sic_records r where r.id::text=split_part(name,'/',1) and public.sic_can_manage(r.site_id)));
create policy sic_storage_cleanup on storage.objects for delete to authenticated using(bucket_id='sic-cards' and owner_id=auth.uid()::text and not exists(select 1 from public.sic_attachments a where a.object_key=name) and exists(select 1 from public.sic_records r where r.id::text=split_part(name,'/',1) and public.sic_can_manage(r.site_id)));
revoke execute on function public.sic_can_read(uuid),public.sic_can_manage(uuid),public.sic_stamp(),public.sic_audit_change(),public.sic_save(jsonb,uuid,uuid,timestamptz) from public,anon;
grant execute on function public.sic_can_read(uuid),public.sic_can_manage(uuid),public.sic_stamp(),public.sic_audit_change(),public.sic_save(jsonb,uuid,uuid,timestamptz) to authenticated;
notify pgrst,'reload schema';
commit;
