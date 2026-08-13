-- VCMS DPR work-package lifecycle and stop/resume history.
-- Run once in Supabase SQL Editor before deploying the matching application release.
begin;

alter table public.dpr_projects add column if not exists project_code text;
alter table public.dpr_projects add column if not exists client_contract text;
alter table public.dpr_projects add column if not exists start_date date;
alter table public.dpr_projects add column if not exists planned_completion_date date;
alter table public.dpr_projects add column if not exists actual_completion_date date;
alter table public.dpr_projects add column if not exists cancelled_date date;
alter table public.dpr_projects add column if not exists lifecycle_status text not null default 'draft';
alter table public.dpr_projects add column if not exists reminder_enabled boolean not null default true;
alter table public.dpr_projects add column if not exists responsible_user_ids uuid[] not null default '{}';
alter table public.dpr_projects add column if not exists remarks text;
alter table public.dpr_projects add column if not exists updated_at timestamptz not null default now();

-- Existing saved DPR directory entries represent live work. Preserve their
-- current reminder behaviour; managers can then complete/pause them explicitly.
update public.dpr_projects set lifecycle_status='active'
where lifecycle_status='draft';

do $$ begin
  if not exists (select 1 from pg_constraint where conname='dpr_projects_lifecycle_status_check') then
    alter table public.dpr_projects add constraint dpr_projects_lifecycle_status_check
      check (lifecycle_status in ('draft','active','temporarily_stopped','completed','cancelled','archived'));
  end if;
end $$;

create table if not exists public.dpr_project_pauses (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.dpr_projects(id) on delete cascade,
  stop_date date not null,
  expected_resume_date date,
  resume_date date,
  reason text,
  stopped_by uuid references public.users(id),
  resumed_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint dpr_project_pause_dates check (resume_date is null or resume_date >= stop_date)
);

create index if not exists dpr_projects_site_lifecycle_idx
  on public.dpr_projects(site_id,lifecycle_status,start_date,actual_completion_date);
create index if not exists dpr_project_pauses_project_dates_idx
  on public.dpr_project_pauses(project_id,stop_date,resume_date);

alter table public.dpr_project_pauses enable row level security;
drop policy if exists dpr_project_pauses_authenticated on public.dpr_project_pauses;
create policy dpr_project_pauses_authenticated on public.dpr_project_pauses
  for all to authenticated using (true) with check (true);

commit;
