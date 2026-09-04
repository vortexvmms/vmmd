from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend/app/main.py").read_text()
ROUTER = (ROOT / "backend/app/modules/pcs_report_router.py").read_text()
JS = (ROOT / "frontend/js/pcs-dpr.js").read_text()
DPR = (ROOT / "frontend/dpr.html").read_text()
MIG = (ROOT / "db/migrations/0018_pcs_stage3_report_rls.sql").read_text()


def test_report_router_mounted():
    assert "from .modules.pcs_report_router import PcsReportContext, build_pcs_report_router" in MAIN
    assert "build_pcs_report_router(PcsReportContext(" in MAIN


def test_report_router_flow_and_guards():
    for frag in ('prefix="/api/v1/pcs"', "/report/ensure", "/report/{parent_id}/location",
                 "/location-report/{lr_id}/activity", "/location-report/{lr_id}/actual-material",
                 "/location-report/{lr_id}/actual-plant", "/resource-request",
                 "/location-report/{lr_id}/reset-draft",
                 "/location-report/{lr_id}/submit", "await c.audit("):
        assert frag in ROUTER, f"missing {frag}"


def test_submit_uses_optimistic_concurrency_and_idempotency():
    assert "record_version" in ROUTER
    assert "status_code=409" in ROUTER          # conflict when versions differ
    assert '"idempotent": True' in ROUTER       # re-submit is a safe no-op


def test_no_cost_tokens_in_report_router():
    low = ROUTER.lower()
    for banned in ("unit_cost", "total_cost", " rate ", "profit", "margin", "pnl"):
        assert banned not in low, f"unexpected cost token: {banned}"


def test_stage3_migration_is_additive_rls_only():
    assert "create policy pcs_par_ins_member" in MIG
    assert "('0018'," in MIG
    assert "create table" not in MIG.lower()    # additive RLS only, no new tables


def test_supervisor_module_is_failsafe_and_offline():
    # Inert unless the backend confirms multi_location; never breaks Standard DPR.
    assert 'if(typeof vmmsApi!=="function")return' in JS
    assert "multi_location" in JS
    assert "function deactivate()" in JS and "showStandard()" in JS
    assert "localStorage" in JS                 # offline draft
    assert "/api/v1/pcs/location-report/" in JS and "/submit" in JS


def test_dpr_page_only_gains_the_loader_and_is_otherwise_intact():
    assert 'js/pcs-dpr.js' in DPR               # one-line loader added
    assert "Description of works" in DPR         # standard block still present
    assert 'onclick="save()"' in DPR             # standard save path untouched


def test_pcs_replaces_only_description_and_has_retry_safety():
    assert 'standard-description-panel' in DPR
    assert 'pcs-description-host' in DPR
    assert 'function standardEls(){return [$("standard-description-panel")]' in JS
    assert '$("dpr-content")' not in JS.split("function standardEls()", 1)[1].split("function hideStandard", 1)[0]
    assert 'reset-draft' in JS
    assert '_pendingSubmit' in JS and 'window.addEventListener("online"' in JS
    assert 'Locations submitted (' in JS


def test_priority2_supervisor_workflow_is_complete():
    for frag in ("Copy latest", "report/latest-location", "previous_percent",
                 "reduction_reason", "activity_status", "Materials required",
                 "Plant, equipment & tools required", "Activity photos",
                 "/photo", "Undo copy", "Manpower assigned to this location",
                 "WhatsApp update", "openLocationWhatsApp", "wa.me"):
        assert frag in JS
    for frag in ("latest-location", "LocationPhotoIn", "ResourceRequestPatch",
                 "Give a reason when cumulative completion is reduced"):
        assert frag in ROUTER
