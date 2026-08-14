-- VCMS Camera V1 · Stage 3
-- Cloud photo metadata. Optimized JPEG objects remain in existing Cloudflare R2.
begin;

create table if not exists public.camera_photos (
  photo_id uuid primary key,
  project_id uuid not null references public.dpr_projects(id),
  item_of_work_id uuid references public.camera_work_items(id) on delete set null,
  item_of_work_name text not null,
  item_of_work_source text not null check (item_of_work_source in ('directory','manual')),
  activity_id uuid references public.camera_activities(id) on delete set null,
  activity_name text not null,
  activity_source text not null check (activity_source in ('directory','manual')),
  capture_source text not null check (capture_source in ('camera','gallery')),
  captured_at timestamptz,
  imported_at timestamptz,
  uploaded_at timestamptz,
  uploaded_by uuid not null references public.users(id),
  r2_object_key text not null unique,
  public_url text not null,
  file_size integer not null default 0,
  width integer not null default 1600,
  height integer not null default 1200,
  input_format text,
  output_format text not null default 'image/jpeg',
  sync_status text not null default 'uploaded' check (sync_status in ('local','pending','uploading','uploaded','failed')),
  dpr_status text not null default 'available' check (dpr_status in ('available','used','archived')),
  dpr_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists camera_photos_project_capture_idx on public.camera_photos(project_id, captured_at desc);
create index if not exists camera_photos_uploader_idx on public.camera_photos(uploaded_by, created_at desc);
alter table public.camera_photos enable row level security;

drop policy if exists camera_photos_read on public.camera_photos;
create policy camera_photos_read on public.camera_photos for select to authenticated using (true);
drop policy if exists camera_photos_insert on public.camera_photos;
create policy camera_photos_insert on public.camera_photos for insert to authenticated
  with check (uploaded_by = public.my_user_id());
drop policy if exists camera_photos_update_own on public.camera_photos;
create policy camera_photos_update_own on public.camera_photos for update to authenticated
  using (uploaded_by = public.my_user_id() or public.my_role() in ('admin','general_manager','operation_manager','main_sup','wshc_lead'))
  with check (uploaded_by = public.my_user_id() or public.my_role() in ('admin','general_manager','operation_manager','main_sup','wshc_lead'));

commit;
