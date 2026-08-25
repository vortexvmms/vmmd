from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_progress_schedule_and_dpr_ui_api_contract():
    progress=(ROOT/"frontend"/"js"/"schedule-progress.js").read_text()
    gantt=(ROOT/"frontend"/"js"/"schedule-gantt.js").read_text()
    dpr=(ROOT/"frontend"/"dpr.html").read_text()
    router=(ROOT/"backend"/"app"/"modules"/"schedule"/"router.py").read_text()
    main=(ROOT/"backend"/"app"/"main.py").read_text()
    assert 'id="tab-progress"' in progress and 'id="progress-panel"' in progress
    assert '"/api/v1/schedule/progress"' in progress and "js/schedule-progress.js" in gantt
    assert '@router.get("/progress")' in router and '@router.post("/progress"' in router
    assert 'id="schedule-progress"' in dpr and "activity_progress:readScheduleProgress()" in dpr
    assert '"source": "dpr"' in main and "activity_progress: list[dict]" in main
    assert "Activity progress must belong to the selected site's project" in main
