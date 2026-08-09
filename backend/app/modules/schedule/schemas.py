from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class WbsCreate(BaseModel):
    project_id: UUID
    parent_id: UUID | None = None
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=240)
    description: str | None = None
    sort_order: int = Field(default=1000, ge=0)


class WbsUpdate(BaseModel):
    parent_id: UUID | None = None
    code: str | None = Field(default=None, min_length=1, max_length=60)
    name: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class WbsOrderItem(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    sort_order: int = Field(ge=0)


class WbsReorder(BaseModel):
    project_id: UUID
    items: list[WbsOrderItem] = Field(min_length=1, max_length=1000)


class ActivityCreate(BaseModel):
    project_id: UUID
    wbs_id: UUID
    calendar_id: UUID | None = None
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=240)
    description: str | None = None
    activity_type: Literal["task", "milestone"] = "task"
    duration_days: int = Field(default=1, ge=0, le=10000)
    planned_start: date
    planned_finish: date
    sort_order: int = Field(default=1000, ge=0)

    @model_validator(mode="after")
    def validate_planning_fields(self):
        if self.planned_finish < self.planned_start:
            raise ValueError("Planned finish cannot be before planned start")
        if self.activity_type == "milestone":
            if self.duration_days != 0 or self.planned_finish != self.planned_start:
                raise ValueError("A milestone must have zero duration and one planned date")
        elif self.duration_days < 1:
            raise ValueError("A task must have a duration of at least one day")
        return self


class ActivityUpdate(BaseModel):
    wbs_id: UUID | None = None
    calendar_id: UUID | None = None
    code: str | None = Field(default=None, min_length=1, max_length=60)
    name: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    activity_type: Literal["task", "milestone"] | None = None
    duration_days: int | None = Field(default=None, ge=0, le=10000)
    planned_start: date | None = None
    planned_finish: date | None = None
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class RelationshipCreate(BaseModel):
    project_id: UUID
    predecessor_id: UUID
    successor_id: UUID
    relationship_type: Literal["FS", "SS", "FF", "SF"] = "FS"
    lag_days: int = Field(default=0, ge=-3650, le=3650)

    @model_validator(mode="after")
    def prevent_self_link(self):
        if self.predecessor_id == self.successor_id:
            raise ValueError("An activity cannot depend on itself")
        return self


class RelationshipUpdate(BaseModel):
    relationship_type: Literal["FS", "SS", "FF", "SF"] | None = None
    lag_days: int | None = Field(default=None, ge=-3650, le=3650)
    is_active: bool | None = None


class CalendarCreate(BaseModel):
    project_id: UUID
    name: str = Field(min_length=1, max_length=120)
    hours_per_day: float = Field(default=8, gt=0, le=24)
    is_default: bool = False


class CalendarUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    is_default: bool | None = None
    is_active: bool | None = None


class WeekdayRule(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    is_working: bool
    work_hours: float = Field(ge=0, le=24)

    @model_validator(mode="after")
    def validate_hours(self):
        if self.is_working and self.work_hours <= 0:
            raise ValueError("A working day must have positive work hours")
        if not self.is_working and self.work_hours != 0:
            raise ValueError("A non-working day must have zero work hours")
        return self


class CalendarWorkweekUpdate(BaseModel):
    rules: list[WeekdayRule] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def require_all_weekdays(self):
        if {rule.day_of_week for rule in self.rules} != set(range(7)):
            raise ValueError("Workweek must contain each weekday exactly once")
        return self


class CalendarExceptionCreate(BaseModel):
    exception_date: date
    name: str = Field(min_length=1, max_length=160)
    is_working: bool = False
    work_hours: float = Field(default=0, ge=0, le=24)

    @model_validator(mode="after")
    def validate_hours(self):
        if self.is_working and self.work_hours <= 0:
            raise ValueError("A working exception must have positive work hours")
        if not self.is_working and self.work_hours != 0:
            raise ValueError("A non-working exception must have zero work hours")
        return self
