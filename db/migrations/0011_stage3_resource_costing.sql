-- VCMS Planning V2.1 Stage 3: private resource costing and PR forecast.
begin;

create table if not exists public.planning_manpower_rates(
 id uuid primary key default gen_random_uuid(), project_id uuid not null references public.projects(id) on delete cascade,
 worker_id uuid references public.workers(id) on delete cascade, trade text,
 normal_rate numeric(14,2) not null default 0 check(normal_rate>=0),
 ot_rate numeric(14,2) not null default 0 check(ot_rate>=0),
 sunday_ph_rate numeric(14,2) not null default 0 check(sunday_ph_rate>=0),
 effective_from date not null, effective_to date,
 is_active boolean not null default true, created_by uuid references public.users(id),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 check(not(worker_id is not null and nullif(trim(trade),'') is not null)),
 check(effective_to is null or effective_to>=effective_from)
);
create index if not exists idx_planning_manpower_rates_lookup on public.planning_manpower_rates(project_id,worker_id,trade,effective_from,effective_to) where is_active;

create table if not exists public.planning_resource_rates(
 id uuid primary key default gen_random_uuid(), project_id uuid not null references public.projects(id) on delete cascade,
 resource_type text not null check(resource_type in('material','equipment')),
 resource_name text not null, unit text,
 unit_rate numeric(14,2) not null default 0 check(unit_rate>=0),
 hourly_rate numeric(14,2) not null default 0 check(hourly_rate>=0),
 daily_rate numeric(14,2) not null default 0 check(daily_rate>=0),
 fixed_rate numeric(14,2) not null default 0 check(fixed_rate>=0),
 effective_from date not null, effective_to date, is_active boolean not null default true,
 created_by uuid references public.users(id), created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 check(effective_to is null or effective_to>=effective_from)
);
create index if not exists idx_planning_resource_rates_lookup on public.planning_resource_rates(project_id,resource_type,lower(resource_name),effective_from,effective_to) where is_active;

create table if not exists public.planning_other_direct_costs(
 id uuid primary key default gen_random_uuid(), project_id uuid not null references public.projects(id) on delete cascade,
 activity_id uuid references public.schedule_activities(id) on delete set null,
 cost_date date not null, category text not null check(category in('subcontractor','transport','disposal','testing_permit','miscellaneous')),
 description text not null, amount numeric(16,2) not null check(amount>=0), remarks text,
 created_by uuid references public.users(id), created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create index if not exists idx_planning_other_costs_project_date on public.planning_other_direct_costs(project_id,cost_date);

drop trigger if exists trg_planning_manpower_rates_updated on public.planning_manpower_rates;
create trigger trg_planning_manpower_rates_updated before update on public.planning_manpower_rates for each row execute function public.set_updated_at();
drop trigger if exists trg_planning_resource_rates_updated on public.planning_resource_rates;
create trigger trg_planning_resource_rates_updated before update on public.planning_resource_rates for each row execute function public.set_updated_at();
drop trigger if exists trg_planning_other_costs_updated on public.planning_other_direct_costs;
create trigger trg_planning_other_costs_updated before update on public.planning_other_direct_costs for each row execute function public.set_updated_at();

alter table public.planning_manpower_rates enable row level security;
alter table public.planning_resource_rates enable row level security;
alter table public.planning_other_direct_costs enable row level security;
create policy planning_manpower_rates_admin on public.planning_manpower_rates for all using(public.my_role()='admin') with check(public.my_role()='admin');
create policy planning_resource_rates_admin on public.planning_resource_rates for all using(public.my_role()='admin') with check(public.my_role()='admin');
create policy planning_other_costs_admin on public.planning_other_direct_costs for all using(public.my_role()='admin') with check(public.my_role()='admin');
grant select,insert,update on public.planning_manpower_rates,public.planning_resource_rates,public.planning_other_direct_costs to authenticated;

create or replace function public.planning_project_cost_summary(p_project_id uuid,p_from date default null,p_to date default null)
returns jsonb language plpgsql security definer set search_path=public as $$
declare v_from date:=coalesce(p_from,date '1900-01-01'); v_to date:=coalesce(p_to,date '2999-12-31');
 v_manpower numeric:=0; v_material numeric:=0; v_equipment numeric:=0; v_other numeric:=0; v_pr numeric:=0;
begin
 if coalesce(public.my_role(),'')<>'admin' then raise exception 'commercial cost access denied'; end if;

 select coalesce(sum(case when a.day_type in('SUN','PH')
   then (a.normal_hours+a.ot_hours)*coalesce(rate.sunday_ph_rate,0)
   else a.normal_hours*coalesce(rate.normal_rate,0)+a.ot_hours*coalesce(rate.ot_rate,0) end),0)
 into v_manpower
 from attendance a join allocations al on al.id=a.allocation_id join sites s on s.id=al.site_id join workers w on w.id=al.worker_id
 left join lateral(select r.* from planning_manpower_rates r where r.project_id=p_project_id and r.is_active
   and r.effective_from<=al.work_date and (r.effective_to is null or r.effective_to>=al.work_date)
   and (r.worker_id=w.id or (r.worker_id is null and nullif(trim(r.trade),'') is not null and lower(trim(r.trade))=lower(trim(coalesce(w.trade,'')))) or (r.worker_id is null and nullif(trim(r.trade),'') is null))
   order by case when r.worker_id=w.id then 1 when nullif(trim(r.trade),'') is not null then 2 else 3 end,r.effective_from desc limit 1) rate on true
 where s.project_id=p_project_id and al.work_date between v_from and v_to and al.status='allocated' and a.present;

 select coalesce(sum(coalesce(nullif(m.item->>'qty','')::numeric,0)*coalesce(rate.unit_rate,0)),0) into v_material
 from daily_reports d join sites s on s.id=d.site_id cross join lateral jsonb_array_elements(coalesce(d.materials,'[]'::jsonb)) m(item)
 left join lateral(select r.unit_rate from planning_resource_rates r where r.project_id=p_project_id and r.resource_type='material' and r.is_active
   and lower(trim(r.resource_name))=lower(trim(m.item->>'name')) and r.effective_from<=d.report_date and (r.effective_to is null or r.effective_to>=d.report_date)
   order by r.effective_from desc limit 1) rate on true
 where s.project_id=p_project_id and d.report_date between v_from and v_to;

 select coalesce(sum(case
   when coalesce(nullif(e.item->>'total','')::numeric,0)>0 then (e.item->>'total')::numeric*coalesce(rate.hourly_rate,0)
   when coalesce(nullif(e.item->>'days','')::numeric,0)>0 then (e.item->>'days')::numeric*coalesce(rate.daily_rate,0)
   else coalesce(nullif(e.item->>'count','')::numeric,0)*coalesce(rate.fixed_rate,0) end),0) into v_equipment
 from daily_reports d join sites s on s.id=d.site_id cross join lateral jsonb_array_elements(coalesce(d.equipment,'[]'::jsonb)) e(item)
 left join lateral(select r.* from planning_resource_rates r where r.project_id=p_project_id and r.resource_type='equipment' and r.is_active
   and lower(trim(r.resource_name))=lower(trim(e.item->>'name')) and r.effective_from<=d.report_date and (r.effective_to is null or r.effective_to>=d.report_date)
   order by r.effective_from desc limit 1) rate on true
 where s.project_id=p_project_id and d.report_date between v_from and v_to;

 select coalesce(sum(amount),0) into v_other from planning_other_direct_costs where project_id=p_project_id and cost_date between v_from and v_to;
 select coalesce(sum(coalesce(nullif(i.item->>'amount','')::numeric,0)),0) into v_pr
 from purchase_requisitions p join sites s on lower(trim(s.site_name))=lower(trim(p.site_name))
 cross join lateral jsonb_array_elements(coalesce(p.items,'[]'::jsonb)) i(item)
 where s.project_id=p_project_id and p.pr_date between v_from and v_to and coalesce(p.status,'submitted')<>'cancelled';

 return jsonb_build_object('project_id',p_project_id,'from',p_from,'to',p_to,
   'manpower_actual',round(v_manpower,2),'material_actual',round(v_material,2),'equipment_actual',round(v_equipment,2),
   'other_actual',round(v_other,2),'actual_total',round(v_manpower+v_material+v_equipment+v_other,2),
   'pr_requested_forecast',round(v_pr,2));
end $$;
revoke all on function public.planning_project_cost_summary(uuid,date,date) from public,anon;
grant execute on function public.planning_project_cost_summary(uuid,date,date) to authenticated;

insert into public.schema_migrations(version,description) values('0011','Planning V2.1 Stage 3 private resource costing and PR forecast') on conflict(version) do nothing;
commit;
