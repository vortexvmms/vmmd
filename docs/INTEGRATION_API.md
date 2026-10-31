# Restricted attendance API v1

Initial release: GET `/api/integration/v1/attendance?from=YYYY-MM-DD&to=YYYY-MM-DD`
and GET `/api/integration/v1/worker-day?worker_code=CODE&date=YYYY-MM-DD`.
Both require `Authorization: Bearer <integration-key>`. No writes, directory,
change feed, edit history, or MCP server are provided in this release.

Configure server-only environment variables:
- `VCMS_INTEGRATION_KEY_HASHES`: one or two comma-separated lowercase SHA-256 hashes.
- `VCMS_INTEGRATION_EXPIRES_AT`: timezone-aware ISO timestamp. Required.

Missing/invalid configuration or expired access denies all reads (503). Invalid
credentials return 401. Rotation: add the new hash,
redeploy, switch caller, remove the old hash and redeploy. Environment changes
require a restart. Never commit raw keys. Both configured hashes share all-site attendance access
and expiry; use only for rotation of the same client.

Attendance supports optional `site_code` for report filtering; omission returns all
current and future sites. No site allowlist configuration is needed. Any legacy
`VCMS_INTEGRATION_SITE_CODES` setting is ignored and can be removed. Site codes
remain in every attendance record. Existing pre-change cursors must be discarded
and the date-range retrieval restarted.
Dates are inclusive Singapore work dates, maximum 62 days. `limit` defaults to 200,
valid 1–500 (outside bounds returns 422). Invalid typed parameters return 422;
malformed cursors/ranges return 400. Follow `next_cursor` without changing filters.
Pagination orders by work date and allocation UUID; each record is one allocation.
Live edits during pagination may change results: periodically re-fetch the entire
comparison period, replacing that period's local snapshot only after every page
succeeds. This also reconciles hard deletions. No incremental-delivery guarantee.
Do not infer absence from null times or missing scans. `end_next_day` preserves
night-shift semantics. Names/codes are source values, not inferred identities.

Responses contain records, next_cursor, has_more, server_time; timestamps use ISO
8601 offsets. Fields are explicitly restricted; no FIN, photos, documents or notes.
Read logs contain endpoint, date range, row count and duration, never credentials
or full records. Configure durable retention externally if required; this initial
release does not promise database audit rows or reliable edit history.

Rate limiting is 60 requests/minute/key/process and resets on restart; it is not a
distributed quota. Database calls time out after 15 seconds. Database failures
return generic 503. Responses use Cache-Control: no-store.

Deployment: apply the integration SQL migration, deploy backend, then configure
hashes and expiry. Verify missing/wrong keys, optional site filtering and allowed
reads. Rollback: remove integration environment variables (denies reads), roll back
backend commit, then drop only the integration function if desired. Existing
attendance tables, policies and user endpoints are unchanged.
