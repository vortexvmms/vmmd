from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_schedule_page_exposes_activity_foundation_controls():
    html = (ROOT / "frontend" / "schedule.html").read_text()
    for control in ('id="tab-activities"', 'id="add-activity"', 'id="activity-wbs"', 'id="activity-type"', 'id="activity-duration"'):
        assert control in html
    assert "js/schedule-activities.js" in html


def test_activity_frontend_and_api_paths_match():
    frontend = (ROOT / "frontend" / "js" / "schedule-activities.js").read_text()
    router = (ROOT / "backend" / "app" / "modules" / "schedule" / "router.py").read_text()
    assert '"/api/v1/schedule/activities' in frontend
    assert '@router.get("/activities")' in router
    assert '@router.post("/activities"' in router
    assert '@router.patch("/activities/{activity_id}")' in router
