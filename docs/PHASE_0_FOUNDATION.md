# VCMS Phase 0 foundation

## Decision

The canonical hierarchy is `Project -> Site -> operational records`. A Project
may contain multiple Sites. Schedule records will always carry the canonical
`project_id`. The legacy `dpr_projects` directory is retained temporarily but
linked to `projects`; it is not a second project master.

## Permission matrix

| Tier | Roles | Project access | Project administration |
|---|---|---|---|
| Full | admin, general_manager, operation_manager, hr_assistant | All | Create and edit |
| Manager | main_sup, wshc_lead | All | Create and edit |
| Supervisor | site_sup, safety_sup, wshc, logistics_sup | Assigned membership or assigned Site | No |
| Payroll | payroll | All, read only | No |

The API uses the user's bearer token. Supabase RLS is the authoritative row
filter, while the API independently checks management-only mutations. The
service-role key remains server-side and is not used by the Projects API.

## Migration sequence

1. Run `scripts/reconcile_schema.py` against a read-only/non-production-capable
   database connection and review the generated inventory.
2. Back up production and verify a restore in a non-production database.
3. Apply `db/migrations/0001_phase0_foundation.sql` in non-production.
4. Review automatically created `DPR-*` and `SITE-*` Project mappings. Legacy
   DPR rows with the same normalized title map to one canonical Project. Merge
   or rename any remaining records only through a separately reviewed data
   migration.
5. Test every role with real Supabase user JWTs.
6. Deploy backend and frontend only after migration and authorization tests pass.

## Rollback rule

The migration is additive except for replacing the old users role constraint.
Do not drop canonical columns to roll back an application release. Restore the
previous constraint only if all live role values are compatible, roll back the
application, and retain Project data until a separately approved cleanup.

## Active Project contract

`frontend/js/project-context.js` fetches only Projects the signed-in user may
access. A stored Project ID is a UI preference, never authorization evidence.
If the saved ID is no longer returned by the API, it is discarded and replaced
with the first authorized active Project. Project-bound modules must call
`vcmsProjectContext.requireActiveId()` and send that ID to APIs, which must
validate it again through RLS.

## Phase 0 completion gates

- The live schema inventory has no unexplained backend table dependencies.
- The migration succeeds on a restored non-production copy.
- Role/RLS tests pass with authenticated JWT claims in the isolated rehearsal database.
- Legacy Sites and DPR records have approved Project mappings.
- `/api/v1/projects` returns only authorized records.
- The shared shell selector changes Project context without granting access.
- Backend unit tests and frontend smoke checks pass.
