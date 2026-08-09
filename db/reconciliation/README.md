# Live schema reconciliation

Run `python scripts/reconcile_schema.py` with `SUPABASE_DB_URL` provided in the
process environment. The tool exports schema only and creates a local inventory.
Generated live-schema artifacts are ignored by Git because they are environment
evidence, not hand-maintained migrations.
