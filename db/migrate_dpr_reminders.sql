-- VCMS: personal missing-DPR reminders. Run once in Supabase SQL Editor.
alter table public.users
  add column if not exists dpr_reminders boolean not null default false;

-- Enable now only for Anbu's profile. Everyone else can opt in from Settings.
update public.users
set dpr_reminders = true
where lower(trim(name)) = lower('Renganathan Anbazhagan');

alter table public.todos add column if not exists source text;
alter table public.todos add column if not exists source_key text;

create unique index if not exists todos_user_source_key_uidx
  on public.todos (user_id, source, source_key)
  where source is not null and source_key is not null;

create index if not exists daily_reports_site_report_date_idx
  on public.daily_reports (site_id, report_date);

-- A signed-in user may change only this preference, never their role/status.
create or replace function public.set_my_dpr_reminders(enabled boolean)
returns void
language sql
security definer
set search_path = public
as $$
  update public.users
  set dpr_reminders = enabled
  where auth_uid = auth.uid();
$$;

revoke all on function public.set_my_dpr_reminders(boolean) from public;
grant execute on function public.set_my_dpr_reminders(boolean) to authenticated;
