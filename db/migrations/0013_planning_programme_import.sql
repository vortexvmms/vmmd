-- VCMS Planning V2.1: atomic WBS and activity programme import.
begin;

create or replace function public.import_planning_programme(
  p_project_id uuid, p_payload jsonb
) returns jsonb language plpgsql security definer set search_path=public as $$
declare
  v_schedule uuid; v_item jsonb; v_id uuid; v_parent uuid; v_wbs uuid;
  v_dates date[]; v_wbs_count integer := 0; v_activity_count integer := 0;
begin
  if coalesce(public.my_role(),'') <> 'admin' then raise exception 'Administrator only'; end if;
  select id into v_schedule from public.schedules where project_id=p_project_id and status <> 'archived';
  if v_schedule is null then raise exception 'Initialise the project schedule before importing'; end if;
  if jsonb_typeof(p_payload->'wbs') <> 'array' or jsonb_array_length(p_payload->'wbs')=0 then
    raise exception 'Import must contain at least one WBS row';
  end if;
  if jsonb_array_length(p_payload->'wbs') > 500 or
     jsonb_array_length(coalesce(p_payload->'activities','[]'::jsonb)) > 5000 then
    raise exception 'Import exceeds the permitted row limit';
  end if;
  if exists(select 1 from jsonb_array_elements(p_payload->'wbs') x
            where nullif(btrim(x->>'code'),'') is null or nullif(btrim(x->>'name'),'') is null) then
    raise exception 'Every WBS row requires code and name';
  end if;
  if exists(select 1 from jsonb_array_elements(coalesce(p_payload->'activities','[]'::jsonb)) x
            where nullif(btrim(x->>'code'),'') is null or nullif(btrim(x->>'name'),'') is null
               or nullif(btrim(x->>'wbs_code'),'') is null) then
    raise exception 'Every activity requires WBS code, activity code and name';
  end if;
  if exists(select upper(btrim(x->>'code')) from jsonb_array_elements(p_payload->'wbs') x
            group by 1 having count(*)>1) then raise exception 'Duplicate WBS code in import'; end if;
  if exists(select upper(btrim(x->>'code')) from jsonb_array_elements(coalesce(p_payload->'activities','[]'::jsonb)) x
            group by 1 having count(*)>1) then raise exception 'Duplicate activity code in import'; end if;
  if exists(select 1 from public.wbs_nodes w join jsonb_array_elements(p_payload->'wbs') x
            on upper(w.code)=upper(btrim(x->>'code')) where w.schedule_id=v_schedule) then
    raise exception 'A WBS code already exists in this schedule';
  end if;
  if exists(select 1 from public.schedule_activities a join jsonb_array_elements(coalesce(p_payload->'activities','[]'::jsonb)) x
            on upper(a.code)=upper(btrim(x->>'code')) where a.schedule_id=v_schedule) then
    raise exception 'An activity code already exists in this schedule';
  end if;

  -- Parents are resolved in repeated passes, allowing the spreadsheet rows to be in any order.
  for v_item in select * from jsonb_array_elements(p_payload->'wbs') loop
    if nullif(btrim(v_item->>'parent_code'),'') is null then
      insert into public.wbs_nodes(project_id,schedule_id,code,name,sort_order,created_by,updated_by)
      values(p_project_id,v_schedule,upper(btrim(v_item->>'code')),btrim(v_item->>'name'),v_wbs_count*10,public.my_user_id(),public.my_user_id())
      returning id into v_id; v_wbs_count:=v_wbs_count+1;
    end if;
  end loop;
  for i in 1..6 loop
    for v_item in select x from jsonb_array_elements(p_payload->'wbs') x
      where nullif(btrim(x->>'parent_code'),'') is not null
        and not exists(select 1 from public.wbs_nodes w where w.schedule_id=v_schedule and upper(w.code)=upper(btrim(x->>'code')))
    loop
      select id into v_parent from public.wbs_nodes where schedule_id=v_schedule
        and upper(code)=upper(btrim(v_item->>'parent_code')) and is_active;
      if v_parent is not null then
        insert into public.wbs_nodes(project_id,schedule_id,parent_id,code,name,sort_order,created_by,updated_by)
        values(p_project_id,v_schedule,v_parent,upper(btrim(v_item->>'code')),btrim(v_item->>'name'),v_wbs_count*10,public.my_user_id(),public.my_user_id())
        returning id into v_id; v_wbs_count:=v_wbs_count+1;
      end if;
      v_parent:=null;
    end loop;
  end loop;
  if v_wbs_count <> jsonb_array_length(p_payload->'wbs') then
    raise exception 'A parent WBS is missing or the hierarchy exceeds six levels';
  end if;

  for v_item in select * from jsonb_array_elements(coalesce(p_payload->'activities','[]'::jsonb)) loop
    select id into v_wbs from public.wbs_nodes where schedule_id=v_schedule
      and upper(code)=upper(btrim(v_item->>'wbs_code')) and is_active;
    select array_agg(distinct d::date order by d::date) into v_dates
      from jsonb_array_elements_text(v_item->'selected_dates') d;
    if v_wbs is null then raise exception 'Activity % refers to missing WBS', v_item->>'code'; end if;
    if coalesce(array_length(v_dates,1),0)=0 then raise exception 'Activity % has no working dates', v_item->>'code'; end if;
    if coalesce(v_item->>'activity_type','task')='milestone' and array_length(v_dates,1)<>1 then
      raise exception 'Milestone % must contain one working date', v_item->>'code';
    end if;
    insert into public.schedule_activities(project_id,schedule_id,wbs_id,code,name,activity_type,duration_days,
      planned_start,planned_finish,sort_order,created_by,updated_by)
    values(p_project_id,v_schedule,v_wbs,upper(btrim(v_item->>'code')),btrim(v_item->>'name'),
      coalesce(v_item->>'activity_type','task'),case when coalesce(v_item->>'activity_type','task')='milestone' then 0 else array_length(v_dates,1) end,
      v_dates[1],v_dates[array_length(v_dates,1)],v_activity_count*10,public.my_user_id(),public.my_user_id()) returning id into v_id;
    insert into public.planning_activity_dates(activity_id,project_id,work_date,selected_by)
      select v_id,p_project_id,unnest(v_dates),public.my_user_id();
    v_activity_count:=v_activity_count+1;
  end loop;
  return jsonb_build_object('ok',true,'wbs_count',v_wbs_count,'activity_count',v_activity_count);
end $$;

revoke all on function public.import_planning_programme(uuid,jsonb) from public,anon;
grant execute on function public.import_planning_programme(uuid,jsonb) to authenticated;
insert into public.schema_migrations(version,description)
values('0013','Atomic WBS and activity Excel import') on conflict(version) do nothing;
commit;
