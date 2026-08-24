-- VCMS security audit remediation — 24/08/2026
-- Safe to run repeatedly in the Supabase SQL editor.

begin;

do $$
begin
  if to_regclass('public.admin_data_corrections') is not null then
    alter table public.admin_data_corrections enable row level security;
    drop policy if exists admin_data_corrections_admin_read
      on public.admin_data_corrections;
    create policy admin_data_corrections_admin_read
      on public.admin_data_corrections
      for select
      using (public.my_role() = 'admin');
  end if;
end $$;

-- No INSERT/UPDATE/DELETE policy is intentionally provided. This ledger is
-- written only by explicit administrator SQL correction scripts.

commit;
