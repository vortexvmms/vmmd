from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.schedule.schemas import CalendarWorkweekUpdate, WeekdayRule


def standard_week():
    return [{"day_of_week": day, "is_working": day in range(1, 6), "work_hours": 8 if day in range(1, 6) else 0} for day in range(7)]


def test_accepts_complete_standard_workweek():
    week = CalendarWorkweekUpdate(rules=standard_week())
    assert len(week.rules) == 7
    assert sum(rule.is_working for rule in week.rules) == 5


def test_rejects_duplicate_or_missing_weekday():
    rules = standard_week()
    rules[-1]["day_of_week"] = 5
    with pytest.raises(ValidationError):
        CalendarWorkweekUpdate(rules=rules)


@pytest.mark.parametrize("rule", [
    {"day_of_week": 1, "is_working": True, "work_hours": 0},
    {"day_of_week": 0, "is_working": False, "work_hours": 8},
])
def test_rejects_inconsistent_working_hours(rule):
    with pytest.raises(ValidationError):
        WeekdayRule(**rule)
