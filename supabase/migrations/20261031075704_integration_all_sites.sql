-- All-site read access when p_sites is NULL; explicit filters still constrain results.
-- Existing callers that supply a site array retain their original scope.
begin;
create or replace function public.integration_attendance_range_v1(
 p_from date, p_to date, p_sites text[], p_worker text default null,
 p_after_date date default null, p_after_id uuid default null, p_limit integer default 201
) returns setof jsonb language sql stable security invoker
set search_path = '' set statement_timeout = '10s'
as $$
 select jsonb_build_object(
 'record_id', a.id, 'work_date', a.work_date,
 'worker_code', w.worker_code, 'worker_name', w.name,
 'site_code', s.site_code, 'site_name', s.site_name,
 'status', case when a.status = 'cancelled' then 'removed'
   when t.id is null then 'not_marked' when t.present then 'present'
   when t.absence_type in ('mc','al','ul','class') then t.absence_type else 'absent' end,
 'start_time', to_char(t.start_time, 'HH24:MI'),
 'end_time', to_char(t.end_time, 'HH24:MI'), 'end_next_day', t.end_next_day,
 'shift_type', t.shift_type, 'normal_hours', t.normal_hours, 'ot_hours', t.ot_hours,
 'day_type', t.day_type, 'submitted_at', t.submitted_at,
 'updated_at', greatest(a.updated_at, t.updated_at))
 from public.allocations a join public.workers w on w.id=a.worker_id
 join public.sites s on s.id=a.site_id
 left join public.attendance t on t.allocation_id=a.id
 where p_from <= p_to and p_to - p_from < 62
 and a.work_date between p_from and p_to and (p_sites is null or s.site_code=any(p_sites))
 and (p_worker is null or w.worker_code=p_worker)
 and (p_after_date is null or (a.work_date,a.id) > (p_after_date,p_after_id))
 order by a.work_date,a.id limit greatest(1,least(coalesce(p_limit,201),501));
$$;
revoke all on function public.integration_attendance_range_v1(date,date,text[],text,date,uuid,integer) from public, anon, authenticated;
grant execute on function public.integration_attendance_range_v1(date,date,text[],text,date,uuid,integer) to service_role;
commit;
