from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_wbs_ui_exposes_pending_save_controls():
    html = (ROOT / "frontend" / "schedule.html").read_text()
    for element_id in ("pending", "save-order", "discard-order", "tree"):
        assert f'id="{element_id}"' in html
    assert "js/wbs-tree.js" in html
    assert "js/schedule-wbs.js" in html


def test_wbs_ui_and_api_share_atomic_reorder_contract():
    frontend = (ROOT / "frontend" / "js" / "schedule-wbs.js").read_text()
    router = (ROOT / "backend" / "app" / "modules" / "schedule" / "router.py").read_text()
    service = (ROOT / "backend" / "app" / "modules" / "schedule" / "service.py").read_text()
    assert '"/api/v1/schedule/wbs/reorder"' in frontend
    assert 'items:nodes.map' in frontend
    assert '@router.post("/wbs/reorder")' in router
    assert '/rpc/reorder_wbs_nodes' in service


def test_all_role_navigation_catalogues_allow_schedule_page():
    shell = (ROOT / "frontend" / "js" / "shell.js").read_text()
    assert shell.count('"schedule.html"') >= 4
