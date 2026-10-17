# VCMS — Vortex Construction Management System

VCMS is a construction operations web application covering site manpower, attendance, progress reporting, procurement, planning, equipment and safety-document records.

The project began as **VMMS — Vortex Manpower Management System**. The repository name and some code identifiers retain VMMS for compatibility. This overview replaces the original project-setup-only description.

## Module areas

| Area | Modules |
| --- | --- |
| Daily work | Home and personal To do |
| Manpower | Workers, Sites, Manpower Request and Allocation |
| Attendance and reports | Attendance, End-Time Verification, Monthly Timesheet, Man-Hours and attendance reports |
| Progress | Project directory, Camera, Daily Progress Reports, report history and Resource Summary |
| Planning | Programme, multi-location planning/reporting and operational cost forecasting |
| Procurement | Purchase Requisitions, PR directory, historical PDF import and PR Board |
| Equipment | Tipper Truck Supply, driver submissions and Lifting |
| Safety records | SIC Register and supporting card records |
| Administration | Users, Settings, Audit Log and Help |

Feature availability depends on the current implementation and authorized user access. This overview does not certify completion of every historical roadmap item.

## Technology overview

| Component | Technology or provider |
| --- | --- |
| Website | HTML, CSS and JavaScript; GitHub Pages |
| Application service | Python FastAPI and Uvicorn; Render |
| Database and login | Supabase / PostgreSQL |
| Files | Cloudflare R2 and Supabase Storage |
| Development automation | GitHub Actions |

## Repository structure

| Path | Purpose |
| --- | --- |
| `frontend/` | Website pages, shared scripts/styles, assets and browser tests |
| `backend/` | Application service and backend tests |
| `db/` | Database scripts and numbered migrations |
| `supabase/migrations/` | Additional timestamped database migrations |
| `scripts/` | Build and maintenance utilities |
| `reports/` | Report automation code |
| `.github/workflows/` | Test, publishing and automation definitions |
| `docs/` | Module guides and project documentation |

## Documentation and development

See the [documentation guide](docs/README.md) for existing module references. Earlier VMMS setup and phase notes are historical documents rather than the current module inventory.

Use `backend/requirements*.txt`, `package.json`, `playwright.config.js` and the checked-in workflows as the development/test references. Use separate test data and configuration for development. Keep credentials, live personnel/transaction exports and private document originals outside the repository.

Detailed business and technical handover materials should be exchanged through an approved company access-controlled location.

Documentation overview updated: **17 October 2026**.
