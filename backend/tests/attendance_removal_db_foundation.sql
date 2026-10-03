-- Disposable test database only: use the real base schema and minimal Auth roles.
create role anon;
create role authenticated;
create role service_role;
create schema auth;
create table auth.users(id uuid primary key);
