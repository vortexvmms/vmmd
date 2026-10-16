-- Qualify object name: sic_records also has a name column.
begin;
alter policy sic_storage_read on storage.objects using(bucket_id='sic-cards' and exists(select 1 from public.sic_records r where r.id::text=split_part(storage.objects.name,'/',1)));
alter policy sic_storage_insert on storage.objects with check(bucket_id='sic-cards' and storage.objects.name ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}$' and exists(select 1 from public.sic_records r where r.id::text=split_part(storage.objects.name,'/',1) and public.sic_can_manage(r.site_id)));
alter policy sic_storage_cleanup on storage.objects using(bucket_id='sic-cards' and owner_id=auth.uid()::text and not exists(select 1 from public.sic_attachments a where a.object_key=storage.objects.name) and exists(select 1 from public.sic_records r where r.id::text=split_part(storage.objects.name,'/',1) and public.sic_can_manage(r.site_id)));
notify pgrst,'reload schema';
commit;
