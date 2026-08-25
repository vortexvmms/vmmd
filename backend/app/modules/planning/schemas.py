from __future__ import annotations

from datetime import date
from pydantic import BaseModel, Field, model_validator


class SetupIn(BaseModel):
    name: str = "Project Schedule"
    data_date: date


class WbsIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=180)
    parent_id: str | None = None


class ActivityIn(BaseModel):
    wbs_id: str
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=220)
    selected_dates: list[date] = Field(min_length=1, max_length=1000)
    activity_type: str = "task"

    @model_validator(mode="after")
    def valid(self):
        self.selected_dates = sorted(set(self.selected_dates))
        if self.activity_type not in {"task", "milestone"}:
            raise ValueError("Invalid activity type")
        if self.activity_type == "milestone" and len(self.selected_dates) != 1:
            raise ValueError("A milestone must use exactly one date")
        return self


class ActivityPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=220)
    selected_dates: list[date] | None = Field(default=None, min_length=1, max_length=1000)
    status: str | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.selected_dates is not None:
            self.selected_dates = sorted(set(self.selected_dates))
        if self.status is not None and self.status not in {"not_started","in_progress","complete"}:
            raise ValueError("Invalid activity status")
        return self


class ActivityTargetIn(BaseModel):
    target_quantity: float = Field(gt=0, le=1_000_000_000)
    unit: str = Field(min_length=1, max_length=30)


class ActivityMappingIn(BaseModel):
    site_id: str
    item_of_work: str | None = Field(default=None, max_length=220)
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return self
