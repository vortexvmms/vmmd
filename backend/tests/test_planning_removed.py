from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_old_planning_is_not_exposed_in_navigation():
    home = (ROOT / "frontend" / "home.html").read_text()
    shell = (ROOT / "frontend" / "js" / "shell.js").read_text()
    users = (ROOT / "frontend" / "users.html").read_text()
    for source in (home, shell, users):
        assert "schedule.html" not in source
        assert "reports.html" not in source
    # The obsolete schedule/reports implementation stays removed. Planning V2.1
    # is a new administrator-only page with a different route and contracts.
    assert 'grp:"Planning"' in home
    assert '"planning.html"' in home
    assert 'group:"Planning"' in shell
    assert '"planning.html"' in shell


def test_old_planning_pages_and_backend_module_are_removed():
    assert not (ROOT / "frontend" / "schedule.html").exists()
    assert not (ROOT / "backend" / "app" / "modules" / "schedule").exists()
    main = (ROOT / "backend" / "app" / "main.py").read_text()
    assert '"/api/v1/schedule' not in main
    assert 'build_planning_router' in main


def test_dpr_no_longer_reads_or_writes_schedule_progress():
    dpr = (ROOT / "frontend" / "dpr.html").read_text()
    main = (ROOT / "backend" / "app" / "main.py").read_text()
    for source in (dpr, main):
        assert "activity_progress" not in source
        assert "record_activity_progress" not in source
