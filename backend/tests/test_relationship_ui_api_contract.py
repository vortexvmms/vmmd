from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_schedule_page_exposes_logic_controls():
    html = (ROOT / "frontend" / "schedule.html").read_text()
    for control in ('id="tab-logic"', 'id="add-relationship"', 'id="logic-predecessor"', 'id="logic-successor"', 'id="logic-lag"'):
        assert control in html
    assert "js/schedule-logic.js" in html


def test_logic_frontend_and_api_paths_match():
    frontend = (ROOT / "frontend" / "js" / "schedule-logic.js").read_text()
    router = (ROOT / "backend" / "app" / "modules" / "schedule" / "router.py").read_text()
    assert '"/api/v1/schedule/relationships' in frontend
    assert '@router.get("/relationships")' in router
    assert '@router.post("/relationships"' in router
    assert '@router.patch("/relationships/{relationship_id}")' in router
