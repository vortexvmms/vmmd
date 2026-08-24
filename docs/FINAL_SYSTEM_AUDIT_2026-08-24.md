# VCMS Final System Audit — 24/08/2026

## Executive result

**Operational modules: PASS with one intentionally deferred Scheduling contract.**

- 70 applicable automated tests passed.
- 5 new critical operational audit tests passed.
- One existing Scheduling/Progress test remains deferred because the Scheduling module has not been released by management.
- No service-role key or password was found in frontend source.
- Mobile end-time changes are stored on the phone, retried after connection restoration and reconciled against server data before final submission.

## 1. Calculations and reports

### Result: PASS

Verified company hour rules:

| Scenario | Expected |
|---|---:|
| Weekday 08:00–17:00 | 8 normal, 0 OT |
| Weekday 08:00–19:00 | 8 normal, 2 OT |
| Saturday 08:00–12:00 | 4 normal, 0 OT |
| Saturday 08:00–17:00 | 4 normal, 4 OT |
| Sunday/PH 08:00–17:00 | 0 normal, 8 OT |
| Night shift 20:00–06:00 next day | 8 normal, 2 OT |

Home, Dashboard, Attendance Report and Man-hours Report consume the stored backend `normal_hours` and `ot_hours` values. Monthly queries page through more than 1,000 Supabase rows, preventing silent truncation. Historical/inactive sites with hours are included in Site Operations totals.

Resource Summary is intentionally DPR/site-resource based, while Home/Timesheet/Man-hours are attendance based. They must agree for manpower hours when DPR data is complete, but materials and plant remain DPR-only.

## 2. Weak mobile connectivity and end-time submission

### Result: PASS at code/regression level; field acceptance required

Verified:

- Every individual change enters a durable local queue before network submission.
- Pending changes survive refresh through local storage.
- Offline events retain the queue.
- Online events trigger automatic retry.
- Batch API returns per-worker outcomes.
- Failed items remain queued instead of being discarded.
- Bulk end time verifies the server result and queues only missing workers.
- Final submission blocks while unconfirmed changes remain.
- The interface says “saved on phone” rather than incorrectly claiming the server saved it.

Required field acceptance: Rajesh and Prakash should complete one normal evening submission each on their usual 4G connections. This is the only reliable way to validate actual carrier coverage, device power-saving and browser suspension behaviour.

## 3. Obsolete code cleanup

### Result: PASS

Removed:

- Retired global notification bell code
- Retired unread-count polling
- Retired frontend Web Push subscription helpers
- Retired Settings notification/broadcast functions

Preserved intentionally:

- Backend notification code behind the disabled feature flag, allowing controlled restoration without database changes
- Historical migrations and correction scripts, which form part of the audit trail
- Unlinked legacy worker-card files; they are not exposed in navigation and do not affect page speed

## 4. Mobile and desktop regression

### Result: PASS at automated contract level

- All frontend HTML pages contain a mobile viewport declaration.
- Home contains separate mobile and desktop breakpoints.
- Supervisor navigation remains limited to daily operational tools.
- Admin mobile navigation includes Request Manpower.
- Shared shell remains desktop-only below the mobile breakpoint.
- Allocation Admin copy controls use equal heights and stack without overlap on narrow phones.
- Service-worker cache version was advanced to force clients onto audited files.

Recommended physical screens for final acceptance: iPhone, Android phone, 13-inch laptop and 1920×1080 monitor.

## 5. Security audit

### Passed

- API CORS origins are restricted to VCMS and local development.
- API responses include no-sniff, frame-deny, referrer and permissions-policy headers.
- Service-role and R2 secrets are server environment variables only.
- Protected routes require a logged-in user; health/root are intentionally public.
- Cron reminder routes require `REMINDER_TOKEN`.
- Audit log is insert-only for normal users and readable by management roles according to RLS.
- RLS enablement is evidenced for operational tables.
- Admin correction ledger remediation was added.

### Required one-time action

Run `db/migrate_security_audit_20260824.sql` in Supabase SQL Editor. It enables RLS on the historical `admin_data_corrections` ledger and permits read access only to Admin.

### Operational checks

- Review active users monthly and deactivate leavers immediately.
- Review Render/Supabase/R2 secret access quarterly.
- Never store secrets in GitHub or screenshots.
- Treat FIN, attendance, leave and worker information as confidential personal data.

## 6. Backup and recovery

### Result: procedure completed; first backup evidence pending

The approved procedure is documented in `docs/BACKUP_RECOVERY_RUNBOOK.md`.

Minimum operation:

- Weekly database export
- Month-end labelled export
- Monthly R2 inventory/count check
- Quarterly test restoration
- Separate protected storage, never the public repository

The audit cannot claim a backup exists until an export has been created and its restore tested.

## Release decision

**Approved for continued internal operational use**, subject to:

1. Running the one-time security migration.
2. Completing two supervisor 4G field submissions.
3. Performing and recording the first database backup.
4. Keeping Scheduling hidden until its remaining contract is completed and tested.
