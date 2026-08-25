from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_management_page_progressive_ui_contract():
    layout = read("frontend/js/core/layout.js")
    assert "vcms-standard-page" in layout
    assert "vcms-legacy-header" in layout
    assert "vcms-control" in layout
    assert "aria-label" in layout


def test_quality_release_and_webkit_ci_contract():
    assert "20260825-ui5" in read("frontend/js/core/pwa.js")
    assert "vcms-v44-themes-tasks" in read("frontend/sw.js")
    assert "playwright install --with-deps chromium webkit" in read(".github/workflows/test.yml")


def test_dpr_schedule_progress_is_validated_and_saved():
    main = read("backend/app/main.py")
    assert "activity_progress: list[dict]" in main
    assert "Activity progress must belong to the selected site's project" in main
    assert '"source": "dpr"' in main
    assert "/rpc/record_activity_progress" in main

