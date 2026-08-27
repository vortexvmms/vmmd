begin;

-- Fast, RLS-aware dashboard summary.  Keeping this function in migration
-- history makes the Render/Supabase deployment reproducible after recovery.
create or replace function public.home_dashboard_agg(
  p_start date,
  p_today date,
  p_site_ids uuid[] default null
)
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
with base as (
  select
    a.work_date,
    a.site_id,
    s.site_name,
    a.worker_id,
    coalesce(w.name, '?') as worker_name,
    coalesce(nullif(w.worker_code, ''), a.worker_id::text) as worker_code,
    att.id as attendance_id,
    att.present,
    att.submitted_at,
    case when att.present then coalesce(att.normal_hours, 0) else 0 end::numeric as nh,
    case when att.present then coalesce(att.ot_hours, 0) else 0 end::numeric as oh,
    case when att.present then att.partial_leave_type else att.absence_type end as leave_type,
    case
      when coalesce(att.leave_value, 0) > 0 then att.leave_value
      when att.present and att.partial_leave_type is not null then 0.5
      when not coalesce(att.present, true) and att.absence_type is not null then 1
      else 0
    end::numeric as leave_days
  from public.allocations a
  join public.sites s on s.id = a.site_id
  join public.workers w on w.id = a.worker_id
  left join public.attendance att on att.allocation_id = a.id
  where a.status = 'allocated'
    and a.work_date between p_start and p_today
    and (p_site_ids is null or a.site_id = any(p_site_ids))
),
site_month_rows as (
  select site_name, sum(nh) as nh, sum(oh) as ot
  from base group by site_name
),
today_rows as (
  select site_name,
         count(*)::integer as allocated,
         count(attendance_id)::integer as with_att,
         count(*) filter (where submitted_at is not null)::integer as submitted
  from base where work_date = p_today group by site_name
),
leave_rows as (
  select worker_code as code, max(worker_name) as name,
         sum(leave_days) filter (where leave_type = 'mc') as mc,
         sum(leave_days) filter (where leave_type = 'al') as al,
         sum(leave_days) filter (where leave_type = 'ul') as ul
  from base
  where leave_type in ('mc', 'al', 'ul')
  group by worker_code
)
select jsonb_build_object(
  'month_nh', coalesce((select sum(nh) from base), 0),
  'month_ot', coalesce((select sum(oh) from base), 0),
  'today_mc', coalesce((select sum(leave_days) from base where work_date=p_today and leave_type='mc'), 0),
  'today_al', coalesce((select sum(leave_days) from base where work_date=p_today and leave_type='al'), 0),
  'today_ul', coalesce((select sum(leave_days) from base where work_date=p_today and leave_type='ul'), 0),
  'site_month', coalesce((select jsonb_agg(jsonb_build_object('site_name',site_name,'nh',nh,'ot',ot) order by site_name) from site_month_rows), '[]'::jsonb),
  'today_by_site', coalesce((select jsonb_agg(jsonb_build_object('site_name',site_name,'allocated',allocated,'with_att',with_att,'submitted',submitted) order by site_name) from today_rows), '[]'::jsonb),
  'leave_by_worker', coalesce((select jsonb_agg(jsonb_build_object('code',code,'name',name,'mc',coalesce(mc,0),'al',coalesce(al,0),'ul',coalesce(ul,0)) order by name) from leave_rows), '[]'::jsonb)
);
$$;

revoke all on function public.home_dashboard_agg(date,date,uuid[]) from public, anon;
grant execute on function public.home_dashboard_agg(date,date,uuid[]) to authenticated;

insert into public.schema_migrations(version, description)
values('0015', 'Fast RLS-aware home dashboard aggregation')
on conflict(version) do nothing;

commit;
