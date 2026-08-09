-- VCMS Phase 1: Resource master, project pools, and activity assignments.
begin;
create table if not exists public.resource_master_library(
 id uuid primary key default gen_random_uuid(),code text not null unique,name text not null,
 category text not null check(category in('labour','equipment','material','subcontractor')),
 classification text check(classification in('direct','indirect')),unit text not null,standard_rate numeric(14,2) not null default 0 check(standard_rate>=0),
 is_active boolean not null default true,created_by uuid references public.users(id),updated_by uuid references public.users(id),created_at timestamptz not null default now(),updated_at timestamptz not null default now(),archived_at timestamptz
);
create table if not exists public.project_resources(
 id uuid primary key default gen_random_uuid(),project_id uuid not null references public.projects(id) on delete restrict,master_resource_id uuid not null references public.resource_master_library(id) on delete restrict,
 project_rate numeric(14,2) check(project_rate>=0),is_active boolean not null default true,created_by uuid references public.users(id),updated_by uuid references public.users(id),created_at timestamptz not null default now(),updated_at timestamptz not null default now(),archived_at timestamptz,
 unique(project_id,master_resource_id)
);
create table if not exists public.activity_resource_assignments(
 id uuid primary key default gen_random_uuid(),project_id uuid not null references public.projects(id) on delete restrict,schedule_id uuid not null references public.schedules(id) on delete restrict,
 activity_id uuid not null references public.schedule_activities(id) on delete restrict,project_resource_id uuid not null references public.project_resources(id) on delete restrict,
 planned_quantity numeric(14,3) not null check(planned_quantity>0),unit_rate numeric(14,2) not null check(unit_rate>=0),budgeted_cost numeric(16,2) generated always as (round(planned_quantity*unit_rate,2)) stored,
 is_active boolean not null default true,created_by uuid references public.users(id),updated_by uuid references public.users(id),created_at timestamptz not null default now(),updated_at timestamptz not null default now(),archived_at timestamptz
);
create unique index if not exists uq_active_activity_resource on public.activity_resource_assignments(activity_id,project_resource_id) where is_active;
create index if not exists idx_project_resources_project on public.project_resources(project_id,is_active);
create index if not exists idx_assignments_project_activity on public.activity_resource_assignments(project_id,activity_id,is_active);
drop trigger if exists trg_resource_master_updated on public.resource_master_library; create trigger trg_resource_master_updated before update on public.resource_master_library for each row execute function public.set_updated_at();
drop trigger if exists trg_project_resources_updated on public.project_resources; create trigger trg_project_resources_updated before update on public.project_resources for each row execute function public.set_updated_at();
drop trigger if exists trg_resource_assignments_updated on public.activity_resource_assignments; create trigger trg_resource_assignments_updated before update on public.activity_resource_assignments for each row execute function public.set_updated_at();
create or replace function public.validate_resource_assignment_scope() returns trigger language plpgsql set search_path=public as $$
declare activity_row public.schedule_activities%rowtype; resource_project uuid;
begin
 select * into activity_row from public.schedule_activities where id=new.activity_id and is_active;
 select project_id into resource_project from public.project_resources where id=new.project_resource_id and is_active;
 if activity_row.id is null or activity_row.project_id<>new.project_id or activity_row.schedule_id<>new.schedule_id then raise exception 'Assignment activity must belong to the same project and schedule'; end if;
 if resource_project is null or resource_project<>new.project_id then raise exception 'Assigned resource must belong to the same project pool'; end if;
 return new;
end $$;
drop trigger if exists trg_validate_resource_assignment_scope on public.activity_resource_assignments;
create trigger trg_validate_resource_assignment_scope before insert or update of project_id,schedule_id,activity_id,project_resource_id on public.activity_resource_assignments for each row execute function public.validate_resource_assignment_scope();
alter table public.resource_master_library enable row level security; alter table public.project_resources enable row level security; alter table public.activity_resource_assignments enable row level security;
drop policy if exists resource_master_select on public.resource_master_library; drop policy if exists resource_master_manage on public.resource_master_library;
drop policy if exists project_resources_select on public.project_resources; drop policy if exists project_resources_manage on public.project_resources;
drop policy if exists assignments_select on public.activity_resource_assignments; drop policy if exists assignments_manage on public.activity_resource_assignments;
create policy resource_master_select on public.resource_master_library for select using(public.my_role() is not null);
create policy resource_master_manage on public.resource_master_library for all using(public.my_role() in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead')) with check(public.my_role() in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));
create policy project_resources_select on public.project_resources for select using(project_id in(select public.my_project_ids()));
create policy project_resources_manage on public.project_resources for all using(public.my_role() in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead')) with check(project_id in(select public.my_project_ids()));
create policy assignments_select on public.activity_resource_assignments for select using(project_id in(select public.my_project_ids()));
create policy assignments_manage on public.activity_resource_assignments for all using(public.my_role() in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead')) with check(project_id in(select public.my_project_ids()));
grant select,insert,update on public.resource_master_library,public.project_resources,public.activity_resource_assignments to authenticated;
insert into public.schema_migrations(version,description) values('0006','Phase 1 Resource master, project pools, and activity assignments') on conflict(version) do nothing;
commit;
