-- VCMS Mobile Performance Indexes — Release 1
-- Safe to run more than once in the Supabase SQL editor.
-- No operational records are changed or deleted.

create index if not exists idx_notifications_user_created
  on public.notifications (user_id, created_at desc);

create index if not exists idx_notifications_user_unread
  on public.notifications (user_id, created_at desc)
  where read_at is null;

create index if not exists idx_site_supervisors_user_site
  on public.site_supervisors (user_id, site_id);

create index if not exists idx_allocations_date_site_status
  on public.allocations (work_date, site_id, status);

create index if not exists idx_allocations_worker_date
  on public.allocations (worker_id, work_date);

-- These newer module tables may not exist in older installations. Create their
-- indexes only when the table is present, so this migration remains portable.
do $$
begin
  if to_regclass('public.manpower_requests') is not null then
    execute 'create index if not exists idx_manpower_requests_date_site on public.manpower_requests (request_date, site_id)';
    execute 'create index if not exists idx_manpower_requests_worker_date on public.manpower_requests (worker_id, request_date)';
  end if;
  if to_regclass('public.todos') is not null then
    execute 'create index if not exists idx_todos_user_done_position on public.todos (user_id, done, position)';
  end if;
  if to_regclass('public.worker_cards') is not null then
    execute 'create index if not exists idx_worker_cards_worker_expiry on public.worker_cards (worker_id, expiry_date)';
  end if;
end $$;

analyze public.notifications;
analyze public.site_supervisors;
analyze public.allocations;
