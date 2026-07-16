-- ============================================================
-- VMMS — Vortex Manpower Management System
-- schema.sql  ·  Phase 2  ·  VMMS-SPEC-001 Rev 5 §14
-- Run FIRST in Supabase SQL Editor.
-- Safe to re-run: uses IF NOT EXISTS where possible.
-- ============================================================

-- ---------- helper: auto-update the updated_at column ----------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ============================================================
-- 1. USERS  (app profile linked to Supabase Auth login)
-- ============================================================
create table if not exists public.users (
  id          uuid primary key default gen_random_uuid(),
  auth_uid    uuid unique references auth.users (id) on delete set null,
  name        text not null,
  role        text not null check (role in ('admin', 'main_sup', 'site_sup', 'payroll')),
  status      text not null default 'active' check (status in ('active', 'inactive')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

drop trigger if exists trg_users_updated on public.users;
create trigger trg_users_updated
  before update on public.users
  for each row execute function public.set_updated_at();

-- ============================================================
-- 2. WORKERS  (worker master — no hard delete, spec FR-2)
--    status: on_leave = overseas home leave (Rev 3 decision)
--    trade: unused in v1, kept nullable for future (Rev 4)
-- ============================================================
create table if not exists public.workers (
  id           uuid primary key default gen_random_uuid(),
  worker_code  text not null unique,
  name         text not null,
  trade        text,
  status       text not null default 'active' check (status in ('active', 'on_leave', 'inactive')),
  created_by   uuid references public.users (id),
  updated_by   uuid references public.users (id),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists idx_workers_name   on public.workers (name);
create index if not exists idx_workers_status on public.workers (status);

drop trigger if exists trg_workers_updated on public.workers;
create trigger trg_workers_updated
  before update on public.workers
  for each row execute function public.set_updated_at();

-- ============================================================
-- 3. SITES  (site master — archive, never delete, spec FR-3)
-- ============================================================
create table if not exists public.sites (
  id          uuid primary key default gen_random_uuid(),
  site_code   text not null unique,
  site_name   text not null,
  status      text not null default 'active' check (status in ('active', 'archived')),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

drop trigger if exists trg_sites_updated on public.sites;
create trigger trg_sites_updated
  before update on public.sites
  for each row execute function public.set_updated_at();

-- ============================================================
-- 4. SITE SUPERVISORS  (who may update which site — drives RLS)
-- ============================================================
create table if not exists public.site_supervisors (
  site_id   uuid not null references public.sites (id) on delete cascade,
  user_id   uuid not null references public.users (id) on delete cascade,
  primary key (site_id, user_id)
);

-- ============================================================
-- 5. ALLOCATIONS  (one worker → one site → one date)
--    UNIQUE (work_date, worker_id) is the database-level
--    guarantee behind spec rule FR-4.2 (no double allocation).
-- ============================================================
create table if not exists public.allocations (
  id          uuid primary key default gen_random_uuid(),
  work_date   date not null,
  site_id     uuid not null references public.sites (id),
  worker_id   uuid not null references public.workers (id),
  status      text not null default 'allocated' check (status in ('allocated', 'cancelled')),
  created_by  uuid references public.users (id),
  updated_by  uuid references public.users (id),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint uq_one_site_per_day unique (work_date, worker_id)
);

create index if not exists idx_alloc_date       on public.allocations (work_date);
create index if not exists idx_alloc_site_date  on public.allocations (site_id, work_date);

drop trigger if exists trg_alloc_updated on public.allocations;
create trigger trg_alloc_updated
  before update on public.allocations
  for each row execute function public.set_updated_at();

-- ============================================================
-- 6. ATTENDANCE  (one row per allocation; hours computed by
--    the backend OT engine per spec §6; day_type frozen at calc)
-- ============================================================
create table if not exists public.attendance (
  id             uuid primary key default gen_random_uuid(),
  allocation_id  uuid not null unique references public.allocations (id) on delete cascade,
  present        boolean not null default true,
  start_time     time not null default '08:00',
  end_time       time,
  end_next_day   boolean not null default false,   -- past-midnight jobs (FR-6.3)
  normal_hours   numeric(4,2) not null default 0,
  ot_hours       numeric(4,2) not null default 0,
  day_type       text check (day_type in ('WD', 'SAT', 'SUN', 'PH')),
  submitted_at   timestamptz,
  submitted_by   uuid references public.users (id),
  edit_reason    text,                              -- mandatory on post-submit edits
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

drop trigger if exists trg_att_updated on public.attendance;
create trigger trg_att_updated
  before update on public.attendance
  for each row execute function public.set_updated_at();

-- ============================================================
-- 7. PUBLIC HOLIDAYS  (Singapore, Admin-maintained yearly)
-- ============================================================
create table if not exists public.public_holidays (
  holiday_date  date primary key,
  description   text not null
);

-- ============================================================
-- 8. SETTINGS  (OT parameters, message templates — spec §6.2)
-- ============================================================
create table if not exists public.settings (
  key             text primary key,
  value           jsonb not null,
  effective_from  date,
  updated_at      timestamptz not null default now()
);

drop trigger if exists trg_settings_updated on public.settings;
create trigger trg_settings_updated
  before update on public.settings
  for each row execute function public.set_updated_at();

-- ============================================================
-- 9. MONTH LOCKS  (payroll month closing — spec §9.1)
-- ============================================================
create table if not exists public.month_locks (
  month      date primary key,          -- always the 1st of the month
  locked_by  uuid references public.users (id),
  locked_at  timestamptz not null default now()
);

-- ============================================================
-- 10. AUDIT LOG  (insert-only — spec §10)
-- ============================================================
create table if not exists public.audit_log (
  id          bigint generated always as identity primary key,
  user_id     uuid references public.users (id),
  action      text not null,
  entity      text not null,
  entity_id   text,
  old_value   jsonb,
  new_value   jsonb,
  ip          text,
  at          timestamptz not null default now()
);

create index if not exists idx_audit_at     on public.audit_log (at);
create index if not exists idx_audit_entity on public.audit_log (entity, entity_id);

-- ============================================================
-- Done. Now run rls_policies.sql, then seed.sql.
-- ============================================================
