from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ProjectStatus = Literal["draft", "active", "on_hold", "completed", "archived"]


class ProjectCreate(BaseModel):
    project_code: str = Field(min_length=1, max_length=40)
    project_name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    client_name: str | None = Field(default=None, max_length=200)
    planned_start_date: date | None = None
    planned_finish_date: date | None = None
    timezone: str = Field(default="Asia/Singapore", min_length=1, max_length=80)
    status: ProjectStatus = "draft"

    @model_validator(mode="after")
    def valid_planned_dates(self):
        if (self.planned_start_date and self.planned_finish_date
                and self.planned_finish_date < self.planned_start_date):
            raise ValueError("planned_finish_date cannot be before planned_start_date")
        return self


class ProjectUpdate(BaseModel):
    project_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    client_name: str | None = Field(default=None, max_length=200)
    planned_start_date: date | None = None
    planned_finish_date: date | None = None
    actual_start_date: date | None = None
    actual_finish_date: date | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    status: ProjectStatus | None = None

    @model_validator(mode="after")
    def valid_dates(self):
        if (self.planned_start_date and self.planned_finish_date
                and self.planned_finish_date < self.planned_start_date):
            raise ValueError("planned_finish_date cannot be before planned_start_date")
        if (self.actual_start_date and self.actual_finish_date
                and self.actual_finish_date < self.actual_start_date):
            raise ValueError("actual_finish_date cannot be before actual_start_date")
        return self
