from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


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
