-- Disposable local test database only.
create role anon;
create role authenticated;
create role service_role bypassrls;
create schema auth;
create schema storage;
create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
create table storage.objects(id uuid primary key default gen_random_uuid(),bucket_id text,name text);
alter table storage.objects enable row level security;
create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
create table public.users(id uuid primary key,auth_uid uuid,name text,role text);
create function public.my_role() returns text language sql stable security definer set search_path=public,pg_temp as $$select role from public.users where auth_uid=auth.uid()$$;
create function public.my_user_id() returns uuid language sql stable security definer set search_path=public,pg_temp as $$select id from public.users where auth_uid=auth.uid()$$;
create table public.schema_migrations(version text primary key,description text);
grant usage on schema public,auth to anon,authenticated,service_role;
grant select on public.users to authenticated,service_role;
alter default privileges in schema public grant all on tables to anon,authenticated,service_role;
alter default privileges in schema public grant all on functions to anon,authenticated,service_role;
