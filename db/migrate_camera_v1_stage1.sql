-- VCMS Camera V1 · Stage 1
-- Reusable Item of Work and Activity records attached to the existing DPR
-- work-package directory. No duplicate Project/Site master is created.
begin;

create table if not exists public.camera_work_items (
  id uuid primary key default gen_random_uuid(),
  dpr_project_id uuid not null references public.dpr_projects(id) on delete cascade,
  name text not null,
  sort_order integer not null default 0,
  active boolean not null default true,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint camera_work_items_name check (length(trim(name)) between 1 and 200),
  constraint camera_work_items_unique unique (dpr_project_id, name)
);

create table if not exists public.camera_activities (
  id uuid primary key default gen_random_uuid(),
  work_item_id uuid not null references public.camera_work_items(id) on delete cascade,
  name text not null,
  sort_order integer not null default 0,
  active boolean not null default true,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint camera_activities_name check (length(trim(name)) between 1 and 200),
  constraint camera_activities_unique unique (work_item_id, name)
);

create index if not exists camera_work_items_project_order_idx
  on public.camera_work_items(dpr_project_id, active, sort_order, name);
create index if not exists camera_activities_item_order_idx
  on public.camera_activities(work_item_id, active, sort_order, name);

alter table public.camera_work_items enable row level security;
alter table public.camera_activities enable row level security;

drop policy if exists camera_work_items_read on public.camera_work_items;
create policy camera_work_items_read on public.camera_work_items
  for select to authenticated using (true);
drop policy if exists camera_activities_read on public.camera_activities;
create policy camera_activities_read on public.camera_activities
  for select to authenticated using (true);

drop policy if exists camera_work_items_manage on public.camera_work_items;
create policy camera_work_items_manage on public.camera_work_items
  for all to authenticated
  using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));
drop policy if exists camera_activities_manage on public.camera_activities;
create policy camera_activities_manage on public.camera_activities
  for all to authenticated
  using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
  with check (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));

commit;
