-- ONE-TIME DATA CORRECTION
-- Transfer allocations (and therefore their linked attendance) from
-- POKB-DLP INSPECTION / DLP Visual Inspection to TUNNEL REPAIR WORK
-- for 10/08/2026 through 13/08/2026 inclusive.
--
-- Attendance is NOT copied or deleted. It remains attached to the same
-- allocation_id, so present/absence, hours and submissions are preserved.

begin;

create table if not exists public.admin_data_corrections (
  id uuid primary key default gen_random_uuid(),
  correction_key text not null unique,
  description text not null,
  details jsonb not null default '{}'::jsonb,
  executed_at timestamptz not null default now()
);

-- The correction ledger contains operational history and must never be
-- exposed to ordinary authenticated users.
alter table public.admin_data_corrections enable row level security;
drop policy if exists admin_data_corrections_admin_read on public.admin_data_corrections;
create policy admin_data_corrections_admin_read on public.admin_data_corrections
  for select using (public.my_role() = 'admin');

do $$
declare
  source_id uuid;
  target_id uuid;
  source_count integer;
  target_before integer;
  attendance_before integer;
  attendance_after integer;
  moved_count integer;
  moved_ids uuid[];
begin
  if exists (
    select 1 from public.admin_data_corrections
    where correction_key = 'DLP_TO_TUNNEL_2026-08-10_2026-08-13'
  ) then
    raise exception 'This correction has already been completed. No data was changed.';
  end if;

  select id into source_id
  from public.sites
  where upper(trim(site_name)) in (
    'POKB-DLP INSPECTION', 'POKB - DLP INSPECTION',
    'DLP VISUAL INSPECTION', 'DLP VISUAL INSPECTION JOB'
  );

  if source_id is null then
    raise exception 'Source site not found. Expected POKB-DLP INSPECTION / DLP Visual Inspection.';
  end if;

  if (select count(*) from public.sites where upper(trim(site_name)) in (
      'POKB-DLP INSPECTION', 'POKB - DLP INSPECTION',
      'DLP VISUAL INSPECTION', 'DLP VISUAL INSPECTION JOB')) <> 1 then
    raise exception 'Source site name is not unique. No data was changed.';
  end if;

  select id into target_id
  from public.sites
  where upper(trim(site_name)) in (
    'TUNNEL REPAIR WORK', 'TUNNEL REPAIR',
    'POKB - TUNNEL REPAIR WORK', 'POKB-TUNNEL REPAIR WORK',
    'POKB-DLP TUNNEL REPAIR WORK'
  );

  if target_id is null then
    raise exception 'Target site not found. Expected Tunnel Repair Work.';
  end if;

  if (select count(*) from public.sites where upper(trim(site_name)) in (
      'TUNNEL REPAIR WORK', 'TUNNEL REPAIR',
      'POKB - TUNNEL REPAIR WORK', 'POKB-TUNNEL REPAIR WORK',
      'POKB-DLP TUNNEL REPAIR WORK')) <> 1 then
    raise exception 'Target site name is not unique. No data was changed.';
  end if;

  select count(*) into source_count
  from public.allocations
  where site_id = source_id
    and work_date between date '2026-08-10' and date '2026-08-13'
    and status = 'allocated';

  select array_agg(id) into moved_ids
  from public.allocations
  where site_id = source_id
    and work_date between date '2026-08-10' and date '2026-08-13'
    and status = 'allocated';

  if source_count = 0 then
    raise exception 'No active DLP allocations found from 10/08/2026 to 13/08/2026. No data was changed.';
  end if;

  select count(*) into target_before
  from public.allocations
  where site_id = target_id
    and work_date between date '2026-08-10' and date '2026-08-13'
    and status = 'allocated';

  select count(*) into attendance_before from public.attendance
  where allocation_id = any(moved_ids);

  update public.allocations
     set site_id = target_id,
         updated_at = now()
   where site_id = source_id
     and work_date between date '2026-08-10' and date '2026-08-13'
     and status = 'allocated';
  get diagnostics moved_count = row_count;

  if moved_count <> source_count then
    raise exception 'Safety check failed: expected to move %, moved %. Transaction rolled back.', source_count, moved_count;
  end if;

  select count(*) into attendance_after from public.attendance
  where allocation_id = any(moved_ids);

  if attendance_after <> attendance_before then
    raise exception 'Attendance preservation check failed. Transaction rolled back.';
  end if;

  if (select count(*) from public.allocations
      where id = any(moved_ids) and site_id=target_id) <> source_count then
    raise exception 'Target-site verification failed. Transaction rolled back.';
  end if;

  insert into public.admin_data_corrections(correction_key, description, details)
  values (
    'DLP_TO_TUNNEL_2026-08-10_2026-08-13',
    'Transferred DLP allocations to Tunnel Repair Work; attendance allocation IDs preserved.',
    jsonb_build_object(
      'source_site_id', source_id, 'target_site_id', target_id,
      'from_date', '2026-08-10', 'to_date', '2026-08-13',
      'allocations_moved', moved_count,
      'linked_attendance_preserved', attendance_before,
      'target_allocations_before', target_before
    )
  );
end $$;

commit;

-- POST-CORRECTION CHECK: this returns one row per date.
select
  a.work_date,
  count(*) filter (where s.site_name ilike '%DLP%') as dlp_allocations_remaining,
  count(*) filter (where upper(s.site_name) like '%TUNNEL%REPAIR%') as tunnel_allocations,
  count(att.id) filter (where upper(s.site_name) like '%TUNNEL%REPAIR%') as tunnel_attendance_records,
  coalesce(sum(att.normal_hours) filter (where upper(s.site_name) like '%TUNNEL%REPAIR%'),0) as normal_hours,
  coalesce(sum(att.ot_hours) filter (where upper(s.site_name) like '%TUNNEL%REPAIR%'),0) as ot_hours
from public.allocations a
join public.sites s on s.id=a.site_id
left join public.attendance att on att.allocation_id=a.id
where a.work_date between date '2026-08-10' and date '2026-08-13'
  and a.status='allocated'
group by a.work_date
order by a.work_date;
