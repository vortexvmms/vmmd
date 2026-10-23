alter table public.worker_cards add column no_expiry boolean not null default false;
alter table public.worker_cards add constraint worker_cards_no_expiry_date check (not no_expiry or expiry_date is null);
