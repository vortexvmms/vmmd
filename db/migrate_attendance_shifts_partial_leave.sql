-- VCMS attendance: night shifts and half-day leave (backward compatible)
alter table public.attendance
  add column if not exists shift_type text not null default 'day',
  add column if not exists partial_leave_type text,
  add column if not exists leave_portion text,
  add column if not exists leave_value numeric(3,2) not null default 0;

alter table public.attendance drop constraint if exists attendance_shift_type_check;
alter table public.attendance add constraint attendance_shift_type_check
  check (shift_type in ('day','night','custom'));

alter table public.attendance drop constraint if exists attendance_partial_leave_type_check;
alter table public.attendance add constraint attendance_partial_leave_type_check
  check (partial_leave_type is null or partial_leave_type in ('mc','al','ul'));

alter table public.attendance drop constraint if exists attendance_leave_portion_check;
alter table public.attendance add constraint attendance_leave_portion_check
  check (leave_portion is null or leave_portion in ('first_half','second_half'));

alter table public.attendance drop constraint if exists attendance_leave_value_check;
alter table public.attendance add constraint attendance_leave_value_check
  check (leave_value in (0,0.5,1));

comment on column public.attendance.shift_type is 'day, night or custom; overnight hours belong to the shift start date';
comment on column public.attendance.partial_leave_type is 'MC, AL or UL taken for part of a day while present=true';
comment on column public.attendance.leave_portion is 'first_half or second_half';
comment on column public.attendance.leave_value is 'Leave-day value used by reports: 0, 0.5 or 1';
