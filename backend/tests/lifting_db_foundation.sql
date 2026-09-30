-- Test-only Supabase scaffold. Never apply to production.
create role anon;
create role authenticated;
create schema auth;
create schema storage;
create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
create table public.users(id uuid primary key,auth_uid uuid unique,name text,role text,status text);
create table public.schema_migrations(version text primary key,description text);
create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
create table storage.objects(id uuid primary key default gen_random_uuid(),bucket_id text,name text);
alter table storage.objects enable row level security;
grant usage on schema public,auth,storage to authenticated,anon;
grant select,insert on storage.objects to authenticated;
grant execute on function auth.uid() to authenticated,anon;
