from datetime import date
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.modules.planning.schemas import CostToCompleteIn, ProjectValueIn

ROOT=Path(__file__).resolve().parents[2]


def test_stage4_value_and_manual_forecast_validation():
    v=ProjectValueIn(original_value=1_000_000,approved_variations=50_000,omissions=10_000)
    assert v.original_value+v.approved_variations-v.omissions==1_040_000
    c=CostToCompleteIn(approved_basis="manual",manual_amount=200_000,manual_reason="Review meeting")
    assert c.manual_amount==200_000
    with pytest.raises(ValidationError):
        CostToCompleteIn(approved_basis="manual",manual_amount=200_000)


def test_stage4_formulas_security_and_snapshots_are_in_migration():
    sql=(ROOT/"db/migrations/0012_stage4_forecast_pnl.sql").read_text().lower()
    assert "current_value:=coalesce(v.original_value,0)+coalesce(v.approved_variations,0)-coalesce(v.omissions,0)" in sql
    assert "final_cost:=actual+approved_ctc" in sql
    assert "profit:=current_value-final_cost" in sql
    assert "planning_pnl_snapshots" in sql and "source_version" in sql
    assert "public.my_role()='admin'" in sql


def test_stage4_routes_are_admin_gated_and_operationally_labelled():
    router=(ROOT/"backend/app/modules/planning/router.py").read_text()
    assert '"/projects/{project_id}/forecast-pnl"' in router
    assert "create_planning_pnl_snapshot" in router
    assert router.count("admin(user)") >= 14
