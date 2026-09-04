from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend/app/main.py").read_text()
ROUTER = (ROOT / "backend/app/modules/pcs_dist_router.py").read_text()
PAGE = (ROOT / "frontend/pcs-report.html").read_text()


def test_dist_router_mounted():
    assert "from .modules.pcs_dist_router import PcsDistContext, build_pcs_dist_router" in MAIN
    assert "build_pcs_dist_router(PcsDistContext(" in MAIN


def test_distribution_endpoints_and_readiness():
    for frag in ('prefix="/api/v1/pcs"', "/distribution", "/readiness",
                 "def management(user)", "await c.audit("):
        assert frag in ROUTER, f"missing {frag}"


def test_distribution_detects_time_overlap_conflicts():
    assert "def _overlap(" in ROUTER and "def _window(" in ROUTER
    assert "status_code=409" in ROUTER            # overlapping assignment rejected
    assert '"conflicts"' in ROUTER                # conflicts surfaced on read


def test_distribution_never_touches_allocation_or_payroll():
    low = ROUTER.lower()
    for banned in ("allocations", "attendance", "payroll", "timesheet",
                   "unit_cost", "total_cost", " rate ", "profit", "margin", "pnl"):
        assert banned not in low, f"distribution must not reference {banned}"


def test_report_page_has_readiness_distribution_and_pdf():
    for frag in ("/api/v1/pcs/readiness", "/api/v1/pcs/distribution", "/api/v1/pcs/report",
                 "window.print()", "Consolidated report", "Manpower distribution",
                 "PCS DAILY PROGRESS REPORT", "@media print"):
        assert frag in PAGE, f"missing {frag}"


def test_priority3_report_outputs_and_location_resources():
    for frag in ("Image PDF", "Excel", "imagePdf()", "excelExport()",
                 "Requirements for upcoming work", "Location photos",
                 "All locations (consolidated)"):
        assert frag in PAGE


def test_standard_dpr_still_untouched():
    dpr = (ROOT / "frontend/dpr.html").read_text()
    assert "Description of works" in dpr
    assert 'onclick="save()"' in dpr
