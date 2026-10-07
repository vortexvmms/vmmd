begin;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('tipper-trip-sheets-private','tipper-trip-sheets-private',false,10485760,
array['image/jpeg','image/png','image/webp','application/pdf']) on conflict(id) do nothing;
-- Other buckets keep their existing policies. No generic authenticated policy
-- can expose this bucket; only the server service role reads/writes its objects.
create policy tipper_private_objects_isolation on storage.objects as restrictive
for all to anon,authenticated using(bucket_id<>'tipper-trip-sheets-private')
with check(bucket_id<>'tipper-trip-sheets-private');

alter table public.tipper_drivers add column if not exists phone text;
alter table public.tipper_trips
  add column if not exists site_name text not null default '',
  add column if not exists billing_mode text not null default 'legacy' check (billing_mode in ('legacy','day','night','trip')),
  add column if not exists start_time time,
  add column if not exists end_time time,
  add column if not exists break_minutes integer not null default 0 check (break_minutes between 0 and 720),
  add column if not exists normal_hours numeric(10,4),
  add column if not exists ot_hours numeric(10,4),
  add column if not exists total_hours numeric(10,4),
  add column if not exists ot_rate numeric(14,2) check (ot_rate >= 0),
  add column if not exists rate_snapshot jsonb not null default '{}',
  add column if not exists submission_id uuid;
-- Keep the original generated amount and every historical value intact.
alter table public.tipper_trips add column if not exists billed_amount numeric(16,2)
  generated always as (case when billing_mode in ('day','night')
    then round(normal_hours * transport_rate + ot_hours * coalesce(ot_rate,0),2)
    else round(quantity * transport_rate,2) end) stored;
create unique index if not exists tipper_trip_submission_uq on public.tipper_trips(submission_id) where submission_id is not null;

create or replace function public.tipper_calculate_hours() returns trigger
language plpgsql security invoker set search_path=public,pg_temp as $$
declare elapsed numeric;
begin
  if new.billing_mode in ('day','night') then
    if new.start_time is null or new.end_time is null then raise exception 'Start and end time required'; end if;
    elapsed := mod(extract(epoch from (new.end_time - new.start_time))::numeric + 86400,86400) / 60;
    if elapsed <= new.break_minutes then raise exception 'Work duration must exceed break deduction'; end if;
    new.total_hours := (elapsed - new.break_minutes)/60;
    new.normal_hours := least(new.total_hours,10);
    new.ot_hours := greatest(new.total_hours-10,0);
    if new.ot_hours > 0 and new.ot_rate is null then raise exception 'OT rate required'; end if;
    new.quantity := 1;
    new.unit_type := 'hour';
  elsif new.billing_mode='trip' then
    if new.quantity <> trunc(new.quantity) then raise exception 'Whole trip count required'; end if;
    new.start_time := null; new.end_time := null;
    new.total_hours := null; new.normal_hours := null; new.ot_hours := null;
    new.break_minutes := 0; new.unit_type := 'trip';
  end if;
  return new;
end $$;
revoke all on function public.tipper_calculate_hours() from public,anon;
drop trigger if exists tipper_hours_before_write on public.tipper_trips;
create trigger tipper_hours_before_write before insert or update on public.tipper_trips
for each row execute function public.tipper_calculate_hours();

create table public.tipper_rate_rules (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.tipper_clients(id),
  site_name text not null check(length(trim(site_name))>0),
  billing_mode text not null check(billing_mode in ('day','night','trip')),
  transport_rate numeric(14,2) not null check(transport_rate>=0),
  ot_rate numeric(14,2) check(ot_rate>=0),
  break_minutes integer not null check(break_minutes between 0 and 720),
  effective_from date not null,
  active boolean not null default true,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  unique(client_id,site_name,billing_mode,effective_from)
);
create index tipper_rules_client_idx on public.tipper_rate_rules(client_id);
alter table public.tipper_rate_rules enable row level security;
revoke all on public.tipper_rate_rules from anon;
grant select,insert,update,delete on public.tipper_rate_rules to authenticated,service_role;
create policy tipper_rules_read on public.tipper_rate_rules for select to authenticated
using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','logistics_sup'));
create policy tipper_rules_admin on public.tipper_rate_rules for all to authenticated
using(public.my_role()='admin') with check(public.my_role()='admin');

create table public.tipper_driver_links (
  id uuid primary key default gen_random_uuid(),
  driver_id uuid not null unique references public.tipper_drivers(id),
  token_hash text not null unique,
  active boolean not null default true,
  created_by uuid not null references public.users(id),
  created_at timestamptz not null default now()
);
alter table public.tipper_driver_links enable row level security;
revoke all on public.tipper_driver_links from anon,authenticated;
grant select,insert,update,delete on public.tipper_driver_links to service_role;

create table public.tipper_submissions (
  id uuid primary key default gen_random_uuid(),
  driver_id uuid not null references public.tipper_drivers(id),
  link_id uuid not null references public.tipper_driver_links(id),
  file_hash text not null,
  source_image_key text not null,
  source_image_url text not null,
  source_mime text not null,
  original_name text not null,
  extracted_data jsonb not null default '{}',
  confirmed_data jsonb,
  trip_date date,
  status text not null default 'draft' check(status in ('draft','pending','approved','rejected')),
  quality_warnings jsonb not null default '[]',
  reviewed_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  submitted_at timestamptz,
  unique(driver_id,file_hash)
);
create table public.tipper_portal_links (
  id uuid primary key default gen_random_uuid(),
  token_hash text not null unique,
  active boolean not null default true,
  created_by uuid not null references public.users(id),
  created_at timestamptz not null default now()
);
alter table public.tipper_portal_links enable row level security;
revoke all on public.tipper_portal_links from anon,authenticated;
grant select,insert,update,delete on public.tipper_portal_links to service_role;
create index tipper_submission_month_idx on public.tipper_submissions(trip_date,status);
create index tipper_submission_link_idx on public.tipper_submissions(link_id);
alter table public.tipper_submissions enable row level security;
revoke all on public.tipper_submissions from anon,authenticated;
grant select on public.tipper_submissions to authenticated;
grant select,insert,update,delete on public.tipper_submissions to service_role;
create policy tipper_submissions_read on public.tipper_submissions for select to authenticated
using(public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','logistics_sup'));
alter table public.tipper_trips add constraint tipper_submission_fk foreign key(submission_id) references public.tipper_submissions(id);

-- The server checks reviewer permissions first. Service-role only, atomic and idempotent.
create function public.tipper_approve_submission(p_id uuid,p_trip jsonb,p_user uuid)
returns jsonb language plpgsql security invoker set search_path=public,pg_temp as $$
declare s public.tipper_submissions; t public.tipper_trips; v public.tipper_trips;
begin
  select * into s from public.tipper_submissions where id=p_id for update;
  if not found then raise exception 'Submission not found'; end if;
  if s.status='approved' then
    select * into t from public.tipper_trips where submission_id=p_id;
    return to_jsonb(t);
  end if;
  if s.status<>'pending' then raise exception 'Submission is not pending'; end if;
  v := jsonb_populate_record(null::public.tipper_trips,p_trip);
  insert into public.tipper_trips(client_id,provider_id,work_type_id,driver_id,driver_name,
    trip_sheet_no,trip_date,do_no,truck_no,pickup_location,delivery_location,material_type,
    quantity,unit_type,transport_rate,source,source_image_url,source_image_key,
    created_by,updated_by,review_status,site_name,billing_mode,start_time,end_time,
    break_minutes,ot_rate,rate_snapshot,submission_id)
  values(v.client_id,v.provider_id,v.work_type_id,s.driver_id,v.driver_name,
    v.trip_sheet_no,v.trip_date,v.do_no,v.truck_no,coalesce(v.pickup_location,''),coalesce(v.delivery_location,''),coalesce(v.material_type,''),
    v.quantity,v.unit_type,v.transport_rate,'image_extract',s.source_image_url,s.source_image_key,
    p_user,p_user,'approved',v.site_name,v.billing_mode,v.start_time,v.end_time,
    v.break_minutes,v.ot_rate,v.rate_snapshot,p_id) returning * into t;
  update public.tipper_submissions set status='approved',reviewed_by=p_user where id=p_id;
  return to_jsonb(t);
end $$;
revoke all on function public.tipper_approve_submission(uuid,jsonb,uuid) from public,anon,authenticated;
grant execute on function public.tipper_approve_submission(uuid,jsonb,uuid) to service_role;
notify pgrst,'reload schema';
commit;
