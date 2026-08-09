-- VCMS Phase 1: Activity predecessor/successor logic foundation.
-- Rehearse on a non-production project before production use.
begin;

create table if not exists public.activity_relationships (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete restrict,
  schedule_id uuid not null references public.schedules(id) on delete restrict,
  predecessor_id uuid not null references public.schedule_activities(id) on delete restrict,
  successor_id uuid not null references public.schedule_activities(id) on delete restrict,
  relationship_type text not null default 'FS' check (relationship_type in ('FS','SS','FF','SF')),
  lag_days integer not null default 0 check (lag_days between -3650 and 3650),
  is_active boolean not null default true,
  created_by uuid references public.users(id),
  updated_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz,
  check (predecessor_id <> successor_id)
);

create index if not exists idx_relationships_project on public.activity_relationships(project_id, is_active);
create index if not exists idx_relationships_predecessor on public.activity_relationships(predecessor_id, is_active);
create index if not exists idx_relationships_successor on public.activity_relationships(successor_id, is_active);
create unique index if not exists uq_active_relationship_pair
on public.activity_relationships(schedule_id, predecessor_id, successor_id) where is_active;

drop trigger if exists trg_activity_relationships_updated on public.activity_relationships;
create trigger trg_activity_relationships_updated before update on public.activity_relationships
for each row execute function public.set_updated_at();

create or replace function public.validate_activity_relationship()
returns trigger language plpgsql set search_path = public as $$
declare predecessor_row public.schedule_activities%rowtype; successor_row public.schedule_activities%rowtype;
begin
  select * into predecessor_row from public.schedule_activities where id = new.predecessor_id and is_active;
  select * into successor_row from public.schedule_activities where id = new.successor_id and is_active;
  if predecessor_row.id is null or successor_row.id is null then raise exception 'Relationship activities must be active'; end if;
  if predecessor_row.project_id <> new.project_id or successor_row.project_id <> new.project_id or
     predecessor_row.schedule_id <> new.schedule_id or successor_row.schedule_id <> new.schedule_id then
    raise exception 'Relationship activities must belong to the same project and schedule';
  end if;
  if exists (
    with recursive downstream as (
      select r.successor_id from public.activity_relationships r
       where r.schedule_id = new.schedule_id and r.predecessor_id = new.successor_id and r.is_active and r.id <> new.id
      union
      select r.successor_id from public.activity_relationships r join downstream d on r.predecessor_id = d.successor_id
       where r.schedule_id = new.schedule_id and r.is_active and r.id <> new.id
    ) select 1 from downstream where successor_id = new.predecessor_id
  ) then raise exception 'Activity logic cannot contain a cycle'; end if;
  return new;
end $$;

drop trigger if exists trg_validate_activity_relationship on public.activity_relationships;
create trigger trg_validate_activity_relationship before insert or update of project_id,schedule_id,predecessor_id,successor_id,is_active
on public.activity_relationships for each row when (new.is_active) execute function public.validate_activity_relationship();

alter table public.activity_relationships enable row level security;
drop policy if exists relationships_select_authorized on public.activity_relationships;
create policy relationships_select_authorized on public.activity_relationships for select
using (project_id in (select public.my_project_ids()));
drop policy if exists relationships_manage on public.activity_relationships;
create policy relationships_manage on public.activity_relationships for all
using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
with check (project_id in (select public.my_project_ids()) and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

grant select, insert, update on public.activity_relationships to authenticated;
insert into public.schema_migrations(version, description)
values ('0004', 'Phase 1 Activity logic relationships foundation')
on conflict (version) do nothing;
commit;
