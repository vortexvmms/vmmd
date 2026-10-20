-- Restore access without changing historical rows or their file locations.
begin;
create or replace function public.worker_documents_can_access(p_worker uuid)
returns boolean language sql stable security invoker set search_path = '' as $$
 select coalesce((select auth.uid()) is not null and (
  public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead')
  or (public.my_role() in ('site_sup','safety_sup','wshc','logistics_sup') and exists (
   select 1 from public.allocations a where a.worker_id=p_worker
    and a.work_date=(now() at time zone 'Asia/Singapore')::date
    and a.site_id in (select public.my_site_ids())
  ))),false) and exists(select 1 from public.workers w where w.id=p_worker)
$$;
revoke all on function public.worker_documents_can_access(uuid) from public,anon;
grant execute on function public.worker_documents_can_access(uuid) to authenticated;
create or replace function public.worker_documents_workers(p_search text default '',p_offset integer default 0)
returns table(id uuid,worker_code text,name text,status text)
language sql stable security invoker set search_path = '' as $$
 select w.id,w.worker_code,w.name,w.status from public.workers w
 where public.worker_documents_can_access(w.id)
 and (strpos(lower(w.name),lower(left(coalesce(p_search,''),200)))>0
      or strpos(lower(w.worker_code),lower(left(coalesce(p_search,''),200)))>0)
 order by w.name,w.id limit 50 offset greatest(0,least(coalesce(p_offset,0),100000))
$$;
revoke all on function public.worker_documents_workers(text,integer) from public,anon;
grant execute on function public.worker_documents_workers(text,integer) to authenticated;
alter table public.worker_certificates add column if not exists updated_at timestamptz not null default now();
alter table public.worker_cards enable row level security;
alter table public.worker_certificates enable row level security;
drop policy if exists worker_cards_all on public.worker_cards;
drop policy if exists worker_certs_all on public.worker_certificates;
drop policy if exists worker_documents_cards on public.worker_cards;
create policy worker_documents_cards on public.worker_cards for all to authenticated
 using(public.worker_documents_can_access(worker_id)) with check(public.worker_documents_can_access(worker_id));
drop policy if exists worker_documents_certificates on public.worker_certificates;
create policy worker_documents_certificates on public.worker_certificates for all to authenticated
 using(public.worker_documents_can_access(worker_id)) with check(public.worker_documents_can_access(worker_id));
revoke all on public.worker_cards,public.worker_certificates from anon,authenticated;
grant select,insert,update on public.worker_cards,public.worker_certificates to authenticated;
create or replace function public.worker_documents_object_access(p_name text)
returns boolean language plpgsql stable security invoker set search_path = '' as $$
begin
 if p_name !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f-]{36}\.(jpg|png|pdf)$' then return false; end if;
 return public.worker_documents_can_access(split_part(p_name,'/',1)::uuid);
end $$;
revoke all on function public.worker_documents_object_access(text) from public,anon;
grant execute on function public.worker_documents_object_access(text) to authenticated;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('worker-cards','worker-cards',false,20971520,array['image/jpeg','image/png','application/pdf'])
on conflict(id) do update set public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
drop policy if exists worker_documents_read on storage.objects;
create policy worker_documents_read on storage.objects for select to authenticated
 using(bucket_id='worker-cards' and public.worker_documents_object_access(name));
drop policy if exists worker_documents_upload on storage.objects;
create policy worker_documents_upload on storage.objects for insert to authenticated
 with check(bucket_id='worker-cards' and public.worker_documents_object_access(name));
create or replace function public.worker_documents_check_record()
returns trigger language plpgsql security invoker set search_path = '' as $$
declare key text; old_key text; field text; fields text[];
begin
 if tg_op='INSERT' then new.uploaded_by:=public.my_user_id(); end if;
 if tg_op='UPDATE' and (new.id<>old.id or new.worker_id<>old.worker_id or new.uploaded_by is distinct from old.uploaded_by or new.created_at<>old.created_at) then
  raise exception 'Worker document identity cannot be changed';
 end if;
 fields:=case when tg_table_name='worker_cards' then array['image_path','back_image_path'] else array['file_path'] end;
 foreach field in array fields loop
  key:=to_jsonb(new)->>field;old_key:=null;
  if tg_op='UPDATE' then old_key:=to_jsonb(old)->>field; end if;
  if key is distinct from old_key and key is not null then
   if split_part(key,'/',1)<>new.worker_id::text or not public.worker_documents_object_access(key)
      or not exists(select 1 from storage.objects o where o.bucket_id='worker-cards' and o.name=key) then
    raise exception 'Attach an uploaded private original for this worker';
   end if;
  end if;
 end loop;
 new.updated_at:=clock_timestamp();
 return new;
end $$;
revoke all on function public.worker_documents_check_record() from public,anon;
drop trigger if exists trg_touch_worker_cards on public.worker_cards;
drop function if exists public.touch_worker_cards();
drop trigger if exists worker_documents_check on public.worker_cards;
create trigger worker_documents_check before insert or update on public.worker_cards for each row execute function public.worker_documents_check_record();
drop trigger if exists worker_documents_check on public.worker_certificates;
create trigger worker_documents_check before insert or update on public.worker_certificates for each row execute function public.worker_documents_check_record();
commit;
