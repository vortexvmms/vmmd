from datetime import date
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.modules.planning.schemas import ActivityIn

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
