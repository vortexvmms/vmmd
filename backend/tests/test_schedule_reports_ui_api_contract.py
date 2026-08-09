from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_schedule_reports_ui_api_contract():
    html=(ROOT/"frontend"/"reports.html").read_text();router=(ROOT/"backend"/"app"/"modules"/"schedule"/"router.py").read_text();service=(ROOT/"backend"/"app"/"modules"/"schedule"/"service.py").read_text()
    for value in ("schedule_summary","lookahead","critical","progress","overdue","variance","resources"): assert f'value="{value}"' in html
    assert "/api/v1/schedule/reports/project-controls" in html
    assert '@router.get("/reports/project-controls")' in router
    assert "class ReportService" in service
