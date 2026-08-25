from datetime import date
from pathlib import Path

from app.modules.planning.schemas import ActivityMappingIn, ActivityTargetIn

ROOT = Path(__file__).resolve().parents[2]


def test_stage2_target_and_mapping_validation():
    target = ActivityTargetIn(target_quantity=125.5, unit="m")
    mapping = ActivityMappingIn(site_id="site", effective_from=date(2026, 8, 10),
                                effective_to=date(2026, 8, 20))
    assert target.target_quantity == 125.5
    assert mapping.effective_to >= mapping.effective_from


def test_stage2_migration_uses_dpr_as_actual_source_and_recalculates_removed_entries():
    sql = (ROOT / "db/migrations/0010_stage2_dpr_progress.sql").read_text().lower()
    assert "planning_dpr_progress_entries" in sql
    assert "record_planning_dpr_progress" in sql
    assert "daily_report_id" in sql
    assert "left join public.planning_dpr_progress_entries" in sql
    assert "percent_complete=least(100" in sql
    assert "public.my_role(),'') <> 'admin'" in sql


def test_dpr_progress_controls_are_admin_only_in_ui_and_api():
    page = (ROOT / "frontend/dpr.html").read_text()
    main = (ROOT / "backend/app/main.py").read_text()
    assert 'ME.role!=="admin"' in page
    assert "planning_progress:collectPlanningProgress()" in page
    assert 'user["role"] != "admin"' in main
    assert "record_planning_dpr_progress" in main
