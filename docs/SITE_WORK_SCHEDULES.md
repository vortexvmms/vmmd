# Site work schedules

Open Sites and select a site to edit Work schedule & OT rules. An unchanged site, including a newly created site, inherits the existing engine: 08:00 start, 12:00–13:00 lunch, 17:00 scheduled finish, 8 weekday basic hours, Saturday basic hours before noon up to 4, and Sunday/public holiday all OT. Existing half-hour downward OT rounding remains unchanged.

PCS-GBM is configured from 2026-10-05: 07:00 start, 11:30–12:00 lunch, 16:30 scheduled finish, 8 weekday basic hours and the first 4 worked Saturday hours basic. Its lunch deduction counts the actual overlap with its lunch window. A full shift is 9 worked hours: weekday 8 basic + 1 OT; Saturday 4 basic + 5 OT; Sunday/holiday 9 OT.

Settings are effective-dated. New attendance captures a schedule snapshot; saved attendance keeps its original snapshot, including the legacy engine for attendance recorded before this release. Settings do not automatically mark a worker present, fill actual end times, submit attendance or rewrite old dates. The scheduled finish adds an Attendance shortcut.

A worker transferring between sites receives one basic-hours allowance for the day, set by the first chronological working segment, with each segment's saved lunch and Saturday rules. Reports consume stored normal/OT hours. Day removal recalculates remaining segments with these same snapshots while retaining the cancelled attendance and audit history.

## Release and recovery

Apply `supabase/migrations/20261005094040_site_work_schedules.sql` before publishing the backend/frontend; the additional columns are compatible with the previous release. Do not run a bulk historical recalculation. Verify the pre/post historical attendance fingerprint, PCS-GBM settings, new backend OpenAPI schema and Sites form. Database tests cover legacy removal, payroll locks, retained records and schedule-aware recalculation.

If attendance saving, historical preservation or calculated hours fail verification, stop affected attendance edits and deploy a corrected backend. A frontend rollback can hide the new settings while retaining the schedule-aware backend. Keep schedule versions and attendance snapshots during recovery; reverting to an old calculation backend after new PCS-GBM attendance is saved would apply legacy lunch rules on later edits.
