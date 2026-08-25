-- VCMS Planning V2.1 Stage 1: authoritative timeline-cell selections.
-- Apply after 0001-0005. Rehearse on a non-production Supabase project first.
begin;

create table if not exists public.planning_activity_dates (
  activity_id uuid not null references public.schedule_activities(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete restrict,
  work_date date not null,
  selected_by uuid references public.users(id),
  selected_at timestamptz not null default now(),
  primary key (activity_id, work_date)
);
create index if not exists idx_planning_activity_dates_project_date
  on public.planning_activity_dates(project_id, work_date);

create or replace function public.replace_activity_dates(
  p_activity_id uuid, p_project_id uuid, p_dates date[]
) returns integer language plpgsql security definer set search_path=public as $$
declare v_count integer;
begin
  if coalesce(public.my_role(),'') <> 'admin' then
    raise exception 'Administrator only';
  end if;
  if not exists (
    select 1 from public.schedule_activities
    where id=p_activity_id and project_id=p_project_id and is_active
  ) then raise exception 'Activity not found'; end if;
  if coalesce(array_length(p_dates,1),0)=0 then raise exception 'Select at least one date'; end if;
  if array_length(p_dates,1)>1000 then raise exception 'A single activity cannot exceed 1000 selected dates'; end if;

  delete from public.planning_activity_dates where activity_id=p_activity_id;
  insert into public.planning_activity_dates(activity_id,project_id,work_date,selected_by)
  select p_activity_id,p_project_id,d,public.my_user_id()
    from (select distinct unnest(p_dates) d) x;
  get diagnostics v_count=row_count;

  update public.schedule_activities
     set planned_start=(select min(work_date) from public.planning_activity_dates where activity_id=p_activity_id),
         planned_finish=(select max(work_date) from public.planning_activity_dates where activity_id=p_activity_id),
         duration_days=v_count,
         updated_by=public.my_user_id()
   where id=p_activity_id;
  return v_count;
end $$;

alter table public.planning_activity_dates enable row level security;
drop policy if exists planning_activity_dates_select on public.planning_activity_dates;
create policy planning_activity_dates_select on public.planning_activity_dates for select
  using(project_id in(select public.my_project_ids()));
drop policy if exists planning_activity_dates_admin on public.planning_activity_dates;
create policy planning_activity_dates_admin on public.planning_activity_dates for all
  using(public.my_role()='admin') with check(public.my_role()='admin');

grant select on public.planning_activity_dates to authenticated;
revoke all on function public.replace_activity_dates(uuid,uuid,date[]) from public,anon;
grant execute on function public.replace_activity_dates(uuid,uuid,date[]) to authenticated;

insert into public.schema_migrations(version,description)
values('0009','Planning V2.1 Stage 1 authoritative selected activity dates')
on conflict(version) do nothing;
commit;
