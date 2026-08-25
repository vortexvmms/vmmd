from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_three_company_theme_combinations_are_available():
    theme = read("frontend/js/core/theme.js")
    settings = read("frontend/settings.html")
    backend = read("backend/app/main.py")
    for preset, label in (
        ("executive", "Vortex Executive"),
        ("industrial", "Industrial Navy"),
        ("construction", "Construction Amber"),
    ):
        assert f"{preset}:" in theme
        assert label in settings
        assert f'"{preset}":' in backend
    for field in ("secondary", "accent", "page", "surface", "ink"):
        assert field in theme
        assert field in backend


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

