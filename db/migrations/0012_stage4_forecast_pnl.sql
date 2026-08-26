-- VCMS Planning V2.1 Stage 4: operational Project Cost & Forecast P&L.
begin;

create table if not exists public.planning_project_values(
 project_id uuid primary key references public.projects(id) on delete cascade,
 currency text not null default 'SGD', original_value numeric(18,2) not null default 0 check(original_value>=0),
 approved_variations numeric(18,2) not null default 0 check(approved_variations>=0),
 omissions numeric(18,2) not null default 0 check(omissions>=0), version integer not null default 1,
 updated_by uuid references public.users(id), created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);

create table if not exists public.planning_ctc_forecasts(
 project_id uuid primary key references public.projects(id) on delete cascade,
 approved_basis text not null default 'automatic' check(approved_basis in('automatic','manual')),
 manual_amount numeric(18,2) check(manual_amount is null or manual_amount>=0), manual_reason text,
 approved_by uuid references public.users(id), approved_at timestamptz, version integer not null default 1,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 check(approved_basis='automatic' or (manual_amount is not null and nullif(trim(manual_reason),'') is not null))
);

create table if not exists public.planning_pnl_snapshots(
 id uuid primary key default gen_random_uuid(), project_id uuid not null references public.projects(id) on delete cascade,
 data_date date not null, snapshot jsonb not null, source_version jsonb not null default '{}'::jsonb,
 created_by uuid references public.users(id), created_at timestamptz not null default now()
);
create index if not exists idx_planning_pnl_snapshots_project on public.planning_pnl_snapshots(project_id,data_date desc,created_at desc);

drop trigger if exists trg_planning_project_values_updated on public.planning_project_values;
create trigger trg_planning_project_values_updated before update on public.planning_project_values for each row execute function public.set_updated_at();
drop trigger if exists trg_planning_ctc_updated on public.planning_ctc_forecasts;
create trigger trg_planning_ctc_updated before update on public.planning_ctc_forecasts for each row execute function public.set_updated_at();
create or replace function public.planning_bump_commercial_version() returns trigger language plpgsql set search_path=public as $$
begin new.version:=old.version+1; return new; end $$;
drop trigger if exists trg_planning_project_values_version on public.planning_project_values;
create trigger trg_planning_project_values_version before update on public.planning_project_values for each row execute function public.planning_bump_commercial_version();
drop trigger if exists trg_planning_ctc_version on public.planning_ctc_forecasts;
create trigger trg_planning_ctc_version before update on public.planning_ctc_forecasts for each row execute function public.planning_bump_commercial_version();

alter table public.planning_project_values enable row level security;
alter table public.planning_ctc_forecasts enable row level security;
alter table public.planning_pnl_snapshots enable row level security;
create policy planning_project_values_admin on public.planning_project_values for all using(public.my_role()='admin') with check(public.my_role()='admin');
create policy planning_ctc_admin on public.planning_ctc_forecasts for all using(public.my_role()='admin') with check(public.my_role()='admin');
create policy planning_pnl_snapshots_admin on public.planning_pnl_snapshots for all using(public.my_role()='admin') with check(public.my_role()='admin');
grant select,insert,update on public.planning_project_values,public.planning_ctc_forecasts to authenticated;
grant select,insert on public.planning_pnl_snapshots to authenticated;

create or replace function public.planning_project_pnl_summary(p_project_id uuid,p_data_date date default current_date)
returns jsonb language plpgsql security definer set search_path=public as $$
declare c jsonb; v public.planning_project_values%rowtype; f public.planning_ctc_forecasts%rowtype;
 actual numeric:=0; current_value numeric:=0; auto_ctc numeric:=0; approved_ctc numeric:=0;
 final_cost numeric:=0; profit numeric:=0; margin numeric:=0; planned_cost numeric:=0; progress numeric:=0;
begin
 if coalesce(public.my_role(),'')<>'admin' then raise exception 'forecast P&L access denied'; end if;
 c:=public.planning_project_cost_summary(p_project_id,null,p_data_date);
 actual:=coalesce((c->>'actual_total')::numeric,0);
 select * into v from planning_project_values where project_id=p_project_id;
 select * into f from planning_ctc_forecasts where project_id=p_project_id;
 current_value:=coalesce(v.original_value,0)+coalesce(v.approved_variations,0)-coalesce(v.omissions,0);
 select coalesce(sum(a.budgeted_cost),0),coalesce(sum(a.budgeted_cost*(1-coalesce(sa.percent_complete,0)/100)),0)
 into planned_cost,auto_ctc from activity_resource_assignments a join schedule_activities sa on sa.id=a.activity_id
 where a.project_id=p_project_id and a.is_active and sa.is_active;
 approved_ctc:=case when f.approved_basis='manual' then coalesce(f.manual_amount,0) else auto_ctc end;
 final_cost:=actual+approved_ctc; profit:=current_value-final_cost;
 margin:=case when current_value<>0 then profit/current_value*100 else 0 end;
 select coalesce(sum(coalesce(actual_quantity,0))/nullif(sum(target_quantity),0)*100,0) into progress
 from schedule_activities where project_id=p_project_id and is_active and target_quantity is not null;
 return jsonb_build_object('project_id',p_project_id,'data_date',p_data_date,'currency',coalesce(v.currency,'SGD'),
  'original_value',coalesce(v.original_value,0),'approved_variations',coalesce(v.approved_variations,0),'omissions',coalesce(v.omissions,0),'current_project_value',round(current_value,2),
  'costs',c,'planned_resource_cost',round(planned_cost,2),'actual_cost_variance',round(planned_cost-actual,2),
  'automatic_ctc',round(auto_ctc,2),'manual_ctc',f.manual_amount,'manual_reason',f.manual_reason,'approved_basis',coalesce(f.approved_basis,'automatic'),
  'approved_ctc',round(approved_ctc,2),'approved_by',f.approved_by,'approved_at',f.approved_at,
  'forecast_final_cost',round(final_cost,2),'forecast_profit_loss',round(profit,2),'forecast_margin_percent',round(margin,2),
  'physical_progress_percent',round(least(100,progress),2),'management_note','Operational forecast only; not an accounting or statutory financial statement.');
end $$;
revoke all on function public.planning_project_pnl_summary(uuid,date) from public,anon;
grant execute on function public.planning_project_pnl_summary(uuid,date) to authenticated;

create or replace function public.create_planning_pnl_snapshot(p_project_id uuid,p_data_date date)
returns uuid language plpgsql security definer set search_path=public as $$
declare sid uuid; snap jsonb; pv integer; cv integer;
begin
 if coalesce(public.my_role(),'')<>'admin' then raise exception 'forecast P&L access denied'; end if;
 snap:=public.planning_project_pnl_summary(p_project_id,p_data_date);
 select version into pv from planning_project_values where project_id=p_project_id;
 select version into cv from planning_ctc_forecasts where project_id=p_project_id;
 insert into planning_pnl_snapshots(project_id,data_date,snapshot,source_version,created_by)
 values(p_project_id,p_data_date,snap,jsonb_build_object('project_value',coalesce(pv,0),'ctc',coalesce(cv,0)),public.my_user_id()) returning id into sid;
 return sid;
end $$;
revoke all on function public.create_planning_pnl_snapshot(uuid,date) from public,anon;
grant execute on function public.create_planning_pnl_snapshot(uuid,date) to authenticated;

insert into public.schema_migrations(version,description) values('0012','Planning V2.1 Stage 4 operational forecast P&L and snapshots') on conflict(version) do nothing;
commit;
