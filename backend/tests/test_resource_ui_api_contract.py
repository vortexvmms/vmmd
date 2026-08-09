from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_resource_ui_and_api_contract():
    html=(ROOT/"frontend"/"schedule.html").read_text(); js=(ROOT/"frontend"/"js"/"schedule-resources.js").read_text(); router=(ROOT/"backend"/"app"/"modules"/"schedule"/"router.py").read_text()
    for control in ('id="tab-resources"','id="add-master-resource"','id="import-resource"','id="assign-resource"'): assert control in html
    assert "js/schedule-resources.js" in html
    assert '"/api/v1/schedule/resources' in js
    assert '@router.post("/resources/master"' in router
    assert '@router.post("/resources/project"' in router
    assert '@router.post("/resources/assignments"' in router
