-- VCMS Planning V2.1 Stage 2: DPR-driven physical progress.
begin;

alter table public.schedule_activities
  add column if not exists target_quantity numeric(16,3),
  add column if not exists unit text;
alter table public.schedule_activities drop constraint if exists schedule_activities_target_quantity_check;
alter table public.schedule_activities add constraint schedule_activities_target_quantity_check
  check(target_quantity is null or target_quantity > 0);

create table if not exists public.planning_activity_site_mappings(
  id uuid primary key default gen_random_uuid(),
  activity_id uuid not null references public.schedule_activities(id) on delete restrict,
  project_id uuid not null references public.projects(id) on delete restrict,
  site_id uuid not null references public.sites(id) on delete restrict,
  item_of_work text,
  effective_from date not null,
  effective_to date,
  is_active boolean not null default true,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  check(effective_to is null or effective_to >= effective_from),
  unique(activity_id,site_id,effective_from)
);
create index if not exists idx_planning_mapping_site_dates
  on public.planning_activity_site_mappings(site_id,effective_from,effective_to) where is_active;

create table if not exists public.planning_dpr_progress_entries(
  id uuid primary key default gen_random_uuid(),
  daily_report_id uuid not null references public.daily_reports(id) on delete restrict,
  activity_id uuid not null references public.schedule_activities(id) on delete restrict,
  project_id uuid not null references public.projects(id) on delete restrict,
  report_date date not null,
  quantity_completed numeric(16,3) not null check(quantity_completed >= 0),
  note text,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(daily_report_id,activity_id)
);
create index if not exists idx_planning_progress_activity_date
  on public.planning_dpr_progress_entries(activity_id,report_date);

create or replace function public.record_planning_dpr_progress(p_dpr_id uuid,p_entries jsonb)
returns integer language plpgsql security definer set search_path=public as $$
declare d public.daily_reports%rowtype; item jsonb; aid uuid; qty numeric; changed integer:=0;
begin
  if coalesce(public.my_role(),'') <> 'admin' then raise exception 'Administrator only'; end if;
  select * into d from public.daily_reports where id=p_dpr_id;
  if d.id is null then raise exception 'DPR not found'; end if;
  if jsonb_array_length(coalesce(p_entries,'[]'::jsonb))>100 then raise exception 'Too many progress entries'; end if;

  delete from public.planning_dpr_progress_entries where daily_report_id=p_dpr_id;
  for item in select * from jsonb_array_elements(coalesce(p_entries,'[]'::jsonb)) loop
    aid:=(item->>'activity_id')::uuid; qty:=coalesce((item->>'quantity_completed')::numeric,0);
    if not exists(
      select 1 from public.planning_activity_site_mappings m
      where m.activity_id=aid and m.site_id=d.site_id and m.is_active
        and d.report_date>=m.effective_from and (m.effective_to is null or d.report_date<=m.effective_to)
    ) then raise exception 'Activity is not mapped to this site and DPR date'; end if;
    insert into public.planning_dpr_progress_entries(daily_report_id,activity_id,project_id,report_date,quantity_completed,note,created_by)
    select d.id,a.id,a.project_id,d.report_date,qty,nullif(trim(item->>'note'),''),public.my_user_id()
      from public.schedule_activities a where a.id=aid and a.is_active;
    if not found then raise exception 'Activity not found'; end if;
    changed:=changed+1;
  end loop;

  update public.schedule_activities a set
    percent_complete=least(100,round(100*coalesce(x.qty,0)/nullif(a.target_quantity,0),2)),
    status=case when coalesce(x.qty,0)>=a.target_quantity then 'complete' when coalesce(x.qty,0)>0 then 'in_progress' else 'not_started' end,
    actual_start=case when coalesce(x.qty,0)>0 then coalesce(a.actual_start,x.first_date) else null end,
    actual_finish=case when coalesce(x.qty,0)>=a.target_quantity then x.last_date else null end,
    updated_by=public.my_user_id()
  from (
    select ids.activity_id,coalesce(sum(p.quantity_completed),0) qty,
           min(p.report_date) first_date,max(p.report_date) last_date
    from (select distinct activity_id from public.planning_activity_site_mappings
          where site_id=d.site_id and is_active) ids
    left join public.planning_dpr_progress_entries p on p.activity_id=ids.activity_id
    group by ids.activity_id
  ) x where a.id=x.activity_id and a.target_quantity is not null;
  return changed;
end $$;

alter table public.planning_activity_site_mappings enable row level security;
alter table public.planning_dpr_progress_entries enable row level security;
create policy planning_mappings_select on public.planning_activity_site_mappings for select using(project_id in(select public.my_project_ids()));
create policy planning_mappings_admin on public.planning_activity_site_mappings for all using(public.my_role()='admin') with check(public.my_role()='admin');
create policy planning_progress_select on public.planning_dpr_progress_entries for select using(project_id in(select public.my_project_ids()));
create policy planning_progress_admin on public.planning_dpr_progress_entries for all using(public.my_role()='admin') with check(public.my_role()='admin');
grant select on public.planning_activity_site_mappings,public.planning_dpr_progress_entries to authenticated;
revoke all on function public.record_planning_dpr_progress(uuid,jsonb) from public,anon;
grant execute on function public.record_planning_dpr_progress(uuid,jsonb) to authenticated;

insert into public.schema_migrations(version,description)
values('0010','Planning V2.1 Stage 2 DPR automatic physical progress') on conflict(version) do nothing;
commit;
