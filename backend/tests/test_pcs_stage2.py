from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend/app/main.py").read_text()
ROUTER = (ROOT / "backend/app/modules/pcs_plan_router.py").read_text()
PAGE = (ROOT / "frontend/pcs-dashboard.html").read_text()


def test_plan_router_mounted():
    assert "from .modules.pcs_plan_router import PcsPlanContext, build_pcs_plan_router" in MAIN
    assert "build_pcs_plan_router(PcsPlanContext(" in MAIN


def test_plan_router_endpoints_and_guards():
    for frag in ('prefix="/api/v1/pcs"', "/plan", "/plan/{plan_id}/publish",
                 "/dashboard", "/whatsapp", "def management(user)", "await c.audit("):
        assert frag in ROUTER, f"missing {frag}"


def test_publish_snapshots_a_revision():
    assert "pcs_daily_plan_revisions" in ROUTER
    assert '"status": "published"' in ROUTER
    assert "revno + 1" in ROUTER  # next revision reserved


def test_no_cost_or_rate_in_plan_router():
    low = ROUTER.lower()
    for banned in ("unit_cost", "total_cost", " rate ", "profit", "margin", "pnl", "amount"):
        assert banned not in low, f"unexpected cost token: {banned}"


def test_whatsapp_is_deterministic_client_side():
    # No external AI service; message built in the page and posted for audit only.
    assert "TOMORROW WORK PLAN" in PAGE
    assert "wa.me" in PAGE
    assert "/api/v1/pcs/whatsapp" in PAGE
    assert "generativelanguage" not in PAGE and "openai" not in PAGE.lower()


def test_planning_page_uses_stage2_endpoints():
    for frag in ("/api/v1/pcs/plan", "/api/v1/pcs/dashboard", "/api/v1/pcs/locations",
                 "Bulk paste", "Copy from date", "Publish to supervisors"):
        assert frag in PAGE, f"missing {frag}"


def test_priority3_manager_resources_and_request_review():
    report_router = (ROOT / "backend/app/modules/pcs_report_router.py").read_text()
    for frag in ("/plan/{plan_id}/material", "/plan/{plan_id}/plant",
                 "/plan/{plan_id}/reopen", "planned_materials", "planned_plant"):
        assert frag in ROUTER
    for frag in ("/resource-requests", "/resource-request/{request_id}", "manager_remarks"):
        assert frag in report_router
    for frag in ("Planned materials", "Planned plant / equipment", "previewPlan()",
                 "reopenPlan()", "reviewRequest("):
        assert frag in PAGE


def test_standard_dpr_still_untouched():
    dpr = (ROOT / "frontend/dpr.html").read_text()
    assert "Description of works" in dpr
    assert "/api/v1/pcs/" not in dpr
