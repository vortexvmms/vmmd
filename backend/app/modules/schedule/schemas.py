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
