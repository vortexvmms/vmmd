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


class ManpowerRateIn(BaseModel):
    worker_id: str | None = None
    trade: str | None = Field(default=None, max_length=100)
    normal_rate: float = Field(ge=0, le=1_000_000)
    ot_rate: float = Field(ge=0, le=1_000_000)
    sunday_ph_rate: float = Field(ge=0, le=1_000_000)
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def valid_rate(self):
        if self.worker_id and self.trade:
            raise ValueError("Use worker or trade, not both")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return self


class ResourceRateIn(BaseModel):
    resource_type: str
    resource_name: str = Field(min_length=1, max_length=180)
    unit: str | None = Field(default=None, max_length=30)
    unit_rate: float = Field(default=0, ge=0, le=1_000_000_000)
    hourly_rate: float = Field(default=0, ge=0, le=1_000_000)
    daily_rate: float = Field(default=0, ge=0, le=1_000_000)
    fixed_rate: float = Field(default=0, ge=0, le=1_000_000_000)
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def valid_rate(self):
        if self.resource_type not in {"material", "equipment"}:
            raise ValueError("Invalid resource type")
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return self


class OtherCostIn(BaseModel):
    activity_id: str | None = None
    cost_date: date
    category: str
    description: str = Field(min_length=1, max_length=300)
    amount: float = Field(ge=0, le=10_000_000_000)
    remarks: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def valid_category(self):
        if self.category not in {"subcontractor","transport","disposal","testing_permit","miscellaneous"}:
            raise ValueError("Invalid cost category")
        return self


class ProjectValueIn(BaseModel):
    currency: str = Field(default="SGD", min_length=3, max_length=3)
    original_value: float = Field(ge=0, le=100_000_000_000)
    approved_variations: float = Field(default=0, ge=0, le=100_000_000_000)
    omissions: float = Field(default=0, ge=0, le=100_000_000_000)


class CostToCompleteIn(BaseModel):
    approved_basis: str
    manual_amount: float | None = Field(default=None, ge=0, le=100_000_000_000)
    manual_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def valid_basis(self):
        if self.approved_basis not in {"automatic", "manual"}:
            raise ValueError("Invalid forecast basis")
        if self.approved_basis == "manual" and (self.manual_amount is None or not (self.manual_reason or "").strip()):
            raise ValueError("Manual forecast requires amount and reason")
        return self
