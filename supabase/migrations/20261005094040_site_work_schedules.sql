-- Empty site schedules inherit the current engine. Empty attendance snapshots
-- preserve that engine for all previously recorded attendance.
alter table public.sites add column if not exists work_schedules jsonb not null default '[]'::jsonb;
alter table public.attendance add column if not exists work_schedule jsonb not null default '{}'::jsonb;
alter table public.sites add constraint sites_work_schedules_array check(jsonb_typeof(work_schedules)='array');
alter table public.attendance add constraint attendance_work_schedule_object check(jsonb_typeof(work_schedule)='object');
-- Configure the requested site only. Never rewrite historical attendance.
update public.sites set work_schedules='[{"effective_from":"2026-10-05","start_time":"07:00","lunch_start":"11:30","lunch_end":"12:00","end_time":"16:30","weekday_basic_hours":8,"saturday_basic_hours":4,"saturday_rule":"first_hours","lunch_rule":"overlap"}]'::jsonb
where site_name='PCS-GBM' and work_schedules='[]'::jsonb;

-- Atomic day-only cancellation: retain attendance, recalculate split-site hours,
-- and write history in the same transaction. Only the backend can call this RPC.
create or replace function public.remove_attendance_day(
  p_allocation_id uuid, p_user_id uuid, p_reason text,
  p_allocation_updated_at timestamptz, p_attendance_updated_at timestamptz
) returns jsonb language plpgsql security invoker set search_path = public as $$
declare
  a public.allocations%rowtype;
  t public.attendance%rowtype;
  actor_role text;
  seg record;
  remaining numeric;
  start_min numeric;
  end_min numeric;
  worked numeric;
  lunch_minutes numeric;
  lunch_start_min numeric;
  lunch_end_min numeric;
  policy jsonb;
  nh numeric;
  oh numeric;
  dtype text;
  recalculated jsonb := '[]'::jsonb;
begin
  if p_reason is null or p_reason not in ('allocated_by_mistake','not_scheduled') then
    raise exception 'Choose a removal reason' using errcode='22023';
  end if;
  select role into actor_role from public.users where id=p_user_id and status='active';
  if actor_role is null or actor_role not in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','site_sup','safety_sup','wshc','logistics_sup') then
    raise exception 'Not allowed' using errcode='42501';
  end if;
  -- Prevent a payroll close being inserted while the cancellation is committing.
  lock table public.month_locks in share mode;
  select * into a from public.allocations where id=p_allocation_id for update;
  if not found then raise exception 'Allocation not found' using errcode='P0002'; end if;
  if actor_role in ('site_sup','safety_sup','wshc','logistics_sup') and not exists (
    select 1 from public.site_supervisors where user_id=p_user_id and site_id=a.site_id
  ) then raise exception 'Not your site' using errcode='42501'; end if;
  if exists(select 1 from public.month_locks where month=date_trunc('month',a.work_date)::date) then
    raise exception 'Month closed by payroll. This day cannot be removed.' using errcode='42501';
  end if;
  if a.status='cancelled' then return jsonb_build_object('ok',true,'already_removed',true,'work_date',a.work_date); end if;
  select * into t from public.attendance where allocation_id=a.id for update;
  if a.updated_at is distinct from p_allocation_updated_at or t.updated_at is distinct from p_attendance_updated_at then
    raise exception 'Attendance changed. Reload and review before removing.' using errcode='40001';
  end if;
  update public.allocations set status='cancelled',updated_by=p_user_id where id=a.id;
  -- Re-apply the normal-hour quota across all remaining sites, including a
  -- single remaining segment. The cancelled attendance row itself is untouched.
  dtype := case when exists(select 1 from public.public_holidays where holiday_date=a.work_date) then 'PH'
                when extract(isodow from a.work_date)=6 then 'SAT'
                when extract(isodow from a.work_date)=7 then 'SUN' else 'WD' end;
  select att.work_schedule into policy from public.allocations al join public.attendance att on att.allocation_id=al.id
    where al.worker_id=a.worker_id and al.work_date=a.work_date and al.status='allocated'
      and att.present and att.end_time is not null order by att.start_time,al.id limit 1;
  remaining := case when dtype='WD' then coalesce((policy->>'weekday_basic_hours')::numeric,8)
                    when dtype='SAT' then coalesce((policy->>'saturday_basic_hours')::numeric,4) else 0 end;
  for seg in
    select att.* from public.allocations al join public.attendance att on att.allocation_id=al.id
    where al.worker_id=a.worker_id and al.work_date=a.work_date and al.status='allocated'
      and att.present and att.end_time is not null
    order by att.start_time,al.id for update of att
  loop
    start_min := extract(epoch from seg.start_time)/60;
    end_min := extract(epoch from seg.end_time)/60 + case when seg.end_next_day then 1440 else 0 end;
    if end_min<=start_min then raise exception 'Remaining attendance has invalid times' using errcode='22023'; end if;
    if seg.work_schedule <> '{}'::jsonb then
      lunch_start_min := extract(epoch from (seg.work_schedule->>'lunch_start')::time)/60;
      lunch_end_min := extract(epoch from (seg.work_schedule->>'lunch_end')::time)/60;
      lunch_minutes := case when seg.work_schedule->>'lunch_rule'='overlap'
          then greatest(0,least(end_min,lunch_end_min)-greatest(start_min,lunch_start_min))
          when start_min<lunch_end_min and end_min>lunch_start_min then lunch_end_min-lunch_start_min else 0 end;
    else
      lunch_minutes := case when not seg.end_next_day and end_min<=720 then 0
                            when start_min<780 and end_min>720 then 60 else 0 end;
    end if;
    worked := (end_min-start_min-lunch_minutes)/60;
    nh := case when dtype in ('SUN','PH') then 0
               when dtype='SAT' then least(remaining,case when seg.work_schedule->>'saturday_rule'='first_hours' then worked else greatest(0,least(end_min,720)-start_min)/60 end,worked)
               else least(remaining,worked) end;
    remaining := remaining-nh;
    oh := floor((worked-nh)*2)/2;
    update public.attendance set normal_hours=round(nh,2),ot_hours=round(oh,2),day_type=dtype where id=seg.id;
    recalculated := recalculated || jsonb_build_array(jsonb_build_object('allocation_id',seg.allocation_id,
      'old_normal_hours',seg.normal_hours,'old_ot_hours',seg.ot_hours,'normal_hours',round(nh,2),'ot_hours',round(oh,2)));
  end loop;
  insert into public.audit_log(user_id,action,entity,entity_id,old_value,new_value)
    values(p_user_id,'remove_attendance_day','allocation',a.id::text,
      jsonb_build_object('allocation',to_jsonb(a),'attendance',case when t.id is null then null else to_jsonb(t) end),
      jsonb_build_object('status','cancelled','reason',p_reason,'work_date',a.work_date,'site_id',a.site_id,
                        'worker_id',a.worker_id,'recalculated',recalculated));
  return jsonb_build_object('ok',true,'work_date',a.work_date,'recalculated',recalculated);
end $$;
revoke all on function public.remove_attendance_day(uuid,uuid,text,timestamptz,timestamptz) from public,anon,authenticated;
grant execute on function public.remove_attendance_day(uuid,uuid,text,timestamptz,timestamptz) to service_role;

