-- VCMS Phase 1: Project calendars and working-day rules.
-- Rehearse on a non-production project before production use.
begin;

create table if not exists public.schedule_calendars (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete restrict,
  name text not null,
  hours_per_day numeric(4,2) not null default 8 check (hours_per_day > 0 and hours_per_day <= 24),
  is_default boolean not null default false,
  is_active boolean not null default true,
  created_by uuid references public.users(id), updated_by uuid references public.users(id),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(), archived_at timestamptz,
  unique(project_id,name)
);
create unique index if not exists uq_project_default_calendar on public.schedule_calendars(project_id) where is_default and is_active;

create table if not exists public.calendar_workweek (
  calendar_id uuid not null references public.schedule_calendars(id) on delete cascade,
  day_of_week smallint not null check(day_of_week between 0 and 6),
  is_working boolean not null,
  work_hours numeric(4,2) not null check(work_hours between 0 and 24),
  primary key(calendar_id,day_of_week),
  check((is_working and work_hours > 0) or (not is_working and work_hours = 0))
);

create table if not exists public.calendar_exceptions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete restrict,
  calendar_id uuid not null references public.schedule_calendars(id) on delete cascade,
  exception_date date not null, name text not null, is_working boolean not null default false,
  work_hours numeric(4,2) not null default 0 check(work_hours between 0 and 24),
  created_by uuid references public.users(id), updated_by uuid references public.users(id),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  unique(calendar_id,exception_date),
  check((is_working and work_hours > 0) or (not is_working and work_hours = 0))
);

drop trigger if exists trg_schedule_calendars_updated on public.schedule_calendars;
create trigger trg_schedule_calendars_updated before update on public.schedule_calendars for each row execute function public.set_updated_at();
drop trigger if exists trg_calendar_exceptions_updated on public.calendar_exceptions;
create trigger trg_calendar_exceptions_updated before update on public.calendar_exceptions for each row execute function public.set_updated_at();

create or replace function public.prepare_project_calendar() returns trigger language plpgsql set search_path=public as $$
begin
  if not exists(select 1 from public.schedule_calendars where project_id=new.project_id and is_default and is_active and id<>new.id) then new.is_default:=true; end if;
  if new.is_default and new.is_active then update public.schedule_calendars set is_default=false where project_id=new.project_id and id<>new.id and is_default; end if;
  return new;
end $$;
drop trigger if exists trg_prepare_project_calendar on public.schedule_calendars;
create trigger trg_prepare_project_calendar before insert or update of is_default,is_active on public.schedule_calendars for each row execute function public.prepare_project_calendar();

create or replace function public.seed_calendar_workweek() returns trigger language plpgsql set search_path=public as $$
begin
  insert into public.calendar_workweek(calendar_id,day_of_week,is_working,work_hours)
  select new.id,d,(d between 1 and 5),case when d between 1 and 5 then new.hours_per_day else 0 end from generate_series(0,6) d
  on conflict(calendar_id,day_of_week) do nothing;
  return new;
end $$;
drop trigger if exists trg_seed_calendar_workweek on public.schedule_calendars;
create trigger trg_seed_calendar_workweek after insert on public.schedule_calendars for each row execute function public.seed_calendar_workweek();

create or replace function public.sync_project_default_calendar() returns trigger language plpgsql set search_path=public as $$
begin
  if new.is_default and new.is_active then update public.projects set default_calendar_id=new.id where id=new.project_id; end if;
  return new;
end $$;
drop trigger if exists trg_sync_project_default_calendar on public.schedule_calendars;
create trigger trg_sync_project_default_calendar after insert or update of is_default,is_active on public.schedule_calendars for each row execute function public.sync_project_default_calendar();

create or replace function public.validate_calendar_exception_scope() returns trigger language plpgsql set search_path=public as $$
declare calendar_project uuid;
begin
  select project_id into calendar_project from public.schedule_calendars where id=new.calendar_id and is_active;
  if calendar_project is null or calendar_project<>new.project_id then raise exception 'Calendar exception must belong to the same project'; end if;
  return new;
end $$;
drop trigger if exists trg_validate_calendar_exception_scope on public.calendar_exceptions;
create trigger trg_validate_calendar_exception_scope before insert or update of project_id,calendar_id on public.calendar_exceptions for each row execute function public.validate_calendar_exception_scope();

alter table public.schedule_activities add column if not exists calendar_id uuid references public.schedule_calendars(id) on delete restrict;
create or replace function public.validate_activity_calendar_scope() returns trigger language plpgsql set search_path=public as $$
begin
  if new.calendar_id is null then select id into new.calendar_id from public.schedule_calendars where project_id=new.project_id and is_default and is_active limit 1; end if;
  if new.calendar_id is not null and not exists(select 1 from public.schedule_calendars c where c.id=new.calendar_id and c.project_id=new.project_id and c.is_active) then
    raise exception 'Activity calendar must belong to the same project';
  end if;
  return new;
end $$;
drop trigger if exists trg_validate_activity_calendar_scope on public.schedule_activities;
create trigger trg_validate_activity_calendar_scope before insert or update of project_id,calendar_id on public.schedule_activities for each row execute function public.validate_activity_calendar_scope();

do $$ begin
  if not exists(select 1 from pg_constraint where conname='projects_default_calendar_id_fkey') then
    alter table public.projects add constraint projects_default_calendar_id_fkey foreign key(default_calendar_id) references public.schedule_calendars(id) on delete set null;
  end if;
end $$;

create or replace function public.set_calendar_workweek(p_calendar_id uuid,p_rules jsonb) returns integer language plpgsql set search_path=public as $$
declare item jsonb; changed integer:=0;
begin
  if coalesce(public.my_role(),'') not in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead') then raise exception 'Not allowed to edit project calendars'; end if;
  if jsonb_array_length(p_rules)<>7 or (select count(distinct (x->>'day_of_week')::int) from jsonb_array_elements(p_rules)x)<>7 then raise exception 'Workweek must contain seven unique weekdays'; end if;
  for item in select * from jsonb_array_elements(p_rules) loop
    insert into public.calendar_workweek(calendar_id,day_of_week,is_working,work_hours)
    values(p_calendar_id,(item->>'day_of_week')::smallint,(item->>'is_working')::boolean,(item->>'work_hours')::numeric)
    on conflict(calendar_id,day_of_week) do update set is_working=excluded.is_working,work_hours=excluded.work_hours;
    changed:=changed+1;
  end loop;
  return changed;
end $$;

alter table public.schedule_calendars enable row level security;
alter table public.calendar_workweek enable row level security;
alter table public.calendar_exceptions enable row level security;
drop policy if exists calendars_select_authorized on public.schedule_calendars;
drop policy if exists calendars_manage on public.schedule_calendars;
drop policy if exists workweek_select_authorized on public.calendar_workweek;
drop policy if exists workweek_manage on public.calendar_workweek;
drop policy if exists exceptions_select_authorized on public.calendar_exceptions;
drop policy if exists exceptions_manage on public.calendar_exceptions;
create policy calendars_select_authorized on public.schedule_calendars for select using(project_id in(select public.my_project_ids()));
create policy calendars_manage on public.schedule_calendars for all using(public.my_role() in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead')) with check(project_id in(select public.my_project_ids()) and public.my_role() in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));
create policy workweek_select_authorized on public.calendar_workweek for select using(calendar_id in(select id from public.schedule_calendars where project_id in(select public.my_project_ids())));
create policy workweek_manage on public.calendar_workweek for all using(calendar_id in(select id from public.schedule_calendars where project_id in(select public.my_project_ids())) and public.my_role() in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead')) with check(calendar_id in(select id from public.schedule_calendars where project_id in(select public.my_project_ids())));
create policy exceptions_select_authorized on public.calendar_exceptions for select using(project_id in(select public.my_project_ids()));
create policy exceptions_manage on public.calendar_exceptions for all using(public.my_role() in('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead')) with check(project_id in(select public.my_project_ids()));
grant select,insert,update on public.schedule_calendars,public.calendar_workweek,public.calendar_exceptions to authenticated;
revoke all on function public.set_calendar_workweek(uuid,jsonb) from public,anon;
grant execute on function public.set_calendar_workweek(uuid,jsonb) to authenticated;
insert into public.schema_migrations(version,description) values('0005','Phase 1 Project calendars and working-day rules') on conflict(version) do nothing;
commit;
