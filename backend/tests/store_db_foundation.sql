create schema auth;
create role anon;
create role authenticated;
create function auth.uid() returns uuid language sql stable
as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
create table public.users(id uuid primary key,auth_uid uuid unique,name text,role text,status text,menu jsonb);
create table public.sites(id uuid primary key,site_name text,status text,removed_at timestamptz);
create table public.site_supervisors(site_id uuid references public.sites,user_id uuid references public.users,primary key(site_id,user_id));
