from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


UnitType = Literal["load", "tonnage", "hour", "meter", "trip", "day"]


class MasterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    provider_id: str | None = None
    truck_no: str | None = Field(default=None, max_length=40)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.strip().split())


class TripCreate(BaseModel):
    client_id: str
    provider_id: str
    work_type_id: str
    driver_id: str | None = None
    driver_name: str | None = Field(default=None, max_length=160)
    trip_sheet_no: str = Field(min_length=1, max_length=80)
    trip_date: date
    do_no: str = Field(min_length=1, max_length=80)
    truck_no: str = Field(min_length=1, max_length=40)
    pickup_location: str = Field(min_length=1, max_length=240)
    delivery_location: str = Field(min_length=1, max_length=240)
    material_type: str = Field(min_length=1, max_length=160)
    quantity: float = Field(gt=0, le=1_000_000)
    unit_type: UnitType = "load"
    transport_rate: float = Field(ge=0, le=10_000_000)
    source: Literal["manual", "image_extract"] = "manual"
    source_image_url: str | None = Field(default=None, max_length=2000)
    source_image_key: str | None = Field(default=None, max_length=800)
    extraction_confidence: float | None = Field(default=None, ge=0, le=100)
    import_item_id: str | None = None

    @field_validator("trip_sheet_no", "do_no", "truck_no", "pickup_location",
                     "delivery_location", "material_type")
    @classmethod
    def clean_required(cls, value: str) -> str:
        return " ".join(value.strip().split())


class TripBulkCreate(BaseModel):
    batch_id: str | None = None
    items: list[TripCreate] = Field(min_length=1, max_length=30)


class ImportBatchCreate(BaseModel):
    total_files: int = Field(ge=1, le=30)


class ExtractTripSheet(BaseModel):
    image_url: str = Field(min_length=8, max_length=2000)
    image_key: str = Field(min_length=8, max_length=800)
    original_name: str = Field(min_length=1, max_length=300)
