-- VCMS PCS Multi-Location DPR — Stage 3: allow supervisors to open the shared
-- parent report for a project/date so they can file their own location reports.
-- Additive RLS only; no tables or data change. Apply after 0017.
-- Test on a non-production Supabase project before production use.
begin;

-- A supervisor cannot create a location report until the parent daily report
-- exists. Stage 1 restricted parent creation to management. This adds an INSERT
-- policy so any user who can see the project (which includes assigned site
-- supervisors, via public.my_project_ids()) may create the open parent shell.
-- Update and delete of the parent remain management-only (pcs_par_mng from 0017).
drop policy if exists pcs_par_ins_member on public.pcs_daily_reports;
create policy pcs_par_ins_member on public.pcs_daily_reports for insert
  with check (project_id in (select public.my_project_ids()));

insert into public.schema_migrations(version, description)
values ('0018', 'PCS Stage 3: supervisor parent-report insert policy')
on conflict (version) do nothing;

commit;

-- ===========================================================================
-- ROLLBACK:
--   begin;
--   drop policy if exists pcs_par_ins_member on public.pcs_daily_reports;
--   delete from public.schema_migrations where version = '0018';
--   commit;
-- ===========================================================================
