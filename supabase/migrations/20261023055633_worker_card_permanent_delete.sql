begin;
-- Storage identities are canonical across the retired and active Supabase hosts.
create or replace function public.worker_card_file_identity(p_path text)
returns text language sql immutable security invoker set search_path='' as $$
 select case
 when p_path ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}\.(jpg|png|pdf)$' then 'worker-cards/'||p_path
 when p_path ~ '^https://(lqnbdemtgkermhaqfboh|dyfwyhpbffnzxfnwjfxg)\.supabase\.co/storage/v1/object/public/dpr-photos/worker-cards/[0-9a-f-]{36}/[A-Za-z0-9_.-]+$'
 then 'dpr-photos/'||split_part(p_path,'/dpr-photos/',2)
 else p_path end
$$;
revoke all on function public.worker_card_file_identity(text) from public,anon;
grant execute on function public.worker_card_file_identity(text) to authenticated;

-- This is an audit receipt and durable cleanup outbox, not a recoverable card.
create table public.worker_card_deletions(
 record_id uuid primary key, worker_id uuid not null, title text not null,
 deleted_by uuid not null references public.users(id), deleted_at timestamptz not null default now(),
 pending_paths text[] not null default '{}', retained_shared integer not null default 0,
 completed_at timestamptz
);
alter table public.worker_card_deletions enable row level security;
revoke all on public.worker_card_deletions from public,anon,authenticated;
grant select on public.worker_card_deletions to authenticated;
create policy worker_card_deletions_read on public.worker_card_deletions for select to authenticated
 using(auth.uid() is not null and public.my_role() in ('admin','hr_assistant'));

-- No raw DELETE grant is added. This narrow RPC validates confirmation, role and version.
create or replace function public.worker_card_delete(p_id uuid,p_updated_at timestamptz,p_confirmation text)
returns public.worker_card_deletions language plpgsql security definer set search_path='' as $$
declare c public.worker_cards; receipt public.worker_card_deletions; paths text[]; pending text[]; shared integer;
begin
 if auth.uid() is null or coalesce(public.my_role(),'') not in ('admin','hr_assistant') then raise insufficient_privilege using message='Only Admin and HR can permanently delete cards';end if;
 if p_confirmation is distinct from 'DELETE' then raise invalid_parameter_value using message='Type DELETE to confirm';end if;
 -- Serializes attachment changes until the outbox and card removal commit together.
 lock table public.worker_cards,public.worker_certificates in share row exclusive mode;
 select * into c from public.worker_cards where id=p_id for update;
 if not found then
  select * into receipt from public.worker_card_deletions where record_id=p_id;
  if found then return receipt;end if;
  raise no_data_found using message='Card not found';
 end if;
 if c.updated_at is distinct from p_updated_at then raise serialization_failure using message='This card changed. Refresh before deleting it';end if;
 select array_agg(distinct path) filter(where path is not null and path<>'') into paths from (
  select c.image_path as path union all select c.back_image_path
  union all select v.data->>f.field from public.audit_log a
   cross join lateral (values(a.old_value),(a.new_value)) v(data)
   cross join (values('image_path'),('back_image_path')) f(field)
   where a.entity='worker_cards' and a.entity_id=p_id::text
 ) versions;
 select coalesce(array_agg(p), '{}'), count(*) filter(where false) into pending,shared from unnest(coalesce(paths,'{}')) p where not exists(
  select 1 from public.worker_cards r cross join lateral (values(r.image_path),(r.back_image_path)) f(path)
   where r.id<>p_id and public.worker_card_file_identity(f.path)=public.worker_card_file_identity(p)
  union all select 1 from public.worker_certificates r where public.worker_card_file_identity(r.file_path)=public.worker_card_file_identity(p)
 );
 shared:=coalesce(array_length(paths,1),0)-coalesce(array_length(pending,1),0);
 insert into public.worker_card_deletions(record_id,worker_id,title,deleted_by,pending_paths,retained_shared,completed_at)
 values(c.id,c.worker_id,coalesce(c.label,c.category,'Card'),public.my_user_id(),pending,shared,case when cardinality(pending)=0 then now() end) returning * into receipt;
 insert into public.audit_log(user_id,action,entity,entity_id,old_value,new_value)
 values(public.my_user_id(),'delete','worker_cards',c.id::text,jsonb_build_object('worker_id',c.worker_id,'label',c.label,'category',c.category),jsonb_build_object('permanent',true,'cleanup_record',c.id));
 delete from public.worker_cards where id=c.id;
 return receipt;
end $$;
revoke all on function public.worker_card_delete(uuid,timestamptz,text) from public,anon,authenticated;
grant execute on function public.worker_card_delete(uuid,timestamptz,text) to authenticated;

-- Reject attempts to reattach files already queued for removal, including older clients.
create or replace function public.worker_card_pending_file_guard()
returns trigger language plpgsql security definer set search_path='' as $$
declare path text;
begin
 for path in select value from jsonb_each_text(to_jsonb(new)) where key in ('image_path','back_image_path','file_path') loop
  if exists(select 1 from public.worker_card_deletions d,unnest(d.pending_paths) p where public.worker_card_file_identity(p)=public.worker_card_file_identity(path)) then
   raise check_violation using message='This photo is pending permanent removal. Upload a new file';
  end if;
 end loop;
 return new;
end $$;
revoke all on function public.worker_card_pending_file_guard() from public,anon,authenticated;
create trigger worker_card_pending_file_guard before insert or update on public.worker_cards for each row execute function public.worker_card_pending_file_guard();
create trigger worker_certificate_pending_file_guard before insert or update on public.worker_certificates for each row execute function public.worker_card_pending_file_guard();

create or replace function public.worker_card_cleanup_object(p_bucket text,p_name text)
returns boolean language sql stable security invoker set search_path='' as $$
 select auth.uid() is not null and public.my_role() in ('admin','hr_assistant') and exists(
  select 1 from public.worker_card_deletions d,unnest(d.pending_paths) p
  where public.worker_card_file_identity(p)=p_bucket||'/'||p_name
  and ((p_bucket='worker-cards' and p_name like d.worker_id::text||'/%') or (p_bucket='dpr-photos' and p_name like 'worker-cards/'||d.worker_id::text||'/%'))
 )
$$;
revoke all on function public.worker_card_cleanup_object(text,text) from public,anon;
grant execute on function public.worker_card_cleanup_object(text,text) to authenticated;
create policy worker_card_cleanup_read on storage.objects for select to authenticated
 using(public.worker_card_cleanup_object(bucket_id,name));
create policy worker_card_cleanup_delete on storage.objects for delete to authenticated
 using(public.worker_card_cleanup_object(bucket_id,name));
-- Prevent another permissive policy from opening arbitrary card-file deletion.
create policy worker_card_cleanup_delete_guard on storage.objects as restrictive for delete to authenticated
 using(case when bucket_id='worker-cards' or bucket_id='dpr-photos' and name like 'worker-cards/%' then public.worker_card_cleanup_object(bucket_id,name) else true end);

create or replace function public.worker_card_cleanup_done(p_id uuid,p_path text)
returns public.worker_card_deletions language plpgsql security definer set search_path='' as $$
declare d public.worker_card_deletions; identity text;
begin
 if auth.uid() is null or coalesce(public.my_role(),'') not in ('admin','hr_assistant') then raise insufficient_privilege;end if;
 select * into d from public.worker_card_deletions where record_id=p_id for update;
 if not found then raise no_data_found;end if;
 identity:=public.worker_card_file_identity(p_path);
 if (identity like 'worker-cards/%' or identity like 'dpr-photos/%') and exists(select 1 from storage.objects o where o.bucket_id||'/'||o.name=identity) then
  raise check_violation using message='Photo removal has not completed';
 end if;
 update public.worker_card_deletions set pending_paths=array_remove(pending_paths,p_path),
  completed_at=case when cardinality(array_remove(pending_paths,p_path))=0 then coalesce(completed_at,clock_timestamp()) end
 where record_id=p_id returning * into d;
 return d;
end $$;
revoke all on function public.worker_card_cleanup_done(uuid,text) from public,anon,authenticated;
grant execute on function public.worker_card_cleanup_done(uuid,text) to authenticated;
commit;
