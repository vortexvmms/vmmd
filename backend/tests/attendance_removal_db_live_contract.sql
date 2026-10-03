-- Match production's existing split-day constraint and legacy absence column.
-- Test fixture only; these are already present in production.
alter table allocations drop constraint uq_one_site_per_day;
alter table allocations add constraint uq_worker_site_per_day unique(work_date,worker_id,site_id);
alter table attendance add column absence_type text;
