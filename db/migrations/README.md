# VCMS database migrations

These files are the ordered, immutable database change history. Apply each
file once, in numeric order, through a controlled Supabase migration process.
Never edit a migration after it has been applied; add a new migration instead.

Before applying a migration:

1. Back up the live database.
2. Run `python scripts/reconcile_schema.py` with `SUPABASE_DB_URL` configured.
3. Test the migration against a non-production database.
4. Run backend and RLS authorization tests.
5. Record the deployment and rollback decision.

`0001_phase0_foundation.sql` is intentionally backward-compatible with the
legacy `sites` and optional `dpr_projects` structures. It creates the
canonical Project identity and retains legacy records during migration.
