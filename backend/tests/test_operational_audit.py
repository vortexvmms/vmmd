"""Critical operational regression contracts for the live VCMS modules."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend/app/main.py").read_text()
ATT = (ROOT / "frontend/attendance.html").read_text()
HOME = (ROOT / "frontend/home.html").read_text()
DASH = (ROOT / "frontend/dashboard.html").read_text()
REPORTS = (ROOT / "frontend/reports.html").read_text()
RESOURCE = (ROOT / "frontend/resource-summary.html").read_text()


def _hours_engine():
    tree = ast.parse(MAIN)
    wanted = {"_to_min", "compute_hours"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    ns = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "hours-engine", "exec"), ns)
    return ns["compute_hours"]


def test_confirmed_hours_rules():
    calc = _hours_engine()
    assert calc("WD", "08:00", "17:00", False) == (8.0, 0.0)
    assert calc("WD", "08:00", "19:00", False) == (8.0, 2.0)
    assert calc("SAT", "08:00", "12:00", False) == (4.0, 0.0)
    assert calc("SAT", "08:00", "17:00", False) == (4.0, 4.0)
    assert calc("SUN", "08:00", "17:00", False) == (0.0, 8.0)
    assert calc("PH", "08:00", "17:00", False) == (0.0, 8.0)
    assert calc("WD", "20:00", "06:00", True) == (8.0, 2.0)


def test_all_management_surfaces_use_server_hour_fields():
    for page in (HOME, DASH):
        assert "month_normal_hours" in page and "month_ot_hours" in page
    assert '"totals": {"nh"' in MAIN
    assert "/api/v1/reports/" in REPORTS
    assert "/api/v1/resource-summary" in RESOURCE


def test_mobile_end_time_has_durable_queue_and_recovery():
    required = [
        "localStorage.setItem(ATT_QUEUE_KEY", "SAVE_QUEUE", 'addEventListener("online"',
        'addEventListener("offline"', "flushSaves", "reconcileSavedChanges",
        "saved on phone", "waiting for network", "/api/v1/attendance/batch",
    ]
    for token in required:
        assert token in ATT, token


def test_submit_waits_for_unconfirmed_mobile_changes():
    assert "if(SAVE_QUEUE.size||SAVE_RUNNING)" in ATT
    assert "not yet confirmed" in ATT


def test_responsive_contracts_present():
    pages = list((ROOT / "frontend").glob("*.html"))
    assert len(pages) >= 20
    for page in pages:
        assert 'name="viewport"' in page.read_text(errors="ignore"), page.name
    assert "max-width:900px" in HOME
    assert "min-width:901px" in HOME
