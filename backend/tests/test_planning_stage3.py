from datetime import date
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.modules.planning.schemas import ManpowerRateIn, OtherCostIn, ResourceRateIn

ROOT = Path(__file__).resolve().parents[2]


def test_stage3_rate_models_and_validation():
    r=ManpowerRateIn(normal_rate=10,ot_rate=15,sunday_ph_rate=20,effective_from=date(2026,8,1))
    assert r.sunday_ph_rate == 20
    e=ResourceRateIn(resource_type="equipment",resource_name="Excavator",hourly_rate=80,daily_rate=600,fixed_rate=50,effective_from=date(2026,8,1))
    assert (e.hourly_rate,e.daily_rate,e.fixed_rate)==(80,600,50)
    with pytest.raises(ValidationError):
        ManpowerRateIn(worker_id="x",trade="Carpenter",normal_rate=1,ot_rate=1,sunday_ph_rate=1,effective_from=date(2026,8,1))


def test_stage3_migration_enforces_private_rates_and_separate_pr_forecast():
    sql=(ROOT/"db/migrations/0011_stage3_resource_costing.sql").read_text().lower()
    assert "planning_manpower_rates" in sql and "planning_resource_rates" in sql
    assert "planning_other_direct_costs" in sql
    assert "public.my_role()='admin'" in sql
    assert "pr_requested_forecast" in sql
    assert "sunday_ph_rate" in sql
    assert "security definer" in sql


def test_stage3_commercial_routes_are_admin_gated():
    router=(ROOT/"backend/app/modules/planning/router.py").read_text()
    assert '"/projects/{project_id}/costing"' in router
    assert router.count("admin(user)") >= 10
    assert "planning_project_cost_summary" in router


def test_other_direct_cost_categories_are_controlled():
    x=OtherCostIn(cost_date=date(2026,8,1),category="transport",description="Lorry",amount=120)
    assert x.amount == 120
    with pytest.raises(ValidationError):
        OtherCostIn(cost_date=date(2026,8,1),category="salary",description="x",amount=1)
