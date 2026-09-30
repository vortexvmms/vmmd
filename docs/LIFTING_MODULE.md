# VCMS Lifting

Lifting is one Equipment & Machineries navigation item. `frontend/lifting.html`
contains Directory (machine landing list and document history), LM Log, LG Log,
and Client Document Pack. Desktop uses tabs; phones use a section selector and
record cards. Existing navigation items and attendance controls are retained.

## Implementation

- `frontend/js/lifting.js`, `frontend/css/lifting.css`: review, registers,
  current-holder movements, version display, pack selection/order, CSV and PDF.
- `backend/app/modules/lifting/{router,domain,pdf}.py`: authenticated API,
  conservative extraction/date calculations, landscape logs and merged originals.
- `db/migrations/0020_lifting_directory.sql`: six additive tables, private
  `lifting-documents` bucket, active-profile permissions and atomic RPCs.
- `frontend/js/shell.js`, `frontend/home.html`: one Lifting navigation item.
- `frontend/sw.js`: refreshed application cache and lifting shell files.
- `.github/workflows/test.yml`: backend, browser and isolated PostgreSQL checks.

## Records and review

PDF/JPG/PNG originals are limited to 20 MB / 150 pages, private and immutable.
PDF text extraction and scanned-page OCR run in the browser using the same
PDF.js/Tesseract approach as the existing PR importer. Extraction can fail;
manual entry and original-document review remain available. No extracted value
becomes verified without explicit user confirmation. Machine ID is manual.
Confirm the quantity and actual physical markings for every gear piece. For
bundles containing several distinct certificates, upload each certificate as a
separate file to maintain a clear record-to-original relationship.

A renewed LM matches its registration number and cross-checks Machine ID,
vehicle and serial number. It updates one machine and retains older documents.
LG renewal preserves the separately tracked physical pieces and their holders.
Six/twelve-month dates use calendar-month addition minus one day. LG next renewal
is capped by printed expiry. Dates and daily alerts use Singapore time.
Certificate maximum SWL is not treated as capacity at every working radius.

Active coordinator roles and Logistics Supervisor can manage lifting records.
Site Supervisor, Safety Supervisor and WSHC have view access. Payroll has no
lifting access. RLS enforces this independently of the interface. Direct writes
and deletion of register/history tables are revoked; reviewed records, transfers
and snapshots use narrowly scoped RPCs. Transfers lock the physical item and
check its expected holder, so simultaneous moves cannot assign it twice.

Pack snapshots freeze machine/gear data, original document IDs/checksums,
selected physical pieces, order, preparer and date in one transaction. Renewals
or movements cannot change older snapshots. A fresh pack selects current
versions and gears currently with the chosen machine. Missing, expired,
unverified or excluded required documents require acknowledgement. Failed PDF
assembly leaves the snapshot available for retry. Downloads rebuild from its
immutable originals, never from the current register.

Logs are A4 landscape with a local Vortex logo, signed-in preparer, generation
date, repeating column headers and bottom-left page numbers. Original PDF page
orientation is preserved. Image originals are converted to PDF pages.

## Deployment and rollback

Follow `db/migrations/README.md`: successful current-project backup, live schema
reconciliation, isolated migration/RLS tests, then the production migration.
Do not enable the navigation in production before the tables and bucket exist.
Merge only after the Test workflow passes; the existing Pages and Render
workflows publish the UI and API. Verify signed-in reads, upload/review,
renewal, issue/borrow/return, pack downloads and phone/desktop layout live.

Rollback the application commit if core workflows or lifting permissions fail.
Keep the additive tables, private originals and frozen packs intact; do not
remove data as a rollback operation.

## Backup setup

The existing `VCMS DB Backup` workflow now encrypts database and schema artifacts
with AES-256. It requires `SUPABASE_DB_URL` and `VCMS_BACKUP_KEY` in Actions
secrets. Retain the separately saved local encryption key for recovery. Do not
commit the key, plaintext dumps, credentials or actual certificate fixtures.
The connection must be for the current vcms-sg project; use its Session pooler
URI on port 5432 for IPv4 runners and percent-encode password characters.

No lifting-plan analysis, automatic approval of a lifting operation, location
tracking, scheduled renewal messaging or example machine seeding is included.
