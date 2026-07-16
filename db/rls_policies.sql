-- ============================================================
-- VMMS — rls_policies.sql  ·  Phase 2
-- Row-Level Security per the role matrix, VMMS-SPEC-001 Rev 5 §4.
-- Run SECOND (after schema.sql).
--
-- Notes:
-- · The FastAPI backend (Phase 3+) connects with the SECRET key,
--   which bypasses RLS; the backend enforces the same role rules
--   in code. RLS here is defence-in-depth: it protects against
--   anyone querying the database directly with the public key.
-- · Roles: admin | main_sup | site_sup | payroll
-- ============================================================

-- ---------- helper functions ----------
create or replace function public.my_role()
returns text
language sql
stable
security definer
set search_path = public
as $$
  select role from public.users
  where auth_uid = auth.uid() and status = 'active'
  limit 1;
$$;

create or replace function public.my_user_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select id from public.users
  where auth_uid = auth.uid() and status = 'active'
  limit 1;
$$;

create or replace function public.my_site_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
  select site_id from public.site_supervisors
  where user_id = public.my_user_id();
$$;

-- ---------- enable RLS everywhere ----------
alter table public.users            enable row level security;
alter table public.workers          enable row level security;
alter table public.sites            enable row level security;
alter table public.site_supervisors enable row level security;
alter table public.allocations      enable row level security;
alter table public.attendance       enable row level security;
alter table public.public_holidays  enable row level security;
alter table public.settings         enable row level security;
alter table public.month_locks      enable row level security;
alter table public.audit_log        enable row level security;

-- ============================================================
-- USERS: admin manages; everyone may read their own profile
-- ============================================================
drop policy if exists users_admin_all on public.users;
create policy users_admin_all on public.users
  for all using (public.my_role() = 'admin');

drop policy if exists users_read_self on public.users;
create policy users_read_self on public.users
  for select using (auth_uid = auth.uid());

-- ============================================================
-- WORKERS: admin writes; main_sup may update status (leave);
-- all signed-in roles may read
-- ============================================================
drop policy if exists workers_admin_all on public.workers;
create policy workers_admin_all on public.workers
  for all using (public.my_role() = 'admin');

drop policy if exists workers_read_all on public.workers;
create policy workers_read_all on public.workers
  for select using (public.my_role() is not null);

drop policy if exists workers_mainsup_update on public.workers;
create policy workers_mainsup_update on public.workers
  for update using (public.my_role() = 'main_sup');

-- ============================================================
-- SITES: admin writes; all signed-in roles read
-- ============================================================
drop policy if exists sites_admin_all on public.sites;
create policy sites_admin_all on public.sites
  for all using (public.my_role() = 'admin');

drop policy if exists sites_read_all on public.sites;
create policy sites_read_all on public.sites
  for select using (public.my_role() is not null);

-- ============================================================
-- SITE SUPERVISORS: admin writes; all signed-in roles read
-- ============================================================
drop policy if exists sitesup_admin_all on public.site_supervisors;
create policy sitesup_admin_all on public.site_supervisors
  for all using (public.my_role() = 'admin');

drop policy if exists sitesup_read_all on public.site_supervisors;
create policy sitesup_read_all on public.site_supervisors
  for select using (public.my_role() is not null);

-- ============================================================
-- ALLOCATIONS: admin + main_sup full; site_sup reads own sites;
-- payroll reads all
-- ============================================================
drop policy if exists alloc_admin_mainsup_all on public.allocations;
create policy alloc_admin_mainsup_all on public.allocations
  for all using (public.my_role() in ('admin', 'main_sup'));

drop policy if exists alloc_sitesup_read on public.allocations;
create policy alloc_sitesup_read on public.allocations
  for select using (
    public.my_role() = 'site_sup'
    and site_id in (select public.my_site_ids())
  );

drop policy if exists alloc_payroll_read on public.allocations;
create policy alloc_payroll_read on public.allocations
  for select using (public.my_role() = 'payroll');

-- ============================================================
-- ATTENDANCE: admin full; site_sup reads/updates own sites only;
-- main_sup + payroll read all. No role may DELETE (spec §4).
-- ============================================================
drop policy if exists att_admin_all on public.attendance;
create policy att_admin_all on public.attendance
  for all using (public.my_role() = 'admin');

drop policy if exists att_read_mainsup_payroll on public.attendance;
create policy att_read_mainsup_payroll on public.attendance
  for select using (public.my_role() in ('main_sup', 'payroll'));

drop policy if exists att_sitesup_read on public.attendance;
create policy att_sitesup_read on public.attendance
  for select using (
    public.my_role() = 'site_sup'
    and allocation_id in (
      select a.id from public.allocations a
      where a.site_id in (select public.my_site_ids())
    )
  );

drop policy if exists att_sitesup_update on public.attendance;
create policy att_sitesup_update on public.attendance
  for update using (
    public.my_role() = 'site_sup'
    and allocation_id in (
      select a.id from public.allocations a
      where a.site_id in (select public.my_site_ids())
    )
  );

drop policy if exists att_sitesup_insert on public.attendance;
create policy att_sitesup_insert on public.attendance
  for insert with check (
    public.my_role() in ('admin', 'main_sup', 'site_sup')
  );

-- ============================================================
-- PUBLIC HOLIDAYS / SETTINGS: admin writes; all roles read
-- ============================================================
drop policy if exists ph_admin_all on public.public_holidays;
create policy ph_admin_all on public.public_holidays
  for all using (public.my_role() = 'admin');

drop policy if exists ph_read_all on public.public_holidays;
create policy ph_read_all on public.public_holidays
  for select using (public.my_role() is not null);

drop policy if exists settings_admin_all on public.settings;
create policy settings_admin_all on public.settings
  for all using (public.my_role() = 'admin');

drop policy if exists settings_read_all on public.settings;
create policy settings_read_all on public.settings
  for select using (public.my_role() is not null);

-- ============================================================
-- MONTH LOCKS: admin + payroll manage; others read
-- ============================================================
drop policy if exists ml_admin_payroll_all on public.month_locks;
create policy ml_admin_payroll_all on public.month_locks
  for all using (public.my_role() in ('admin', 'payroll'));

drop policy if exists ml_read_all on public.month_locks;
create policy ml_read_all on public.month_locks
  for select using (public.my_role() is not null);

-- ============================================================
-- AUDIT LOG: any signed-in role may insert; only admin reads;
-- nobody updates or deletes (insert-only by policy absence)
-- ============================================================
drop policy if exists audit_insert_all on public.audit_log;
create policy audit_insert_all on public.audit_log
  for insert with check (public.my_role() is not null);

drop policy if exists audit_admin_read on public.audit_log;
create policy audit_admin_read on public.audit_log
  for select using (public.my_role() = 'admin');

-- ============================================================
-- Done. Now run seed.sql.
-- ============================================================
