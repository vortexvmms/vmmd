from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.schedule.schemas import ActivityCreate


def activity(**overrides):
    values = dict(project_id=uuid4(), wbs_id=uuid4(), code="A100", name="Mobilisation", activity_type="task", duration_days=5, planned_start=date(2026, 8, 10), planned_finish=date(2026, 8, 14))
    values.update(overrides)
    return values


def test_accepts_task_and_zero_duration_milestone():
    assert ActivityCreate(**activity()).duration_days == 5
    milestone = ActivityCreate(**activity(activity_type="milestone", duration_days=0, planned_finish=date(2026, 8, 10)))
    assert milestone.activity_type == "milestone"


@pytest.mark.parametrize("overrides", [
    {"activity_type": "task", "duration_days": 0},
    {"activity_type": "milestone", "duration_days": 1, "planned_finish": date(2026, 8, 10)},
    {"activity_type": "milestone", "duration_days": 0},
    {"planned_finish": date(2026, 8, 9)},
])
def test_rejects_invalid_planning_dates_and_durations(overrides):
    with pytest.raises(ValidationError):
        ActivityCreate(**activity(**overrides))
