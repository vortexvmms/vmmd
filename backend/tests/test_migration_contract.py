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


def test_phase1_activity_migration_contract():
    sql = (ROOT / "db" / "migrations" / "0003_phase1_activities_milestones.sql").read_text()
    for required in ("public.schedule_activities", "project_id", "schedule_id", "wbs_id", "activity_type", "duration_days"):
        assert required in sql
    assert "planned_finish >= planned_start" in sql
    assert "activity_type = 'milestone' and duration_days = 0" in sql
    assert "public.validate_activity_scope" in sql
    assert "alter table public.schedule_activities enable row level security" in sql
    assert "values ('0003'" in sql


def test_phase1_activity_logic_migration_contract():
    sql = (ROOT / "db" / "migrations" / "0004_phase1_activity_logic.sql").read_text()
    for required in ("public.activity_relationships", "predecessor_id", "successor_id", "relationship_type", "lag_days"):
        assert required in sql
    assert "('FS','SS','FF','SF')" in sql
    assert "Activity logic cannot contain a cycle" in sql
    assert "uq_active_relationship_pair" in sql
    assert "public.validate_activity_relationship" in sql
    assert "alter table public.activity_relationships enable row level security" in sql
    assert "values ('0004'" in sql


def test_phase1_project_calendar_migration_contract():
    sql = (ROOT / "db" / "migrations" / "0005_phase1_project_calendars.sql").read_text()
    for required in ("public.schedule_calendars", "public.calendar_workweek", "public.calendar_exceptions", "day_of_week", "work_hours"):
        assert required in sql
    assert "uq_project_default_calendar" in sql
    assert "pg_trigger_depth()>1" in sql
    assert "public.set_calendar_workweek" in sql
    assert "public.validate_activity_calendar_scope" in sql
    assert "alter table public.schedule_calendars enable row level security" in sql
    assert "values('0005'" in sql


def test_phase1_resource_migration_contract():
    sql=(ROOT/"db"/"migrations"/"0006_phase1_resources.sql").read_text()
    for required in ("public.resource_master_library","public.project_resources","public.activity_resource_assignments","budgeted_cost","project_resource_id"):
        assert required in sql
    assert "public.validate_resource_assignment_scope" in sql
    assert "uq_active_activity_resource" in sql
    assert "alter table public.resource_master_library enable row level security" in sql
    assert "values('0006'" in sql


def test_phase1_gantt_baseline_migration_contract():
    sql=(ROOT/"db"/"migrations"/"0007_phase1_gantt_baselines.sql").read_text()
    for required in ("early_start","late_finish","total_float","public.schedule_baselines","public.baseline_activity_snapshots","budgeted_cost"):
        assert required in sql
    assert "public.create_schedule_baseline" in sql
    assert "alter table public.schedule_baselines enable row level security" in sql
    assert "values('0007'" in sql


def test_phase1_progress_dpr_migration_contract():
    sql=(ROOT/"db"/"migrations"/"0008_phase1_progress_dpr.sql").read_text()
    for required in ("public.activity_progress_updates","actual_start","actual_finish","percent_complete","dpr_report_id","public.record_activity_progress"):
        assert required in sql
    assert "public.refresh_activity_progress" in sql
    assert "min(actual_start)" in sql
    assert "alter table public.activity_progress_updates enable row level security" in sql
    assert "values('0008'" in sql
