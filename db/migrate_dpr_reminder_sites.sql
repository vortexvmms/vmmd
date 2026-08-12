-- VCMS: choose which sites generate missing-DPR reminders for each user.
-- Run once in Supabase SQL Editor.
alter table public.users
  add column if not exists dpr_reminder_sites uuid[];

comment on column public.users.dpr_reminder_sites is
  'NULL = all accessible sites; uuid array = only selected sites; empty array = no sites';
