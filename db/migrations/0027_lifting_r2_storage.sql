-- New LG original certificates reside in private Cloudflare R2.
-- Legacy LM/LG originals remain in Supabase Storage and continue to be readable.
begin;
alter table public.lifting_documents
  add column if not exists storage_backend text not null default 'supabase'
  check (storage_backend in ('supabase','r2'));
create index if not exists lifting_documents_storage_backend_idx
  on public.lifting_documents(storage_backend);
insert into public.schema_migrations(version,description)
values ('0027','Track private Cloudflare R2 storage for new LG certificates')
on conflict (version) do nothing;
commit;
