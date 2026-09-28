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
    assert "vcms-v68-attendance-popup" in page("sw.js")
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


def test_pr_pdf_preview_close_controls_stay_accessible():
    html = page("pr-dashboard.html")
    assert "z-index:10000" in html
    assert 'id="preview-close"' in html
    assert 'event.key==="Escape"' in html
    assert "event.target===this" in html


def test_attendance_transfer_control_and_popup_stay_above_desktop_footer():
    html = page("attendance.html")
    assert "#att-main{padding-bottom:150px!important}" in html
    assert "#addbtn{scroll-margin-bottom:130px}" in html
    assert "#tr-modal{z-index:1200" in html
    assert 'id="tr-panel"' in html
    assert "100dvh - 32px" in html
    assert 'event.key === "Escape"' in html
    assert "event.target === event.currentTarget" in html


def test_saved_theme_is_bootstrapped_before_first_paint():
    for path in FRONTEND.glob("*.html"):
        html = path.read_text()
        if 'href="css/app.css"' not in html:
            continue
        assert 'src="js/theme-boot.js?v=20260927-1"' in html, path.name
        assert 'href="css/theme-boot.css?v=20260927-1"' in html, path.name
        assert html.index("theme-boot.js") < html.index("css/app.css"), path.name
        assert html.index("theme-boot.css") < html.index("css/app.css"), path.name

    boot = page("js/theme-boot.js")
    assert 'vcms_company_appearance_v1' in boot
    assert 'data-vcms-theme-boot' in boot
    css = page("css/theme-boot.css")
    assert "background-color: var(--vcms-brand) !important" in css
