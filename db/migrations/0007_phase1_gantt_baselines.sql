-- VCMS Phase 1: calculated schedule dates, Gantt data, and immutable baselines.
begin;
alter table public.schedule_activities add column if not exists early_start date;
alter table public.schedule_activities add column if not exists early_finish date;
alter table public.schedule_activities add column if not exists late_start date;
alter table public.schedule_activities add column if not exists late_finish date;
alter table public.schedule_activities add column if not exists total_float integer;
alter table public.schedule_activities add column if not exists is_critical boolean not null default false;
alter table public.schedule_activities add column if not exists calculated_at timestamptz;
alter table public.schedules add column if not exists last_calculated_at timestamptz;

create table if not exists public.schedule_baselines(
 id uuid primary key default gen_random_uuid(),project_id uuid not null references public.projects(id) on delete restrict,schedule_id uuid not null references public.schedules(id) on delete restrict,
 name text not null,description text,data_date date not null,status text not null default 'active' check(status in('active','superseded','archived')),
 created_by uuid references public.users(id),created_at timestamptz not null default now(),unique(schedule_id,name)
);
create table if not exists public.baseline_activity_snapshots(
 id uuid primary key default gen_random_uuid(),baseline_id uuid not null references public.schedule_baselines(id) on delete cascade,activity_id uuid not null references public.schedule_activities(id) on delete restrict,
 activity_code text not null,activity_name text not null,activity_type text not null,duration_days integer not null,
 planned_start date not null,planned_finish date not null,early_start date,early_finish date,late_start date,late_finish date,total_float integer,is_critical boolean not null default false,budgeted_cost numeric(16,2) not null default 0,
 unique(baseline_id,activity_id)
);
create index if not exists idx_baselines_project on public.schedule_baselines(project_id,created_at desc);
create index if not exists idx_baseline_snapshots_baseline on public.baseline_activity_snapshots(baseline_id);

create or replace function public.create_schedule_baseline(p_project_id uuid,p_name text,p_description text,p_data_date date) returns uuid language plpgsql security definer set search_path=public as $$
declare schedule_row public.schedules%rowtype; new_baseline_id uuid;
begin
 if coalesce(public.my_role(),'') not in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead') then raise exception 'Not allowed to create baselines'; end if;
 select * into schedule_row from public.schedules where project_id=p_project_id;
 if schedule_row.id is null then raise exception 'Project schedule not found'; end if;
 if schedule_row.last_calculated_at is null then raise exception 'Calculate the schedule before creating a baseline'; end if;
 insert into public.schedule_baselines(project_id,schedule_id,name,description,data_date,created_by) values(p_project_id,schedule_row.id,trim(p_name),p_description,p_data_date,public.my_user_id()) returning id into new_baseline_id;
 insert into public.baseline_activity_snapshots(baseline_id,activity_id,activity_code,activity_name,activity_type,duration_days,planned_start,planned_finish,early_start,early_finish,late_start,late_finish,total_float,is_critical,budgeted_cost)
 select new_baseline_id,a.id,a.code,a.name,a.activity_type,a.duration_days,a.planned_start,a.planned_finish,a.early_start,a.early_finish,a.late_start,a.late_finish,a.total_float,a.is_critical,
 coalesce((select sum(r.budgeted_cost) from public.activity_resource_assignments r where r.activity_id=a.id and r.is_active),0)
 from public.schedule_activities a where a.project_id=p_project_id and a.is_active;
 return new_baseline_id;
end $$;

alter table public.schedule_baselines enable row level security; alter table public.baseline_activity_snapshots enable row level security;
drop policy if exists baselines_select on public.schedule_baselines; drop policy if exists baselines_manage on public.schedule_baselines; drop policy if exists baseline_snapshots_select on public.baseline_activity_snapshots;
create policy baselines_select on public.schedule_baselines for select using(project_id in(select public.my_project_ids()));
create policy baselines_manage on public.schedule_baselines for all using(public.my_role() in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead')) with check(project_id in(select public.my_project_ids()));
create policy baseline_snapshots_select on public.baseline_activity_snapshots for select using(baseline_id in(select id from public.schedule_baselines where project_id in(select public.my_project_ids())));
grant select,insert,update on public.schedule_baselines to authenticated; grant select on public.baseline_activity_snapshots to authenticated;
revoke all on function public.create_schedule_baseline(uuid,text,text,date) from public,anon; grant execute on function public.create_schedule_baseline(uuid,text,text,date) to authenticated;
insert into public.schema_migrations(version,description) values('0007','Phase 1 Schedule calculation, Gantt, and baselines') on conflict(version) do nothing;
commit;
