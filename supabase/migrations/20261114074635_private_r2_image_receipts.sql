begin;

-- Only the backend service can attest to a successful R2 write.
create table public.private_r2_image_receipts (
 bucket_id text not null check (bucket_id in ('worker-cards', 'sic-cards')),
 object_key text not null,
 uploader uuid not null,
 primary key (bucket_id, object_key, uploader)
);
alter table public.private_r2_image_receipts enable row level security;
revoke all on public.private_r2_image_receipts from public, anon, authenticated;
grant select on public.private_r2_image_receipts to authenticated;
grant select, insert, delete on public.private_r2_image_receipts to service_role;
create policy private_r2_receipt_owner on public.private_r2_image_receipts
 for select to authenticated using (uploader = (select auth.uid()));

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
      or not (
       exists(select 1 from storage.objects o where o.bucket_id='worker-cards' and o.name=key)
       or exists(select 1 from public.private_r2_image_receipts r where r.bucket_id='worker-cards' and r.object_key=key and r.uploader=auth.uid())
      ) then
    raise exception 'Attach an uploaded private original for this worker';
   end if;
  end if;
 end loop;
 new.updated_at:=clock_timestamp();
 return new;
end $$;

alter policy sic_attachment_insert on public.sic_attachments with check (
 created_by=auth.uid()
 and exists(select 1 from public.sic_records r where r.id=record_id and public.sic_can_manage(r.site_id))
 and (
  exists(select 1 from storage.objects o where o.bucket_id='sic-cards' and o.name=object_key)
  or exists(select 1 from public.private_r2_image_receipts receipt
            where receipt.bucket_id='sic-cards' and receipt.object_key=sic_attachments.object_key and receipt.uploader=auth.uid())
 )
);

commit;
