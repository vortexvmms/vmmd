from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.projects.schemas import ProjectCreate, ProjectUpdate


def test_project_create_accepts_valid_dates():
    project = ProjectCreate(
        project_code="VC-001",
        project_name="Example",
        planned_start_date=date(2026, 1, 1),
        planned_finish_date=date(2026, 2, 1),
    )
    assert project.status == "draft"
    assert project.timezone == "Asia/Singapore"


def test_project_create_rejects_reversed_planned_dates():
    with pytest.raises(ValidationError):
        ProjectCreate(
            project_code="VC-001",
            project_name="Example",
            planned_start_date=date(2026, 2, 1),
            planned_finish_date=date(2026, 1, 1),
        )


def test_project_update_rejects_reversed_actual_dates():
    with pytest.raises(ValidationError):
        ProjectUpdate(
            actual_start_date=date(2026, 2, 1),
            actual_finish_date=date(2026, 1, 1),
        )
