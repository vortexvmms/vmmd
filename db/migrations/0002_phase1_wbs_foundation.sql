-- VCMS Phase 1: project Schedule and WBS hierarchy foundation.
-- Rehearse on a non-production project before production use.
begin;

create table if not exists public.schedules (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null unique references public.projects(id) on delete restrict,
  name text not null default 'Project Schedule',
  data_date date not null default current_date,
  status text not null default 'draft' check (status in ('draft','active','archived')),
  currency text not null default 'SGD',
  created_by uuid references public.users(id),
  updated_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz
);

drop trigger if exists trg_schedules_updated on public.schedules;
create trigger trg_schedules_updated before update on public.schedules
for each row execute function public.set_updated_at();

create table if not exists public.wbs_nodes (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete restrict,
  schedule_id uuid not null references public.schedules(id) on delete restrict,
  parent_id uuid references public.wbs_nodes(id) on delete restrict,
  code text not null,
  name text not null,
  description text,
  sort_order integer not null default 1000 check (sort_order >= 0),
  depth smallint not null default 1 check (depth between 1 and 6),
  is_active boolean not null default true,
  created_by uuid references public.users(id),
  updated_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz,
  unique (schedule_id, code)
);

create index if not exists idx_wbs_project_order on public.wbs_nodes(project_id, sort_order);
create index if not exists idx_wbs_schedule_parent on public.wbs_nodes(schedule_id, parent_id, sort_order);

drop trigger if exists trg_wbs_nodes_updated on public.wbs_nodes;
create trigger trg_wbs_nodes_updated before update on public.wbs_nodes
for each row execute function public.set_updated_at();

create or replace function public.validate_wbs_hierarchy()
returns trigger language plpgsql set search_path = public as $$
declare parent_row public.wbs_nodes%rowtype;
begin
  if new.parent_id is null then
    new.depth := 1;
  else
    if new.parent_id = new.id then raise exception 'A WBS node cannot be its own parent'; end if;
    select * into parent_row from public.wbs_nodes where id = new.parent_id;
    if not found then raise exception 'WBS parent does not exist'; end if;
    if parent_row.schedule_id <> new.schedule_id or parent_row.project_id <> new.project_id then
      raise exception 'WBS parent must belong to the same project and schedule';
    end if;
    new.depth := parent_row.depth + 1;
    if new.depth > 6 then raise exception 'WBS hierarchy cannot exceed 6 levels'; end if;
    if exists (
      with recursive descendants as (
        select id from public.wbs_nodes where parent_id = new.id
        union all select w.id from public.wbs_nodes w join descendants d on w.parent_id = d.id
      ) select 1 from descendants where id = new.parent_id
    ) then raise exception 'WBS hierarchy cannot contain a cycle'; end if;
  end if;
  return new;
end $$;

drop trigger if exists trg_validate_wbs_hierarchy on public.wbs_nodes;
create trigger trg_validate_wbs_hierarchy before insert or update of parent_id, schedule_id, project_id
on public.wbs_nodes for each row execute function public.validate_wbs_hierarchy();

create or replace function public.refresh_wbs_descendant_depths()
returns trigger language plpgsql set search_path = public as $$
begin
  with recursive descendants as (
    select w.id, new.depth + 1 as calculated_depth
      from public.wbs_nodes w where w.parent_id = new.id
    union all
    select w.id, d.calculated_depth + 1
      from public.wbs_nodes w join descendants d on w.parent_id = d.id
  )
  update public.wbs_nodes w set depth = d.calculated_depth
    from descendants d where w.id = d.id;
  if exists (
    with recursive descendants as (
      select w.id, new.depth + 1 as calculated_depth from public.wbs_nodes w where w.parent_id = new.id
      union all select w.id, d.calculated_depth + 1 from public.wbs_nodes w join descendants d on w.parent_id = d.id
    ) select 1 from descendants where calculated_depth > 6
  ) then raise exception 'WBS hierarchy cannot exceed 6 levels'; end if;
  return new;
end $$;

drop trigger if exists trg_refresh_wbs_depths on public.wbs_nodes;
create trigger trg_refresh_wbs_depths after update of parent_id on public.wbs_nodes
for each row execute function public.refresh_wbs_descendant_depths();

create or replace function public.reorder_wbs_nodes(p_project_id uuid, p_items jsonb)
returns integer language plpgsql set search_path = public as $$
declare item jsonb; changed integer := 0; affected integer;
begin
  if coalesce(public.my_role(), '') not in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead') then
    raise exception 'Not allowed to edit the WBS';
  end if;
  for item in select * from jsonb_array_elements(p_items)
  loop
    update public.wbs_nodes
       set parent_id = nullif(item->>'parent_id','')::uuid,
           sort_order = (item->>'sort_order')::integer,
           updated_by = public.my_user_id()
     where id = (item->>'id')::uuid and project_id = p_project_id and is_active;
    get diagnostics affected = row_count;
    if affected <> 1 then raise exception 'WBS reorder item is not accessible'; end if;
    changed := changed + 1;
  end loop;
  return changed;
end $$;

alter table public.schedules enable row level security;
alter table public.wbs_nodes enable row level security;

drop policy if exists schedules_select_authorized on public.schedules;
create policy schedules_select_authorized on public.schedules for select
using (project_id in (select public.my_project_ids()));
drop policy if exists schedules_manage on public.schedules;
create policy schedules_manage on public.schedules for all
using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
with check (project_id in (select public.my_project_ids()) and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

drop policy if exists wbs_select_authorized on public.wbs_nodes;
create policy wbs_select_authorized on public.wbs_nodes for select
using (project_id in (select public.my_project_ids()));
drop policy if exists wbs_manage on public.wbs_nodes;
create policy wbs_manage on public.wbs_nodes for all
using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
with check (project_id in (select public.my_project_ids()) and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

grant select, insert, update on public.schedules, public.wbs_nodes to authenticated;
revoke all on function public.reorder_wbs_nodes(uuid, jsonb) from public, anon;
grant execute on function public.reorder_wbs_nodes(uuid, jsonb) to authenticated;

insert into public.schema_migrations(version, description)
values ('0002', 'Phase 1 Schedule and WBS hierarchy foundation')
on conflict (version) do nothing;

commit;
