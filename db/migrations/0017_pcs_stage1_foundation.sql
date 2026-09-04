-- VCMS PCS Multi-Location DPR — Stage 1: configuration + data foundation.
-- Additive only. Creates the DPR mode flag and the PCS parent/child data model.
-- No existing rows are rewritten; existing DPR behaviour is unchanged until an
-- administrator sets a project's dpr_mode to 'multi_location'.
-- Test on a non-production Supabase project before production use.
begin; set local check_function_bodies = off;

-- ---------------------------------------------------------------------------
-- 1. DPR Mode flag (Section 2). Lives on the canonical Project so every DPR for
--    that project resolves one mode. Existing rows default to 'standard', so
--    the current Standard DPR workflow is untouched.
-- ---------------------------------------------------------------------------
alter table public.projects
  add column if not exists dpr_mode text not null default 'standard'
  check (dpr_mode in ('standard','multi_location'));

-- ---------------------------------------------------------------------------
-- 2. Permission helper: locations a user may operate on. Supervisors get their
--    assigned locations; management/full roles get every location in projects
--    they can already see. Mirrors public.my_project_ids().
-- ---------------------------------------------------------------------------
create or replace function public.my_pcs_location_ids()
returns setof uuid
language sql
stable
security definer
set search_path = public
as $$
  select l.id
  from public.pcs_work_locations l
  where l.project_id in (select public.my_project_ids())
    and public.my_role() in (
      'admin','general_manager','operation_manager','hr_assistant',
      'main_sup','wshc_lead'
    )
  union
  select ls.location_id
  from public.pcs_location_supervisors ls
  where ls.user_id = public.my_user_id();
$$;

-- ---------------------------------------------------------------------------
-- 3. Work Location directory (Section 3)
-- ---------------------------------------------------------------------------
create table if not exists public.pcs_work_locations (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  name text not null,
  code text,
  description text,
  start_date date,
  planned_completion_date date,
  actual_completion_date date,
  status text not null default 'active'
    check (status in ('active','stopped','completed')),
  dpr_reminder boolean not null default true,
  display_order int not null default 0,
  remarks text,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_by uuid references public.users(id),
  updated_at timestamptz not null default now(),
  unique (project_id, name)
);
create index if not exists idx_pcs_loc_project_status
  on public.pcs_work_locations(project_id, status);
create index if not exists idx_pcs_loc_order
  on public.pcs_work_locations(project_id, display_order);
drop trigger if exists trg_pcs_loc_updated on public.pcs_work_locations;
create trigger trg_pcs_loc_updated before update on public.pcs_work_locations
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 4. Location <-> supervisor assignment (Section 3)
-- ---------------------------------------------------------------------------
create table if not exists public.pcs_location_supervisors (
  location_id uuid not null references public.pcs_work_locations(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  primary key (location_id, user_id)
);
create index if not exists idx_pcs_loc_sup_user
  on public.pcs_location_supervisors(user_id, location_id);

-- ---------------------------------------------------------------------------
-- 5. Manager daily plan header + revisions + planned rows (Section 13)
-- ---------------------------------------------------------------------------
create table if not exists public.pcs_daily_plans (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  plan_date date not null,
  status text not null default 'draft'
    check (status in ('draft','published','accepted','in_progress','completed','deferred','cancelled')),
  revision int not null default 1,
  published_by uuid references public.users(id),
  published_at timestamptz,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_by uuid references public.users(id),
  updated_at timestamptz not null default now(),
  unique (project_id, plan_date)
);
create index if not exists idx_pcs_plan_project_date
  on public.pcs_daily_plans(project_id, plan_date, status);
drop trigger if exists trg_pcs_plan_updated on public.pcs_daily_plans;
create trigger trg_pcs_plan_updated before update on public.pcs_daily_plans
  for each row execute function public.set_updated_at();

create table if not exists public.pcs_daily_plan_revisions (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.pcs_daily_plans(id) on delete cascade,
  revision int not null,
  snapshot jsonb not null,
  published_by uuid references public.users(id),
  published_at timestamptz not null default now(),
  unique (plan_id, revision)
);

create table if not exists public.pcs_planned_activities (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.pcs_daily_plans(id) on delete cascade,
  location_id uuid not null references public.pcs_work_locations(id) on delete cascade,
  description text not null,
  previous_completion numeric(5,2)
    check (previous_completion is null or (previous_completion >= 0 and previous_completion <= 100)),
  supervisor_id uuid references public.users(id),
  priority text not null default 'normal'
    check (priority in ('normal','urgent','critical')),
  planned_manpower int check (planned_manpower is null or planned_manpower >= 0),
  status text not null default 'draft'
    check (status in ('draft','published','accepted','in_progress','completed','deferred','cancelled')),
  display_order int not null default 0,
  remarks text,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_by uuid references public.users(id),
  updated_at timestamptz not null default now()
);
create index if not exists idx_pcs_plan_act_plan
  on public.pcs_planned_activities(plan_id, location_id);
drop trigger if exists trg_pcs_plan_act_updated on public.pcs_planned_activities;
create trigger trg_pcs_plan_act_updated before update on public.pcs_planned_activities
  for each row execute function public.set_updated_at();

-- Planned materials / plant are kept separate from requested and actual (Section 11).
create table if not exists public.pcs_planned_materials (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.pcs_daily_plans(id) on delete cascade,
  location_id uuid references public.pcs_work_locations(id) on delete cascade,
  item_id uuid,               -- soft reference to material master (FK added later)
  item_name text not null,
  quantity numeric,
  unit text,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now()
);
create index if not exists idx_pcs_plan_mat_plan on public.pcs_planned_materials(plan_id);

create table if not exists public.pcs_planned_plant (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references public.pcs_daily_plans(id) on delete cascade,
  location_id uuid references public.pcs_work_locations(id) on delete cascade,
  item_id uuid,               -- soft reference to plant/equipment master (FK added later)
  item_name text not null,
  quantity numeric,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now()
);
create index if not exists idx_pcs_plan_plant_plan on public.pcs_planned_plant(plan_id);

-- ---------------------------------------------------------------------------
-- 6. PCS parent report + child location reports (Sections 4, 15, 18, 20)
--    NOTE: separate from the existing public.daily_reports; nothing there changes.
-- ---------------------------------------------------------------------------
create table if not exists public.pcs_daily_reports (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  report_date date not null,
  status text not null default 'open'
    check (status in ('open','submitted','completed')),
  overall_prepared_by uuid references public.users(id),
  overall_approved_by uuid references public.users(id),
  completion_override boolean not null default false,
  override_reason text,
  overridden_by uuid references public.users(id),
  overridden_at timestamptz,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_by uuid references public.users(id),
  updated_at timestamptz not null default now(),
  unique (project_id, report_date)
);
create index if not exists idx_pcs_par_project_date
  on public.pcs_daily_reports(project_id, report_date);
drop trigger if exists trg_pcs_par_updated on public.pcs_daily_reports;
create trigger trg_pcs_par_updated before update on public.pcs_daily_reports
  for each row execute function public.set_updated_at();

create table if not exists public.pcs_location_reports (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references public.pcs_daily_reports(id) on delete cascade,
  location_id uuid not null references public.pcs_work_locations(id) on delete restrict,
  reported_by uuid references public.users(id),
  supervisor_id uuid references public.users(id),
  status text not null default 'draft'
    check (status in ('draft','submitted','reopened')),
  record_version int not null default 1,
  submitted_by uuid references public.users(id),
  submitted_at timestamptz,
  last_updated_by uuid references public.users(id),
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (parent_id, location_id)          -- Section 18.3: one report per location/date
);
create index if not exists idx_pcs_locrep_location on public.pcs_location_reports(location_id);
create index if not exists idx_pcs_locrep_parent on public.pcs_location_reports(parent_id, status);
drop trigger if exists trg_pcs_locrep_updated on public.pcs_location_reports;
create trigger trg_pcs_locrep_updated before update on public.pcs_location_reports
  for each row execute function public.set_updated_at();

-- Today's + tomorrow's activity rows (Sections 5, 6)
create table if not exists public.pcs_location_activities (
  id uuid primary key default gen_random_uuid(),
  location_report_id uuid not null references public.pcs_location_reports(id) on delete cascade,
  kind text not null check (kind in ('today','tomorrow')),
  description text not null,
  percent_complete numeric(5,2)
    check (percent_complete is null or (percent_complete >= 0 and percent_complete <= 100)),
  previous_percent numeric(5,2)
    check (previous_percent is null or (previous_percent >= 0 and previous_percent <= 100)),
  source_plan_activity_id uuid references public.pcs_planned_activities(id) on delete set null,
  origin text not null default 'manual' check (origin in ('planned','manual')),
  activity_status text
    check (activity_status is null or activity_status in
      ('planned','manual','in_progress','completed','deferred','cancelled')),
  remark text,
  reduction_reason text,      -- Section 5.11: required when cumulative % is reduced
  display_order int not null default 0,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_by uuid references public.users(id),
  updated_at timestamptz not null default now()
);
create index if not exists idx_pcs_locact_report on public.pcs_location_activities(location_report_id, kind);
drop trigger if exists trg_pcs_locact_updated on public.pcs_location_activities;
create trigger trg_pcs_locact_updated before update on public.pcs_location_activities
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 7. Worker location distribution (Section 9). Operational only — never writes
--    allocation, attendance, payroll or timesheet data.
-- ---------------------------------------------------------------------------
create table if not exists public.pcs_worker_distributions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  distribution_date date not null,
  location_id uuid not null references public.pcs_work_locations(id) on delete cascade,
  worker_id uuid not null references public.workers(id) on delete cascade,
  segment text not null default 'custom'
    check (segment in ('morning','afternoon','night','custom')),
  start_time time,
  end_time time,
  remarks text,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_by uuid references public.users(id),
  updated_at timestamptz not null default now()
);
create index if not exists idx_pcs_dist_project_date
  on public.pcs_worker_distributions(project_id, distribution_date);
create index if not exists idx_pcs_dist_worker_date
  on public.pcs_worker_distributions(worker_id, distribution_date);
drop trigger if exists trg_pcs_dist_updated on public.pcs_worker_distributions;
create trigger trg_pcs_dist_updated before update on public.pcs_worker_distributions
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 8. Actual materials / plant used (Section 10) — separate from planned/requested
-- ---------------------------------------------------------------------------
create table if not exists public.pcs_actual_materials (
  id uuid primary key default gen_random_uuid(),
  location_report_id uuid not null references public.pcs_location_reports(id) on delete cascade,
  item_id uuid,               -- soft reference to material master
  item_name text not null,
  quantity numeric,
  unit text,
  delivery_ref text,
  remarks text,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now()
);
create index if not exists idx_pcs_act_mat_report on public.pcs_actual_materials(location_report_id);

create table if not exists public.pcs_actual_plant (
  id uuid primary key default gen_random_uuid(),
  location_report_id uuid not null references public.pcs_location_reports(id) on delete cascade,
  item_id uuid,               -- soft reference to plant/equipment master
  item_name text not null,
  quantity numeric,
  usage_hours numeric,
  usage_days numeric,
  provider text,
  remarks text,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now()
);
create index if not exists idx_pcs_act_plant_report on public.pcs_actual_plant(location_report_id);

-- ---------------------------------------------------------------------------
-- 9. Resource requests (Section 11). No cost columns — supervisors read this.
--    converted_pr_id links to the existing Purchase Request module only when a
--    manager explicitly converts (soft reference; FK added when PR table verified).
-- ---------------------------------------------------------------------------
create table if not exists public.pcs_resource_requests (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  location_id uuid references public.pcs_work_locations(id) on delete set null,
  location_report_id uuid references public.pcs_location_reports(id) on delete set null,
  request_type text not null check (request_type in ('material','plant')),
  item_id uuid,               -- soft reference to master
  item_name text not null,
  quantity numeric,
  unit text,
  required_by date,
  required_from date,
  required_until date,
  priority text not null default 'normal' check (priority in ('normal','urgent','critical')),
  status text not null default 'requested'
    check (status in ('requested','reviewed','approved','partially_arranged','arranged','rejected')),
  manager_remarks text,
  converted_pr_id uuid,       -- soft reference to purchase request (Section 11.11)
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_by uuid references public.users(id),
  updated_at timestamptz not null default now()
);
create index if not exists idx_pcs_req_project_status
  on public.pcs_resource_requests(project_id, status);
drop trigger if exists trg_pcs_req_updated on public.pcs_resource_requests;
create trigger trg_pcs_req_updated before update on public.pcs_resource_requests
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- 10. Location photos (Section 18) — join existing photos to a location report.
--     photo_id is a soft reference to the existing photo store.
-- ---------------------------------------------------------------------------
create table if not exists public.pcs_location_photos (
  id uuid primary key default gen_random_uuid(),
  location_report_id uuid not null references public.pcs_location_reports(id) on delete cascade,
  photo_id uuid not null,     -- soft reference to existing photo/camera store
  caption text,
  display_order int not null default 0,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now()
);
create index if not exists idx_pcs_locphoto_report on public.pcs_location_photos(location_report_id);

-- ---------------------------------------------------------------------------
-- 11. WhatsApp plan message audit (Section 14)
-- ---------------------------------------------------------------------------
create table if not exists public.pcs_whatsapp_plan_messages (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  plan_date date not null,
  format text not null default 'detailed' check (format in ('short','detailed')),
  generated_text text,
  edited_text text,
  final_text text,
  generated_by uuid references public.users(id),
  generated_at timestamptz not null default now()
);
create index if not exists idx_pcs_wa_project_date
  on public.pcs_whatsapp_plan_messages(project_id, plan_date);

-- ---------------------------------------------------------------------------
-- 12. Row Level Security. Read = project visible via my_project_ids(); write =
--     management roles, plus supervisors for their own operational rows. Cost
--     protection is structural (no cost columns on any table above).
-- ---------------------------------------------------------------------------
do $$
declare
  mgmt constant text := $q$public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead')$q$;
  t text;
begin
  foreach t in array array[
    'pcs_work_locations','pcs_location_supervisors','pcs_daily_plans',
    'pcs_daily_plan_revisions','pcs_planned_activities','pcs_planned_materials',
    'pcs_planned_plant','pcs_daily_reports','pcs_location_reports',
    'pcs_location_activities','pcs_worker_distributions','pcs_actual_materials',
    'pcs_actual_plant','pcs_resource_requests','pcs_location_photos',
    'pcs_whatsapp_plan_messages'
  ] loop
    execute format('alter table public.%I enable row level security;', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated;', t);
  end loop;
end $$;

-- Directory / planning tables: readable by anyone who can see the project;
-- writable by management only.
create policy pcs_loc_sel on public.pcs_work_locations for select
  using (project_id in (select public.my_project_ids()));
create policy pcs_loc_mng on public.pcs_work_locations for all
  using (project_id in (select public.my_project_ids())
    and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (project_id in (select public.my_project_ids())
    and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

create policy pcs_locsup_sel on public.pcs_location_supervisors for select
  using (location_id in (select public.my_pcs_location_ids()));
create policy pcs_locsup_mng on public.pcs_location_supervisors for all
  using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

create policy pcs_plan_sel on public.pcs_daily_plans for select
  using (project_id in (select public.my_project_ids()));
create policy pcs_plan_mng on public.pcs_daily_plans for all
  using (project_id in (select public.my_project_ids())
    and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (project_id in (select public.my_project_ids())
    and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

create policy pcs_planrev_sel on public.pcs_daily_plan_revisions for select
  using (plan_id in (select id from public.pcs_daily_plans where project_id in (select public.my_project_ids())));
create policy pcs_planrev_mng on public.pcs_daily_plan_revisions for all
  using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

create policy pcs_planact_sel on public.pcs_planned_activities for select
  using (plan_id in (select id from public.pcs_daily_plans where project_id in (select public.my_project_ids())));
create policy pcs_planact_mng on public.pcs_planned_activities for all
  using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

create policy pcs_planmat_sel on public.pcs_planned_materials for select
  using (plan_id in (select id from public.pcs_daily_plans where project_id in (select public.my_project_ids())));
create policy pcs_planmat_mng on public.pcs_planned_materials for all
  using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

create policy pcs_planplant_sel on public.pcs_planned_plant for select
  using (plan_id in (select id from public.pcs_daily_plans where project_id in (select public.my_project_ids())));
create policy pcs_planplant_mng on public.pcs_planned_plant for all
  using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

-- Parent report: management create/manage; anyone on the project can read.
create policy pcs_par_sel on public.pcs_daily_reports for select
  using (project_id in (select public.my_project_ids()));
create policy pcs_par_mng on public.pcs_daily_reports for all
  using (project_id in (select public.my_project_ids())
    and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (project_id in (select public.my_project_ids())
    and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

-- Location reports and their children: management full; supervisors for their
-- own assigned locations.
create policy pcs_locrep_sel on public.pcs_location_reports for select
  using (location_id in (select public.my_pcs_location_ids())
    or exists (select 1 from public.pcs_daily_reports r
               where r.id = parent_id and r.project_id in (select public.my_project_ids())));
create policy pcs_locrep_write on public.pcs_location_reports for all
  using (location_id in (select public.my_pcs_location_ids()))
  with check (location_id in (select public.my_pcs_location_ids()));

create policy pcs_locact_sel on public.pcs_location_activities for select
  using (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())
       or exists (select 1 from public.pcs_daily_reports r
                  where r.id = lr.parent_id and r.project_id in (select public.my_project_ids()))));
create policy pcs_locact_write on public.pcs_location_activities for all
  using (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())))
  with check (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())));

create policy pcs_dist_sel on public.pcs_worker_distributions for select
  using (project_id in (select public.my_project_ids()));
create policy pcs_dist_write on public.pcs_worker_distributions for all
  using (location_id in (select public.my_pcs_location_ids()))
  with check (location_id in (select public.my_pcs_location_ids()));

create policy pcs_actmat_sel on public.pcs_actual_materials for select
  using (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())
       or exists (select 1 from public.pcs_daily_reports r
                  where r.id = lr.parent_id and r.project_id in (select public.my_project_ids()))));
create policy pcs_actmat_write on public.pcs_actual_materials for all
  using (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())))
  with check (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())));

create policy pcs_actplant_sel on public.pcs_actual_plant for select
  using (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())
       or exists (select 1 from public.pcs_daily_reports r
                  where r.id = lr.parent_id and r.project_id in (select public.my_project_ids()))));
create policy pcs_actplant_write on public.pcs_actual_plant for all
  using (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())))
  with check (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())));

-- Resource requests: supervisors create/read for their locations; management
-- reviews/approves anywhere on the project. No cost columns exist here.
create policy pcs_req_sel on public.pcs_resource_requests for select
  using (project_id in (select public.my_project_ids()));
create policy pcs_req_ins on public.pcs_resource_requests for insert
  with check (location_id in (select public.my_pcs_location_ids())
    or public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));
create policy pcs_req_upd on public.pcs_resource_requests for update
  using (location_id in (select public.my_pcs_location_ids())
    or public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (project_id in (select public.my_project_ids()));

create policy pcs_locphoto_sel on public.pcs_location_photos for select
  using (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())
       or exists (select 1 from public.pcs_daily_reports r
                  where r.id = lr.parent_id and r.project_id in (select public.my_project_ids()))));
create policy pcs_locphoto_write on public.pcs_location_photos for all
  using (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())))
  with check (location_report_id in (
    select lr.id from public.pcs_location_reports lr
    where lr.location_id in (select public.my_pcs_location_ids())));

create policy pcs_wa_sel on public.pcs_whatsapp_plan_messages for select
  using (project_id in (select public.my_project_ids()));
create policy pcs_wa_mng on public.pcs_whatsapp_plan_messages for all
  using (project_id in (select public.my_project_ids())
    and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (project_id in (select public.my_project_ids())
    and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

-- ---------------------------------------------------------------------------
insert into public.schema_migrations(version, description)
values ('0017', 'PCS Stage 1: DPR mode flag and multi-location DPR data foundation')
on conflict (version) do nothing;

commit;

-- ===========================================================================
-- ROLLBACK (run only if reverting Stage 1; additive, so this is clean):
--   begin;
--   drop table if exists public.pcs_whatsapp_plan_messages, public.pcs_location_photos,
--     public.pcs_resource_requests, public.pcs_actual_plant, public.pcs_actual_materials,
--     public.pcs_worker_distributions, public.pcs_location_activities, public.pcs_location_reports,
--     public.pcs_daily_reports, public.pcs_planned_plant, public.pcs_planned_materials,
--     public.pcs_planned_activities, public.pcs_daily_plan_revisions, public.pcs_daily_plans,
--     public.pcs_location_supervisors, public.pcs_work_locations cascade;
--   drop function if exists public.my_pcs_location_ids();
--   alter table public.projects drop column if exists dpr_mode;
--   delete from public.schema_migrations where version = '0017';
--   commit;
-- ===========================================================================
