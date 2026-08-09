from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_schedule_page_exposes_calendar_controls():
    html = (ROOT / "frontend" / "schedule.html").read_text()
    for control in ('id="tab-calendars"', 'id="add-calendar"', 'id="calendar-name"', 'id="calendar-hours"'):
        assert control in html
    assert "js/schedule-calendars.js" in html


def test_calendar_frontend_and_api_paths_match():
    frontend = (ROOT / "frontend" / "js" / "schedule-calendars.js").read_text()
    router = (ROOT / "backend" / "app" / "modules" / "schedule" / "router.py").read_text()
    assert '"/api/v1/schedule/calendars' in frontend
    assert '@router.get("/calendars")' in router
    assert '@router.post("/calendars"' in router
    assert '@router.put("/calendars/{calendar_id}/workweek")' in router
    assert '@router.post("/calendars/{calendar_id}/exceptions"' in router
