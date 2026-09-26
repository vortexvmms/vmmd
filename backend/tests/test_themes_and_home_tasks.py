from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_three_company_theme_combinations_are_available():
    theme = read("frontend/js/core/theme.js")
    designer = read("frontend/js/theme-designer.js")
    backend = read("backend/app/main.py")
    for preset, label in (
        ("executive", "Vortex Executive"),
        ("industrial", "Industrial Navy"),
        ("construction", "Construction Amber"),
    ):
        assert f"{preset}:" in theme
        assert label in designer
        assert f'"{preset}":' in backend
    for field in ("secondary", "accent", "page", "surface", "ink"):
        assert field in theme
        assert field in backend


def test_complete_theme_is_central_and_admin_only():
    backend = read("backend/app/main.py")
    designer = read("frontend/js/theme-designer.js")
    settings = read("frontend/settings.html")
    assert "theme_bundle" in backend
    assert "_normalise_theme_bundle" in backend
    assert 'me.role !== "admin"' in designer
    assert "theme_bundle: bundle" in designer
    assert 'id="vcms-theme-designer"' in settings
    assert 'id="company-theme"' not in settings


def test_home_uses_company_variables_and_tasks_have_failure_fallback():
    home = read("frontend/home.html")
    assert "var(--vcms-brand)" in home
    assert "var(--vcms-secondary)" in home
    assert "Tasks could not be loaded" in home
    assert "onclick=\"loadTasks()\"" in home


def test_todo_reconciliation_cannot_hide_normal_todos():
    main = read("backend/app/main.py")
    assert "asyncio.wait_for(dpr_missing" in main
    assert "A reminder scan must never make the user's normal to-do list disappear" in main


def test_completed_todos_have_a_separate_filterable_view():
    todo = read("frontend/todo.html")
    backend = read("backend/app/main.py")
    assert 'id="tab-active"' in todo
    assert 'id="tab-completed"' in todo
    assert 'id="completed-search"' in todo
    assert 'id="completed-period"' in todo
    assert 'id="completed-quadrant"' in todo
    assert 'id="completed-source"' in todo
    assert 'id="completed-page-info"' in todo
    assert "COMPLETED_PAGE_SIZE=25" in todo
    assert 'active.filter(t=>(t.quadrant||"inbox")===q)' in todo
    assert 'created_at,updated_at,source,source_key' in backend


def test_connected_workflow_navigation_is_available():
    shell = read("frontend/js/shell.js")
    workflow = read("frontend/js/workflow.js")
    home = read("frontend/home.html")
    assert "Reports & Analytics" in shell
    assert "Reports & Analytics" in home
    assert "vcms_work_context" in workflow
    for page in ("request.html", "allocation.html", "attendance.html", "verify.html", "timesheet.html"):
        assert page in workflow
    assert "Workflow context" in workflow
    assert "Open pending attendance" in home
    assert "Open missing end times" in home
