-- VCMS Phase 1: Activities and Milestones foundation connected to WBS.
-- Rehearse on a non-production project before production use.
begin;

create table if not exists public.schedule_activities (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete restrict,
  schedule_id uuid not null references public.schedules(id) on delete restrict,
  wbs_id uuid not null references public.wbs_nodes(id) on delete restrict,
  code text not null,
  name text not null,
  description text,
  activity_type text not null default 'task' check (activity_type in ('task','milestone')),
  duration_days integer not null default 1 check (duration_days >= 0 and duration_days <= 10000),
  planned_start date not null,
  planned_finish date not null,
  status text not null default 'not_started' check (status in ('not_started','in_progress','complete')),
  percent_complete numeric(5,2) not null default 0 check (percent_complete between 0 and 100),
  sort_order integer not null default 1000 check (sort_order >= 0),
  is_active boolean not null default true,
  created_by uuid references public.users(id),
  updated_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz,
  unique (schedule_id, code),
  check (planned_finish >= planned_start),
  check ((activity_type = 'milestone' and duration_days = 0 and planned_finish = planned_start) or
         (activity_type = 'task' and duration_days >= 1))
);

create index if not exists idx_activities_project_order on public.schedule_activities(project_id, sort_order);
create index if not exists idx_activities_wbs_order on public.schedule_activities(wbs_id, sort_order);
create index if not exists idx_activities_schedule_dates on public.schedule_activities(schedule_id, planned_start, planned_finish);

drop trigger if exists trg_schedule_activities_updated on public.schedule_activities;
create trigger trg_schedule_activities_updated before update on public.schedule_activities
for each row execute function public.set_updated_at();

create or replace function public.validate_activity_scope()
returns trigger language plpgsql set search_path = public as $$
declare schedule_project uuid; wbs_row public.wbs_nodes%rowtype;
begin
  select project_id into schedule_project from public.schedules where id = new.schedule_id;
  if schedule_project is null or schedule_project <> new.project_id then
    raise exception 'Activity schedule must belong to the same project';
  end if;
  select * into wbs_row from public.wbs_nodes where id = new.wbs_id and is_active;
  if not found or wbs_row.project_id <> new.project_id or wbs_row.schedule_id <> new.schedule_id then
    raise exception 'Activity WBS must belong to the same project and schedule';
  end if;
  return new;
end $$;

drop trigger if exists trg_validate_activity_scope on public.schedule_activities;
create trigger trg_validate_activity_scope before insert or update of project_id, schedule_id, wbs_id
on public.schedule_activities for each row execute function public.validate_activity_scope();

alter table public.schedule_activities enable row level security;
drop policy if exists activities_select_authorized on public.schedule_activities;
create policy activities_select_authorized on public.schedule_activities for select
using (project_id in (select public.my_project_ids()));
drop policy if exists activities_manage on public.schedule_activities;
create policy activities_manage on public.schedule_activities for all
using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
with check (project_id in (select public.my_project_ids()) and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

grant select, insert, update on public.schedule_activities to authenticated;

insert into public.schema_migrations(version, description)
values ('0003', 'Phase 1 Activities and Milestones foundation')
on conflict (version) do nothing;

commit;
