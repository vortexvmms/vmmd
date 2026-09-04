from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


def page(name: str) -> str:
    return (FRONTEND / name).read_text()


def test_critical_supervisor_pages_use_shared_header_and_release():
    for name in ("request.html", "attendance.html", "allocation.html", "whatsapp.html"):
        html = page(name)
        assert 'class="vcms-page-header"' in html
        assert "vcms-page-header__row" in html
        assert "vcms-page-toolbar" in html
        assert "vcms-control" in html
        assert "core-bundle.js?v=20260904-history1" in html


def test_critical_workflows_use_shared_mobile_actions_and_toast():
    for name in ("request.html", "attendance.html", "allocation.html", "whatsapp.html"):
        html = page(name)
        assert "vcms-mobile-actions" in html
        assert 'class="vcms-toast hidden"' in html


def test_supervisor_mobile_home_includes_site_progress_module():
    html = page("home.html")
    assert 'if(TIER[role]==="supervisor")' in html
    assert '{name:"Site progress"' in html
    for href in ("request.html", "attendance.html", "whatsapp.html", "camera.html", "dpr.html", "dprlist.html", "dashboard.html", "settings.html", "help.html"):
        assert f'"{href}"' in html
    assert "body.sup-mobile" in html


def test_stage_two_cache_and_component_contract():
    assert "vcms-v57-supervisor-site-progress" in page("sw.js")
    css = page("js/core/components.js")
    for class_name in (
        ".vcms-segmented",
        ".vcms-section-card",
        ".vcms-filter-row",
        ".vcms-mobile-actions",
        ".vcms-toast",
        ".vcms-supervisor-main",
    ):
        assert class_name in css
