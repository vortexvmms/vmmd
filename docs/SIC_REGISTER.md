# SIC Register

Four tabs: Dashboard, New Entry, Upload SIC Cards and SIC Log. Uses the existing VCMS session and worker/site directories, with Supabase REST/RPC and RLS authorization. No backend deployment dependency.

Coordinators (admin, GM, OM, HR, site manager, WSHC lead) manage across sites. WSHC and safety supervisors manage assigned sites. Other site supervisors and logistics supervisors read assigned sites. Payroll and unregistered/inactive accounts have no access.

Validity uses calendar months, clamps to target month end and subtracts one day. Explicit card expiry overrides require a reason. Renewals are atomic, reject stale edits and retain earlier records/cards. Each worker/FIN has one current record per site. FIN can be entered on the SIC record when the worker directory is missing it.

Cards are private PDF/JPEG/PNG files, maximum 20 MB each and ten per upload. The client checks file signatures; Storage enforces MIME and size. Failed attachment uploads can be retried without duplicating the SIC record. Original uploads are immutable through the app; image rotation before upload changes the selected copy. OCR is not included in this release.

The log has seven standard columns, with screen-only status/card/actions. Search, site, status, card, worker status and date filters apply to all loaded rows. Export can use filtered results or all current authorised records. PDF uses jsPDF 2.5.1 / AutoTable 3.8.2 and Excel uses ExcelJS 4.4.0, loaded on demand. These require internet access. PDF has repeating headings, unsplit rows and numbered pages. Excel includes real dates, filters, frozen headings and site summary. Browser printing uses the same seven columns; page-counter support depends on browser.

## Verification

- `node --test frontend/tests/sic-domain.test.cjs`
- `npx playwright test sic-register.spec.js`
- SIC database CI: isolated PostgreSQL foundation, migration, then rollback-only assertions.
- Migration dry-run and eleven database assertions were also executed against the connected project inside a transaction and rolled back before deployment.

## Deploy / rollback

Apply `db/migrations/0023_sic_register.sql` once before publishing the frontend. All schema changes are additive. GitHub Pages publishes after the full Test workflow succeeds on main. Service-worker cache v84 updates navigation/assets.

If the SIC module fails, revert the frontend commit or hide its navigation entry. Retain the SIC tables, private bucket and audit history; never drop populated tables as a routine rollback. The previous production commit is d7d1801edd94645fabaac71047fcf8cfb2926183.

Dashboard filters support site, SIC status, worker status, card availability, record archive status, search and expiry ranges. KPI tiles and the filtered-log action carry the selected scope into the log. Archived sites remain selectable in SIC (clearly labelled) without changing their master status. Missing-card metrics/options are omitted.

SIC site choices hide an archived duplicate when an active site with the same normalized name exists and the archived site has no SIC history. Independent archived sites such as Advario remain selectable. Historical links and site-master rows are preserved.
