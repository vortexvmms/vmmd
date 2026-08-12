-- VCMS: optional task deadline. Run once in Supabase SQL Editor.
alter table public.todos
  add column if not exists due_date date;

create index if not exists todos_user_due_date_idx
  on public.todos (user_id, due_date)
  where due_date is not null and done = false;
