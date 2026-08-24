# VCMS Backup and Recovery Runbook

## Scope

Back up these separately because one does not contain the other:

1. Supabase database (workers, sites, allocations, attendance, DPR, PR and audit data)
2. Cloudflare R2 objects (camera and uploaded photos)
3. GitHub repository (frontend, backend, migrations and documentation)
4. Render and Supabase environment-variable inventory (names only; never place secret values in Git)

## Schedule

- Every Friday: export the Supabase database and verify that the file is non-empty.
- Month end: create an additional labelled export after payroll/man-hours are checked.
- Monthly: export/list the R2 object inventory and compare object counts.
- After every migration: retain the pre-migration export until the next successful monthly check.

## Supabase database procedure

1. Sign in to Supabase directly.
2. Use the project backup/export facility or an approved `pg_dump` connection.
3. Save the encrypted export outside the public GitHub repository.
4. Name it `VCMS_DB_YYYY-MM-DD_HHMM_SGT`.
5. Record file size, export time and the person who performed it.
6. Never paste the database password or service-role key into VCMS source files.

## R2 procedure

1. Open the VCMS R2 bucket in Cloudflare.
2. Record the object count and total stored size.
3. Export/copy objects to a separate protected location when required by company retention policy.
4. Keep worker/site photos access-controlled; do not use a publicly listable bucket.

## Recovery drill (quarterly)

1. Restore the latest database export into a separate test project—not production.
2. Confirm counts for users, workers, sites, allocations, attendance, DPRs, PRs and audit records.
3. Open one DPR with photos and one PR attachment.
4. Confirm normal-hours and OT totals for one completed month.
5. Record the test result and any missing objects.

## Recovery order

1. Freeze data entry and record the incident time.
2. Preserve the damaged/current database before restoring anything.
3. Restore the database to a test environment and validate totals.
4. Restore production only after management approval.
5. Reconnect R2 URLs and verify sample images.
6. Rotate credentials if compromise is suspected.
7. Document the incident in the audit/incident record.

## Retention recommendation

- Keep at least four weekly exports and twelve month-end exports.
- Retain payroll, attendance and safety-related records according to Vortex's approved Singapore legal/contractual retention policy.
- Treat this runbook as an operational draft for management review.
