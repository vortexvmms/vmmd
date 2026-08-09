-- VCMS Phase 1: dated activity progress updates and DPR integration.
begin;

alter table public.schedule_activities add column if not exists actual_start date;
alter table public.schedule_activities add column if not exists actual_finish date;

create table if not exists public.activity_progress_updates(
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete restrict,
  schedule_id uuid not null references public.schedules(id) on delete restrict,
  activity_id uuid not null references public.schedule_activities(id) on delete restrict,
  progress_date date not null,
  percent_complete numeric(5,2) not null check(percent_complete between 0 and 100),
  actual_start date,
  actual_finish date,
  quantity_completed numeric(14,3) check(quantity_completed is null or quantity_completed >= 0),
  remarks text,
  source text not null default 'manual' check(source in('manual','dpr')),
  dpr_report_id uuid,
  created_by uuid references public.users(id),
  updated_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(activity_id,progress_date,source),
  check(actual_finish is null or actual_start is not null),
  check(actual_finish is null or actual_finish >= actual_start),
  check((percent_complete < 100 and actual_finish is null) or percent_complete = 100)
);

create index if not exists idx_activity_progress_project_date on public.activity_progress_updates(project_id,progress_date desc);
create index if not exists idx_activity_progress_activity_date on public.activity_progress_updates(activity_id,progress_date desc,updated_at desc);
drop trigger if exists trg_activity_progress_updated on public.activity_progress_updates;
create trigger trg_activity_progress_updated before update on public.activity_progress_updates for each row execute function public.set_updated_at();

create or replace function public.validate_activity_progress_scope() returns trigger language plpgsql set search_path=public as $$
declare activity_row public.schedule_activities%rowtype;
begin
  select * into activity_row from public.schedule_activities where id=new.activity_id and is_active;
  if activity_row.id is null or activity_row.project_id<>new.project_id or activity_row.schedule_id<>new.schedule_id then
    raise exception 'Progress activity must belong to the same project and schedule';
  end if;
  if new.percent_complete>0 and new.actual_start is null then new.actual_start:=new.progress_date; end if;
  if new.percent_complete=100 and new.actual_finish is null then new.actual_finish:=new.progress_date; end if;
  if new.source='dpr' and new.dpr_report_id is null then raise exception 'DPR progress requires a report reference'; end if;
  if new.source='manual' then new.dpr_report_id:=null; end if;
  return new;
end $$;

drop trigger if exists trg_validate_activity_progress_scope on public.activity_progress_updates;
create trigger trg_validate_activity_progress_scope before insert or update of project_id,schedule_id,activity_id,progress_date,percent_complete,actual_start,actual_finish,source,dpr_report_id
on public.activity_progress_updates for each row execute function public.validate_activity_progress_scope();

create or replace function public.refresh_activity_progress() returns trigger language plpgsql security definer set search_path=public as $$
declare target_activity uuid:=coalesce(new.activity_id,old.activity_id); latest public.activity_progress_updates%rowtype; first_start date;
begin
  select * into latest from public.activity_progress_updates where activity_id=target_activity order by progress_date desc,updated_at desc limit 1;
  select min(actual_start) into first_start from public.activity_progress_updates where activity_id=target_activity and percent_complete>0;
  if latest.id is null then
    update public.schedule_activities set percent_complete=0,status='not_started',actual_start=null,actual_finish=null where id=target_activity;
  else
    update public.schedule_activities set percent_complete=latest.percent_complete,
      status=case when latest.percent_complete=100 then 'complete' when latest.percent_complete>0 then 'in_progress' else 'not_started' end,
      actual_start=first_start,actual_finish=latest.actual_finish,updated_by=latest.updated_by
    where id=target_activity;
  end if;
  if tg_op='DELETE' then return old; end if;
  return new;
end $$;

drop trigger if exists trg_refresh_activity_progress on public.activity_progress_updates;
create trigger trg_refresh_activity_progress after insert or update or delete on public.activity_progress_updates
for each row execute function public.refresh_activity_progress();

create or replace function public.record_activity_progress(
  p_project_id uuid,p_activity_id uuid,p_progress_date date,p_percent_complete numeric,
  p_actual_start date,p_actual_finish date,p_quantity_completed numeric,p_remarks text,
  p_source text default 'manual',p_dpr_report_id uuid default null
) returns uuid language plpgsql security definer set search_path=public as $$
declare activity_row public.schedule_activities%rowtype; saved_id uuid;
begin
  if coalesce(public.my_role(),'') not in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','site_sup','safety_sup','wshc','logistics_sup') then
    raise exception 'Not allowed to record activity progress';
  end if;
  if not exists(select 1 from public.my_project_ids() allowed_project where allowed_project=p_project_id) then raise exception 'Project is not available to this user'; end if;
  select * into activity_row from public.schedule_activities where id=p_activity_id and project_id=p_project_id and is_active;
  if activity_row.id is null then raise exception 'Active project activity not found'; end if;
  insert into public.activity_progress_updates(project_id,schedule_id,activity_id,progress_date,percent_complete,actual_start,actual_finish,quantity_completed,remarks,source,dpr_report_id,created_by,updated_by)
  values(p_project_id,activity_row.schedule_id,p_activity_id,p_progress_date,p_percent_complete,p_actual_start,p_actual_finish,p_quantity_completed,nullif(trim(p_remarks),''),p_source,p_dpr_report_id,public.my_user_id(),public.my_user_id())
  on conflict(activity_id,progress_date,source) do update set percent_complete=excluded.percent_complete,actual_start=excluded.actual_start,actual_finish=excluded.actual_finish,quantity_completed=excluded.quantity_completed,remarks=excluded.remarks,dpr_report_id=excluded.dpr_report_id,updated_by=excluded.updated_by
  returning id into saved_id;
  return saved_id;
end $$;

alter table public.activity_progress_updates enable row level security;
drop policy if exists activity_progress_select on public.activity_progress_updates;
drop policy if exists activity_progress_manage on public.activity_progress_updates;
create policy activity_progress_select on public.activity_progress_updates for select using(project_id in(select public.my_project_ids()));
create policy activity_progress_manage on public.activity_progress_updates for all
using(project_id in(select public.my_project_ids())) with check(project_id in(select public.my_project_ids()));
grant select on public.activity_progress_updates to authenticated;
revoke all on function public.record_activity_progress(uuid,uuid,date,numeric,date,date,numeric,text,text,uuid) from public,anon;
grant execute on function public.record_activity_progress(uuid,uuid,date,numeric,date,date,numeric,text,text,uuid) to authenticated;

insert into public.schema_migrations(version,description) values('0008','Phase 1 Progress updates and DPR integration') on conflict(version) do nothing;
commit;
