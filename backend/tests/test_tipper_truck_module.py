from pathlib import Path

import pytest
from fastapi import HTTPException

from app.modules.equipment.router import (
    _month_bounds,
    _normalise_extraction,
    _parse_date,
    _valid_public_image,
)


ROOT = Path(__file__).resolve().parents[2]


def test_tipper_migration_contains_master_data_and_secure_tables():
    sql = (ROOT / "db" / "migrations" / "0016_tipper_truck_supply.sql").read_text()
    for table in ("tipper_clients", "tipper_providers", "tipper_work_types", "tipper_drivers",
                  "tipper_trips", "tipper_import_batches", "tipper_import_items"):
        assert f"public.{table}" in sql
        assert f"alter table public.{table} enable row level security" in sql
    for seed in ("PKJV-T5-MSP", "COJV-T5-SUB", "VORTEX", "SVP", "VEL",
                 "Day Work", "Trip Work", "Night Work", "Hourly"):
        assert seed in sql
    assert "generated always as" in sql
    assert "values('0016'" in sql


def test_equipment_navigation_and_page_are_published():
    shell = (ROOT / "frontend" / "js" / "shell.js").read_text()
    home = (ROOT / "frontend" / "home.html").read_text()
    page = (ROOT / "frontend" / "tipper-trucks.html").read_text()
    sw = (ROOT / "frontend" / "sw.js").read_text()
    assert "Equipment & Machineries" in shell
    assert "Equipment & Machineries" in home
    assert "Tipper Truck Supply" in shell
    assert "tipper-trucks.html" in shell and "tipper-trucks.html" in sw
    assert "Bulk Trip Sheets" in page
    assert "multiple" in page and "maximum of 30" in page
    assert "A4 landscape" in page
    assert "configured Gemini service" in page


def test_extraction_normalisation_is_conservative():
    value = _normalise_extraction({
        "date": "31/07/2026", "truck_no": "xf1412y", "quantity": "10 loads",
        "transport_rate": "$85.00", "unit_type": "unknown", "confidence": 104,
        "warnings": ["rate unclear"],
    })
    assert value["trip_date"] == "2026-07-31"
    assert value["truck_no"] == "XF1412Y"
    assert value["quantity"] == 10
    assert value["transport_rate"] == 85
    assert value["unit_type"] == "load"
    assert value["confidence"] == 100
    assert value["warnings"] == ["rate unclear"]


@pytest.mark.parametrize(("raw", "expected"), [
    ("2026-07-31", "2026-07-31"), ("31-07-26", "2026-07-31"),
    ("31-Jul-26", "2026-07-31"), ("", None), ("not a date", None),
])
def test_trip_sheet_dates(raw, expected):
    assert _parse_date(raw) == expected


def test_month_filter_rejects_bad_ranges():
    assert _month_bounds("2026-12") == ("2026-12-01", "2027-01-01")
    with pytest.raises(HTTPException):
        _month_bounds("2026-13")


def test_extraction_only_reads_the_exact_uploaded_r2_object():
    base = "https://files.example.com/vcms"
    key = "tipper-trip-sheets/2026/09/batch/photo 1.jpg"
    assert _valid_public_image(base, "https://files.example.com/vcms/tipper-trip-sheets/2026/09/batch/photo%201.jpg", key)
    assert not _valid_public_image(base, "https://files.example.com/vcms/worker-photos/private.jpg", key)
    assert not _valid_public_image(base, "https://files.example.com/vcms/tipper-trip-sheets/2026/09/batch/photo%201.jpg?x=1", key)
    assert not _valid_public_image(base, "https://files.example.com.evil.test/vcms/tipper-trip-sheets/2026/09/batch/photo%201.jpg", key)
