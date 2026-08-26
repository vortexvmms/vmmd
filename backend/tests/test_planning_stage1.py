from datetime import date
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.modules.planning.schemas import ActivityIn, ProgrammeImportIn

ROOT = Path(__file__).resolve().parents[2]


def test_activity_dates_are_deduplicated_sorted_and_discontinuous():
    body = ActivityIn(wbs_id="w", code="A1", name="Work", selected_dates=[
        date(2026, 8, 12), date(2026, 8, 10), date(2026, 8, 12)
    ])
    assert body.selected_dates == [date(2026, 8, 10), date(2026, 8, 12)]


def test_milestone_has_exactly_one_selected_date():
    with pytest.raises(ValidationError):
        ActivityIn(wbs_id="w", code="M1", name="Milestone", activity_type="milestone",
                   selected_dates=[date(2026, 8, 10), date(2026, 8, 11)])


def test_stage1_migration_is_admin_only_and_authoritative():
    sql = (ROOT / "db/migrations/0009_stage1_selected_dates.sql").read_text().lower()
    assert "planning_activity_dates" in sql
    assert "replace_activity_dates" in sql
    assert "public.my_role()='admin'" in sql.replace(" ", "")
    assert "planned_start=(select min(work_date)" in sql
    assert "planned_finish=(select max(work_date)" in sql


def test_planning_page_keeps_grid_selection_and_excludes_stage4_pnl():
    page = (ROOT / "frontend/planning.html").read_text()
    assert "data-activity" in page and "selected_dates" in page
    assert "pointerdown" in page and "pointerover" in page
    assert "forecast_pnl" not in page


def test_programme_import_validates_hierarchy_and_discontinuous_dates():
    body = ProgrammeImportIn(wbs=[
        {"code": "1", "name": "Main"},
        {"code": "1.1", "name": "Survey", "parent_code": "1"},
    ], activities=[{
        "wbs_code": "1.1", "code": "A100", "name": "Survey work",
        "selected_dates": ["2026-08-24", "2026-08-26", "2026-08-24"]
    }])
    assert [str(x) for x in body.activities[0].selected_dates] == ["2026-08-24", "2026-08-26"]


def test_programme_import_ui_and_atomic_rpc_are_present():
    page = (ROOT / "frontend/planning.html").read_text()
    sql = (ROOT / "db/migrations/0013_planning_programme_import.sql").read_text().lower()
    router = (ROOT / "backend/app/modules/planning/router.py").read_text()
    assert 'id="importWbs"' in page
    assert "Download template" in page and "Confirm import" in page
    assert "parseImportRows" in page and "Exclude Dates" in page
    assert "import_planning_programme" in sql and "security definer" in sql
    assert '"/projects/{project_id}/import"' in router
