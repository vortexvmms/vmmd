from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_gantt_and_baseline_ui_api_contract():
    html=(ROOT/"frontend"/"schedule.html").read_text(); js=(ROOT/"frontend"/"js"/"schedule-gantt.js").read_text(); router=(ROOT/"backend"/"app"/"modules"/"schedule"/"router.py").read_text()
    for control in ('id="tab-gantt"','id="calculate-schedule"','id="create-baseline"','id="baseline-select"','id="gantt-chart"'): assert control in html
    assert "js/schedule-gantt.js" in html
    assert '"/api/v1/schedule/calculate"' in js and '"/api/v1/schedule/baselines"' in js
    assert '@router.post("/calculate")' in router and '@router.post("/baselines"' in router
