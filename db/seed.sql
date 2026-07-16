-- ============================================================
-- VMMS — seed.sql  ·  Phase 2
-- Starting data: 5 confirmed sites (Rev 5 §5.3), sample workers
-- for testing, OT settings (spec §6.2), sample public holidays.
-- Run THIRD (after schema.sql and rls_policies.sql).
-- Safe to re-run: uses ON CONFLICT DO NOTHING / DO UPDATE.
-- ============================================================

-- ---------- 5 confirmed sites ----------
insert into public.sites (site_code, site_name) values
  ('PKJV-T5',  'PKJV-T5'),
  ('PSCH-SB',  'PSCH-SOILBUILD'),
  ('PCS',      'PCS'),
  ('TWRP',     'TWRP'),
  ('TUAS-LOT', 'TUAS LOT')
on conflict (site_code) do nothing;

-- ---------- sample workers (TEST DATA — replace before go-live) ----------
insert into public.workers (worker_code, name, status) values
  ('W001', 'SAMPLE Raj Kumar',        'active'),
  ('W002', 'SAMPLE Mani Selvam',      'active'),
  ('W003', 'SAMPLE Ravi Chandran',    'active'),
  ('W004', 'SAMPLE John Peter',       'active'),
  ('W005', 'SAMPLE Siva Murugan',     'active'),
  ('W006', 'SAMPLE Kumar Vel',        'active'),
  ('W007', 'SAMPLE Arun Prakash',     'active'),
  ('W008', 'SAMPLE Ahmed Rahim',      'active'),
  ('W009', 'SAMPLE Zhang Wei',        'active'),
  ('W010', 'SAMPLE Bala Krishnan',    'active'),
  ('W011', 'SAMPLE Suresh Babu',      'on_leave'),
  ('W012', 'SAMPLE Dinesh Raja',      'inactive')
on conflict (worker_code) do nothing;

-- ---------- OT & system settings (spec §6.2, confirmed Rev 3) ----------
insert into public.settings (key, value, effective_from) values
  ('default_start_time',      '"08:00"',                        '2026-07-01'),
  ('lunch_minutes',           '60',                             '2026-07-01'),
  ('lunch_window',            '{"from": "12:00", "to": "13:00"}', '2026-07-01'),
  ('no_lunch_if_end_by',      '"12:00"',                        '2026-07-01'),
  ('weekday_normal_hours',    '8',                              '2026-07-01'),
  ('saturday_ot_after',       '"12:00"',                        '2026-07-01'),
  ('sunday_ph_all_ot',        'true',                           '2026-07-01'),
  ('attendance_lock_days',    '7',                              '2026-07-01'),
  ('allocation_msg_header',   '"*MANPOWER DISTRIBUTION*"',      '2026-07-01'),
  ('home_leave_section_name', '"HOME LEAVE"',                   '2026-07-01')
on conflict (key) do update set value = excluded.value;

-- ---------- public holidays (PARTIAL SAMPLE — Admin must complete
--            the official Singapore list for each year; verify
--            against the MOM gazetted holiday list) ----------
insert into public.public_holidays (holiday_date, description) values
  ('2026-01-01', 'New Year''s Day'),
  ('2026-05-01', 'Labour Day'),
  ('2026-08-09', 'National Day'),
  ('2026-08-10', 'National Day (observed) — VERIFY'),
  ('2026-12-25', 'Christmas Day')
on conflict (holiday_date) do nothing;

-- ============================================================
-- Done. Verify in Table Editor:
--   sites → 5 rows · workers → 12 rows · settings → 10 rows
-- ============================================================
