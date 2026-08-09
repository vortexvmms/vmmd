from pathlib import Path

from app.core.roles import ALL_ROLES

ROOT = Path(__file__).resolve().parents[2]


def test_phase0_migration_contains_every_backend_role():
    sql = (ROOT / "db" / "migrations" / "0001_phase0_foundation.sql").read_text()
    for role in ALL_ROLES:
        assert f"'{role}'" in sql


def test_phase0_migration_has_project_isolation_objects():
    sql = (ROOT / "db" / "migrations" / "0001_phase0_foundation.sql").read_text()
    for required in ("public.projects", "public.project_members", "public.my_project_ids()"):
        assert required in sql
    assert "alter table public.schema_migrations enable row level security" in sql


def test_frontend_catalogue_contains_every_backend_role():
    frontend = (ROOT / "frontend" / "js" / "config.js").read_text()
    for role in ALL_ROLES:
        assert f'"{role}"' in frontend


def test_live_migration_preserves_existing_rls_policies():
    sql = (ROOT / "db" / "migrations" / "0001_phase0_foundation.sql").read_text()
    assert "leaves those policies untouched" in sql
    assert "drop policy if exists att_admin_all" not in sql


def test_phase1_wbs_migration_contract():
    sql = (ROOT / "db" / "migrations" / "0002_phase1_wbs_foundation.sql").read_text()
    for required in ("public.schedules", "public.wbs_nodes", "project_id", "schedule_id", "parent_id"):
        assert required in sql
    assert "depth between 1 and 6" in sql
    assert "WBS hierarchy cannot contain a cycle" in sql
    assert "public.reorder_wbs_nodes" in sql
    assert "alter table public.wbs_nodes enable row level security" in sql
    assert "values ('0002'" in sql
