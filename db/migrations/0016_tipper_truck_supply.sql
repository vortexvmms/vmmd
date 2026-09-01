begin;

-- Equipment & Machineries · Tipper Truck Supply
-- Master data follows the user's current workbook and daily trip-sheet process.
create table if not exists public.tipper_clients (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  active boolean not null default true,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.tipper_providers (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  active boolean not null default true,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.tipper_work_types (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  active boolean not null default true,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.tipper_drivers (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  provider_id uuid references public.tipper_providers(id) on delete set null,
  truck_no text,
  active boolean not null default true,
  created_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(name, provider_id)
);

create table if not exists public.tipper_trips (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.tipper_clients(id),
  provider_id uuid not null references public.tipper_providers(id),
  work_type_id uuid not null references public.tipper_work_types(id),
  driver_id uuid references public.tipper_drivers(id) on delete set null,
  driver_name text,
  trip_sheet_no text not null,
  trip_date date not null,
  do_no text not null,
  truck_no text not null,
  pickup_location text not null,
  delivery_location text not null,
  material_type text not null,
  quantity numeric(14,3) not null check (quantity > 0),
  unit_type text not null default 'load'
    check (unit_type in ('load','tonnage','hour','meter','trip','day')),
  transport_rate numeric(14,2) not null check (transport_rate >= 0),
  transport_amount numeric(16,2) generated always as (round(quantity * transport_rate, 2)) stored,
  source text not null default 'manual' check (source in ('manual','image_extract')),
  source_image_url text,
  source_image_key text,
  review_status text not null default 'approved' check (review_status in ('pending','approved','rejected')),
  extraction_confidence numeric(5,2),
  created_by uuid not null references public.users(id),
  updated_by uuid references public.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index if not exists tipper_trips_client_sheet_uq
  on public.tipper_trips(client_id, trip_sheet_no);
create index if not exists tipper_trips_month_idx on public.tipper_trips(trip_date desc);
create index if not exists tipper_trips_client_month_idx on public.tipper_trips(client_id, trip_date desc);
create index if not exists tipper_trips_provider_month_idx on public.tipper_trips(provider_id, trip_date desc);

create table if not exists public.tipper_import_batches (
  id uuid primary key default gen_random_uuid(),
  status text not null default 'processing' check (status in ('processing','review','completed','failed')),
  total_files integer not null check (total_files between 1 and 30),
  processed_files integer not null default 0,
  failed_files integer not null default 0,
  created_by uuid not null references public.users(id),
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists public.tipper_import_items (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references public.tipper_import_batches(id) on delete cascade,
  original_name text not null,
  image_url text not null,
  image_key text not null unique,
  status text not null default 'extracted' check (status in ('extracted','approved','failed')),
  extracted_data jsonb not null default '{}'::jsonb,
  confidence numeric(5,2),
  warnings jsonb not null default '[]'::jsonb,
  error_message text,
  trip_id uuid references public.tipper_trips(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists tipper_import_items_batch_idx on public.tipper_import_items(batch_id, created_at);

-- Seed the master data supplied by the user. Existing names are preserved.
insert into public.tipper_clients(name) values ('PKJV-T5-MSP'), ('COJV-T5-SUB')
on conflict(name) do nothing;
insert into public.tipper_providers(name) values ('VORTEX'), ('SVP'), ('VEL')
on conflict(name) do nothing;
insert into public.tipper_work_types(name) values ('Day Work'), ('Trip Work'), ('Night Work'), ('Hourly')
on conflict(name) do nothing;

-- All module data is restricted to signed-in equipment coordinators.
alter table public.tipper_clients enable row level security;
alter table public.tipper_providers enable row level security;
alter table public.tipper_work_types enable row level security;
alter table public.tipper_drivers enable row level security;
alter table public.tipper_trips enable row level security;
alter table public.tipper_import_batches enable row level security;
alter table public.tipper_import_items enable row level security;

do $$
declare t text;
begin
  foreach t in array array['tipper_clients','tipper_providers','tipper_work_types','tipper_drivers'] loop
    execute format('drop policy if exists %I_read on public.%I', t, t);
    execute format('create policy %I_read on public.%I for select to authenticated using (public.my_role() in (''admin'',''general_manager'',''operation_manager'',''hr_assistant'',''main_sup'',''wshc_lead'',''logistics_sup''))', t, t);
    execute format('drop policy if exists %I_admin_write on public.%I', t, t);
    execute format('create policy %I_admin_write on public.%I for all to authenticated using (public.my_role() = ''admin'') with check (public.my_role() = ''admin'')', t, t);
  end loop;
end $$;

drop policy if exists tipper_trips_read on public.tipper_trips;
create policy tipper_trips_read on public.tipper_trips for select to authenticated
using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','logistics_sup'));
drop policy if exists tipper_trips_insert on public.tipper_trips;
create policy tipper_trips_insert on public.tipper_trips for insert to authenticated
with check (created_by = public.my_user_id() and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','logistics_sup'));
drop policy if exists tipper_trips_update on public.tipper_trips;
create policy tipper_trips_update on public.tipper_trips for update to authenticated
using (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'))
with check (public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead'));
drop policy if exists tipper_trips_delete on public.tipper_trips;
create policy tipper_trips_delete on public.tipper_trips for delete to authenticated
using (public.my_role() = 'admin');

drop policy if exists tipper_batches_own on public.tipper_import_batches;
create policy tipper_batches_own on public.tipper_import_batches for all to authenticated
using (created_by = public.my_user_id() or public.my_role() = 'admin')
with check (created_by = public.my_user_id() and public.my_role() in ('admin','general_manager','operation_manager','hr_assistant','main_sup','wshc_lead','logistics_sup'));
drop policy if exists tipper_items_own on public.tipper_import_items;
create policy tipper_items_own on public.tipper_import_items for all to authenticated
using (exists(select 1 from public.tipper_import_batches b where b.id=batch_id and (b.created_by=public.my_user_id() or public.my_role()='admin')))
with check (exists(select 1 from public.tipper_import_batches b where b.id=batch_id and b.created_by=public.my_user_id()));

grant select on public.tipper_clients, public.tipper_providers, public.tipper_work_types, public.tipper_drivers to authenticated;
grant insert, update, delete on public.tipper_clients, public.tipper_providers, public.tipper_work_types, public.tipper_drivers to authenticated;
grant select, insert, update, delete on public.tipper_trips to authenticated;
grant select, insert, update on public.tipper_import_batches, public.tipper_import_items to authenticated;

insert into public.schema_migrations(version, description)
values('0016', 'Equipment and Machineries tipper-truck supply, bulk image extraction and TRP reporting')
on conflict(version) do nothing;

commit;
