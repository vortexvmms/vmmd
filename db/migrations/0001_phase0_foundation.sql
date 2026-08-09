-- VCMS Phase 0: canonical roles, Projects, legacy mapping, and RLS.
-- Test on a non-production Supabase project before production use.
begin;

create table if not exists public.schema_migrations (
  version text primary key,
  description text not null,
  applied_at timestamptz not null default now()
);
alter table public.schema_migrations enable row level security;

-- Canonical role catalogue. Production already has the expanded constraint;
-- only replace a legacy four-role CHECK when an environment is behind.
do $$
declare constraint_name text;
begin
  if not exists (
    select 1 from pg_constraint
     where conrelid = 'public.users'::regclass and contype = 'c'
       and pg_get_constraintdef(oid) ilike '%general_manager%'
       and pg_get_constraintdef(oid) ilike '%logistics_sup%'
  ) then
    for constraint_name in
      select conname from pg_constraint
       where conrelid = 'public.users'::regclass and contype = 'c'
         and pg_get_constraintdef(oid) ilike '%role%'
    loop
      execute format('alter table public.users drop constraint %I', constraint_name);
    end loop;
    alter table public.users add constraint users_role_check check (role in (
      'admin', 'general_manager', 'operation_manager', 'hr_assistant',
      'main_sup', 'wshc_lead',
      'site_sup', 'safety_sup', 'wshc', 'logistics_sup', 'payroll'
    ));
  end if;
end $$;

create table if not exists public.projects (
  id                    uuid primary key default gen_random_uuid(),
  project_code          text not null unique,
  project_name          text not null,
  description           text,
  client_name           text,
  planned_start_date    date,
  planned_finish_date   date,
  actual_start_date     date,
  actual_finish_date    date,
  status                text not null default 'draft'
                        check (status in ('draft','active','on_hold','completed','archived')),
  default_calendar_id   uuid,
  timezone              text not null default 'Asia/Singapore',
  created_by            uuid references public.users(id),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  archived_at           timestamptz,
  constraint projects_planned_dates check (
    planned_start_date is null or planned_finish_date is null
    or planned_finish_date >= planned_start_date
  ),
  constraint projects_actual_dates check (
    actual_start_date is null or actual_finish_date is null
    or actual_finish_date >= actual_start_date
  )
);

create index if not exists idx_projects_status on public.projects(status);
create index if not exists idx_projects_name on public.projects(project_name);
drop trigger if exists trg_projects_updated on public.projects;
create trigger trg_projects_updated before update on public.projects
for each row execute function public.set_updated_at();

create table if not exists public.project_members (
  project_id    uuid not null references public.projects(id) on delete cascade,
  user_id       uuid not null references public.users(id) on delete cascade,
  access_level  text not null default 'viewer'
                check (access_level in ('viewer','editor','project_admin')),
  created_at    timestamptz not null default now(),
  primary key (project_id, user_id)
);
create index if not exists idx_project_members_user on public.project_members(user_id, project_id);

-- A Project may contain multiple operational Sites. Nullable during legacy
-- reconciliation; new Schedule data must always use project_id.
alter table public.sites add column if not exists project_id uuid;
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'sites_project_id_fkey'
  ) then
    alter table public.sites add constraint sites_project_id_fkey
      foreign key (project_id) references public.projects(id) on delete restrict;
  end if;
end $$;

create index if not exists idx_sites_project on public.sites(project_id);

-- Preserve the legacy DPR directory while linking each record to the
-- canonical Project. This block safely skips installations without that table.
do $$
begin
  if to_regclass('public.dpr_projects') is not null then
    alter table public.dpr_projects add column if not exists project_id uuid;

    -- Equal normalized titles represent the same contractual Project. The
    -- production inventory contains duplicate DPR directory rows for one
    -- title, so title-derived codes prevent duplicate canonical Projects.
    insert into public.projects(project_code, project_name, description, status, created_by)
    select 'DPR-' || upper(substr(md5(lower(trim(coalesce(dp.title, dp.id::text)))), 1, 12)),
           coalesce(nullif(trim(dp.title), ''), 'Legacy DPR Project'),
           max(concat_ws(' | ', nullif(dp.location, ''), nullif(dp.item_of_work, ''))),
           'active', min(dp.created_by::text)::uuid
      from public.dpr_projects dp
     where dp.project_id is null
     group by lower(trim(coalesce(dp.title, dp.id::text))),
              coalesce(nullif(trim(dp.title), ''), 'Legacy DPR Project')
    on conflict (project_code) do nothing;

    update public.dpr_projects dp
       set project_id = p.id
      from public.projects p
     where dp.project_id is null
       and p.project_code = 'DPR-' || upper(substr(md5(lower(trim(coalesce(dp.title, dp.id::text)))), 1, 12));

    update public.sites s
       set project_id = dp.project_id
      from public.dpr_projects dp
     where s.id = dp.site_id and s.project_id is null and dp.project_id is not null;

    if not exists (
      select 1 from pg_constraint where conname = 'dpr_projects_project_id_fkey'
    ) then
      alter table public.dpr_projects add constraint dpr_projects_project_id_fkey
        foreign key (project_id) references public.projects(id) on delete restrict;
    end if;
    create index if not exists idx_dpr_projects_project on public.dpr_projects(project_id);
  end if;
end $$;

-- Any remaining legacy Site receives a canonical Project so no operational
-- history is orphaned. Administrators may merge these records after review.
insert into public.projects(project_code, project_name, status)
select 'SITE-' || upper(s.site_code), s.site_name, 'active'
  from public.sites s
 where s.project_id is null
on conflict (project_code) do nothing;

update public.sites s
   set project_id = p.id
  from public.projects p
 where s.project_id is null and p.project_code = 'SITE-' || upper(s.site_code);

-- Daily reports inherit their canonical Project after every Site has been
-- mapped. Nullable rows identify historical data requiring manual review.
do $$
begin
  if to_regclass('public.daily_reports') is not null then
    alter table public.daily_reports add column if not exists project_id uuid;
    update public.daily_reports dr set project_id = s.project_id
      from public.sites s
     where dr.site_id = s.id and dr.project_id is null and s.project_id is not null;
    if not exists (select 1 from pg_constraint where conname = 'daily_reports_project_id_fkey') then
      alter table public.daily_reports add constraint daily_reports_project_id_fkey
        foreign key (project_id) references public.projects(id) on delete restrict;
    end if;
    create index if not exists idx_daily_reports_project_date
      on public.daily_reports(project_id, report_date);
  end if;
end $$;

create or replace function public.my_project_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
  select p.id
    from public.projects p
   where public.my_role() in (
     'admin','general_manager','operation_manager','hr_assistant',
     'main_sup','wshc_lead','payroll'
   )
  union
  select pm.project_id
    from public.project_members pm
   where pm.user_id = public.my_user_id()
  union
  select s.project_id
    from public.sites s
    join public.site_supervisors ss on ss.site_id = s.id
   where ss.user_id = public.my_user_id() and s.project_id is not null;
$$;

-- Existing production RLS is already expanded across all 21 tables. This
-- migration deliberately leaves those policies untouched and adds only the
-- Project policies below, avoiding duplicate permissive policies.

alter table public.projects enable row level security;
alter table public.project_members enable row level security;

drop policy if exists projects_select_authorized on public.projects;
create policy projects_select_authorized on public.projects for select
using (id in (select public.my_project_ids()));

drop policy if exists projects_insert_management on public.projects;
create policy projects_insert_management on public.projects for insert
with check (public.my_role() in (
  'admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'
));

drop policy if exists projects_update_management on public.projects;
create policy projects_update_management on public.projects for update
using (public.my_role() in (
  'admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'
))
with check (public.my_role() in (
  'admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'
));

drop policy if exists project_members_select_authorized on public.project_members;
create policy project_members_select_authorized on public.project_members for select
using (project_id in (select public.my_project_ids()));

drop policy if exists project_members_manage_management on public.project_members;
create policy project_members_manage_management on public.project_members for all
using (public.my_role() in (
  'admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'
))
with check (public.my_role() in (
  'admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'
));

grant select, insert, update on public.projects to authenticated;
grant select, insert, update, delete on public.project_members to authenticated;
revoke all on public.schema_migrations from anon, authenticated;

insert into public.schema_migrations(version, description)
values ('0001', 'Phase 0 roles, canonical Projects, legacy mapping, and RLS')
on conflict (version) do nothing;

commit;
