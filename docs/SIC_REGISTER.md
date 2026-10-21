# SIC Register

Three navigation tabs: Dashboard, New Entry and SIC Log. Attach cards remains available from the log and each editable record. Uses the existing VCMS session and worker/site directories, with Supabase REST/RPC and RLS authorization. No backend deployment dependency.

Coordinators (admin, GM, OM, HR, site manager, WSHC lead) manage across sites. WSHC and safety supervisors manage assigned sites. Other site supervisors and logistics supervisors read assigned sites. Payroll and unregistered/inactive accounts have no access.

Validity uses calendar months, clamps to target month end and subtracts one day. Explicit card expiry overrides require a reason. Renewals are atomic, reject stale edits and retain earlier records/cards. Each worker/FIN has one current record per site. FIN can be entered on the SIC record when the worker directory is missing it.

Cards are private PDF/JPEG/PNG files, maximum 20 MB each and ten per upload. The client checks file signatures; Storage enforces MIME and size. Failed attachment uploads can be retried without duplicating the SIC record. Original uploads are immutable through the app; image rotation before upload changes the selected copy. New Entry reads uploaded cards automatically in the browser; PDF text is extracted with PDF.js 4.10.38 and images/scans use Tesseract.js 5.1.1 (English). The pinned libraries and language model are downloaded on demand, so reading requires internet access. Card bytes and extracted text are not sent to an OCR service. Read text stays in the current page; saved fields, card references/issuer in remarks, and original attachments use existing private SIC storage and permissions.

The compact entry uses one worker search selector, a three-column desktop form, and collapsed remarks. Upload & Autofill creates reviewable drafts, matches FIN before exact worker name, and matches sites only when unambiguous. Printed expiry takes priority; absent expiry is calculated using site validity and labelled Calculated. Conflicts and missing values require review. Existing typed values are preserved. A confirmation is required before saving extracted values. Separate worker files become separate drafts; front/back files with one shared identity combine. PDFs containing multiple FINs must be split by worker before saving, to avoid attaching another worker's card. Unknown extra fields remain accessible in the source text and original card.

Reading is sequential and limited to 30 pages per batch, 100,000 characters per page and 6 million rendered pixels per page. Stop reading terminates OCR work; late results cannot change a cancelled/reset entry. Failed reading leaves manual entry available. Original attachment upload, renewal history and failed-file retries retain their existing behavior. No database migration or Edge Function is required.

SIC Log shows Worker/FIN, Designation, Site, SIC Date, Expiry/Status and Actions. View card and Renew are direct actions; Edit, Attach cards and History are under More. Search, Site and Status remain visible; More filters contains designation, card, worker/archive status, dates and sorting. Table headings stay visible inside the scroll area; mobile rows stack with actions visible. Export contains Print, PDF and Excel with an explicit filtered/all-authorised scope. PDF/print/Excel retain eight standard columns, including Designation and validity. Search, site, status, card, worker status and date filters apply to all loaded rows. Export can use filtered results or all current authorised records. PDF uses jsPDF 2.5.1 / AutoTable 3.8.2 and Excel uses ExcelJS 4.4.0, loaded on demand. These require internet access. PDF has repeating headings, unsplit rows and numbered pages. Excel includes real dates, filters, frozen headings and site summary. Browser printing uses the same eight columns; page-counter support depends on browser.

## Verification

- `node --test frontend/tests/sic-domain.test.cjs frontend/tests/sic-card-data.test.cjs`
- `npx playwright test sic-register.spec.js` (desktop Chromium and mobile WebKit; extraction responses are deterministic fixtures)
- `SIC_OCR_SMOKE=1 npx playwright test sic-card-reader.spec.js --workers=1` (actual OCR and PDF dependencies on synthetic cards; requires internet). This does not establish accuracy for every real SIC card format.
- SIC database CI: isolated PostgreSQL foundation, migration, then rollback-only assertions.
- Migration dry-run and eleven database assertions were also executed against the connected project inside a transaction and rolled back before deployment.

## Deploy / rollback

Apply `db/migrations/0023_sic_register.sql` once before publishing the frontend. All schema changes are additive. GitHub Pages publishes after the full Test workflow succeeds on main. Service-worker cache v94 updates navigation/assets.

If the SIC module fails, revert the frontend commit or hide its navigation entry. Retain the SIC tables, private bucket and audit history; never drop populated tables as a routine rollback. The production commit before designation and the streamlined log is aac0ae49de3d793effc71de16c41a93301ff3343. Restore its frontend files to roll back while retaining the additive designation column and compatible save RPC.

The dashboard uses a compact Site / Search / More filters / Clear row. More filters contains worker status, card availability, record archive status and custom expiry ranges. Defaults are active/on-leave workers and current records. Four cards show registered workers (distinct worker IDs), valid records (>30 days), expiring records (today through 30 days), and expired records. Status selections affect the action list without changing the overview counts for the selected filter scope.

One Action required table replaces the separate upcoming, expired and recent lists. It shows at most ten rows, the full matching count, days left/overdue, direct renewal for authorized managers and card viewing. Expired rows appear first, ordered by expiry date. Shortcuts cover action required (overdue plus next 30 days), expired, next 7/30/60 days and all records. Date shortcuts intersect any custom date range. Open in SIC Log preserves the selected scope and shortcut. The site summary omits sites with no matching records, ranks expired and expiring counts first, and links each count to matching log rows. Mobile action rows stack with visible actions; site totals appear under site names while valid/total columns are omitted.

Recent activity is available through Sort by → Recently added / renewed under SIC Log More filters, sorted newest first. Site validity settings remain collapsed at the bottom of the dashboard. Successful refresh reloads SIC data, worker/site directories and assigned-site scope together, then records an Updated time in Asia/Singapore. A failed refresh retains the last complete snapshot and timestamp and displays the failure. No database changes are required. Archived sites remain selectable in SIC (clearly labelled) without changing their master status. Missing-card metrics/options are omitted.

SIC site choices hide an archived duplicate when an active site with the same normalized name exists and the archived site has no SIC history. Independent archived sites such as Advario remain selectable. Historical links and site-master rows are preserved.

Card storage policies qualify `storage.objects.name` to avoid accidentally matching the worker-name column in a correlated subquery. The database suite tests actual object-row insertion, read and SIC attachment linkage.

The main Sites directory supports recoverable removal of archived sites and restoring them as archived. Only management can remove or restore; active sites must be archived first. Removed sites are omitted from ordinary site directories. Attendance/report references and SIC history remain intact.

## Designation snapshots

Apply `supabase/migrations/20261021083812_sic_designation_snapshot.sql` before this frontend. The nullable designation column leaves existing records unknown; no roles are inferred from worker names or blank directory trades. New entries and renewals require one primary designation. Legacy edits may keep an unspecified role. The searchable options are General Worker, Welder, Rigger & Signalman, Lifting Supervisor, Supervisor, CS Supervisor, WAH Supervisor, Safety Supervisor, Driver, Lorry Crane Operator, Traffic Controller & Banksman and Fire Watchman, plus Other — specify (up to 120 characters). CS and WAH are preserved verbatim. A recorded role does not verify competency or certification.

Designation is a per-course/site snapshot, prefilled for renewal and included in history, audit evidence and exports. Explicit Designation, Job Title, Position or Occupation card labels can suggest it; trade/course names alone are not used to infer it. Missing and conflicting values remain for user review. The save RPC preserves an existing designation when older clients omit the JSON key during rollout; new clients send the key and cannot create a blank role or clear a known role. Existing invoker authority, grants, site authorization, stale-edit checks and atomic renewal are retained.

`backend/tests/sic_designation_checks.sql` covers legacy compatibility, typed values, role changes across renewals, audit evidence, rejected clears/oversize values, unregistered users and invoker/grant invariants. Run inside a transaction and roll back. Deployment verification ran these checks against the connected project with rollback, and confirmed the pre-existing record digest and audit count were unchanged.
