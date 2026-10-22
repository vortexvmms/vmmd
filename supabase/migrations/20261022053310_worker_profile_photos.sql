begin;
alter table public.workers add column if not exists photo_path text;
alter table public.workers add constraint workers_photo_worker_path check(photo_path is null or photo_path ~ ('^' || id::text || '/[0-9a-f-]{36}\.jpg$'));
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('worker-photos','worker-photos',false,2097152,array['image/jpeg'])
on conflict(id) do update set public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;
-- A restrictive guard prevents older broad permissive storage policies granting access.
create policy worker_photos_guard on storage.objects as restrictive for all to authenticated
 using(bucket_id <> 'worker-photos' or ((select auth.uid()) is not null and public.worker_documents_object_access(name)))
 with check(bucket_id <> 'worker-photos' or ((select auth.uid()) is not null and public.is_full() and public.worker_documents_object_access(name)));
create policy worker_photos_anon_guard on storage.objects as restrictive for all to anon
 using(bucket_id <> 'worker-photos') with check(bucket_id <> 'worker-photos');
create policy worker_photos_read on storage.objects for select to authenticated
 using(bucket_id='worker-photos' and public.worker_documents_object_access(name));
create policy worker_photos_insert on storage.objects for insert to authenticated
 with check(bucket_id='worker-photos' and public.is_full() and public.worker_documents_object_access(name));
-- Portraits use new object names. No client replacement or deletion of existing originals.
create policy worker_photos_no_update on storage.objects as restrictive for update to public
 using(bucket_id <> 'worker-photos') with check(bucket_id <> 'worker-photos');
create policy worker_photos_no_delete on storage.objects as restrictive for delete to public
 using(bucket_id <> 'worker-photos');
commit;
