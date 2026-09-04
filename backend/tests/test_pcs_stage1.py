from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = (ROOT / "db/migrations/0017_pcs_stage1_foundation.sql").read_text()
MAIN = (ROOT / "backend/app/main.py").read_text()
ROUTER = (ROOT / "backend/app/modules/pcs_router.py").read_text()
DPRPROJ = (ROOT / "frontend/dpr-projects.html").read_text()
DPR = (ROOT / "frontend/dpr.html").read_text()

PCS_TABLES = [
    "pcs_work_locations", "pcs_location_supervisors", "pcs_daily_plans",
    "pcs_daily_plan_revisions", "pcs_planned_activities", "pcs_planned_materials",
    "pcs_planned_plant", "pcs_daily_reports", "pcs_location_reports",
    "pcs_location_activities", "pcs_worker_distributions", "pcs_actual_materials",
    "pcs_actual_plant", "pcs_resource_requests", "pcs_location_photos",
    "pcs_whatsapp_plan_messages",
]


def test_migration_is_additive_and_versioned():
    assert MIG.strip().startswith("-- VCMS PCS")
    assert "begin;" in MIG and "commit;" in MIG
    assert "('0017'," in MIG  # schema_migrations entry
    # DPR mode flag, defaulting existing projects to standard (Section 2)
    assert "add column if not exists dpr_mode text not null default 'standard'" in MIG
    assert "check (dpr_mode in ('standard','multi_location'))" in MIG


def test_all_sixteen_pcs_tables_created_with_rls():
    for t in PCS_TABLES:
        assert f"create table if not exists public.{t}" in MIG, f"missing table {t}"
    # RLS is enabled for every PCS table (via the loop) and the helper exists
    assert "enable row level security" in MIG
    assert "create or replace function public.my_pcs_location_ids()" in MIG
    # one report per location per date (Section 18.3)
    assert "unique (parent_id, location_id)" in MIG
    # cumulative percentage bounded 0-100 (Section 5)
    assert "percent_complete >= 0 and percent_complete <= 100" in MIG


def test_no_cost_or_rate_columns_on_pcs_tables():
    # Supervisors read these tables; cost/rate/P&L must live only in the PR/costing
    # module, never here (Section 10, 11, 19).
    lowered = MIG.lower()
    for banned in ("unit_cost", "total_cost", " rate ", "amount", "profit", "margin", "p_and_l", "pnl"):
        assert banned not in lowered, f"unexpected cost token in PCS migration: {banned}"


def test_resource_request_converts_to_pr_without_cost():
    assert "converted_pr_id uuid" in MIG  # explicit manager conversion path (Section 11.11)


def test_pcs_router_mounted_and_role_guarded():
    assert "from .modules.pcs_router import PcsContext, build_pcs_router" in MAIN
    assert "build_pcs_router(PcsContext(" in MAIN
    assert 'prefix="/api/v1/pcs"' in ROUTER
    assert "MANAGEMENT_ROLES" in ROUTER
    assert "def management(user)" in ROUTER
    assert "await c.audit(" in ROUTER  # mutations are audited
    assert "SUPERVISOR_ROLES" in ROUTER
    assert 'row.get("pcs_location_supervisors")' in ROUTER


def test_dpr_projects_page_has_feature_flagged_pcs_ui():
    assert "PCS_FEATURE" in DPRPROJ
    assert "/api/v1/pcs/dpr-config" in DPRPROJ
    assert "/api/v1/pcs/locations" in DPRPROJ


def test_standard_dpr_page_untouched_in_stage1():
    # Stage 1 does not modify the supervisor DPR page; Standard behaviour is intact.
    assert "Description of works" in DPR
    assert "/api/v1/pcs/" not in DPR
