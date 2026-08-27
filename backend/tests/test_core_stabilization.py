from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_backend_foundations_are_modular():
    main = (ROOT / "backend/app/main.py").read_text()
    for name in ("settings.py", "db.py", "auth.py", "storage.py", "errors.py"):
        assert (ROOT / "backend/app" / name).exists()
    assert "from .auth import" in main
    assert "from .db import" in main
    assert "install_error_handlers(app)" in main


def test_retired_features_are_not_published_or_callable():
    main = (ROOT / "backend/app/main.py").read_text()
    sw = (ROOT / "frontend/sw.js").read_text()
    for page in ("cards.html", "worker-cards.html", "training-matrix.html"):
        assert not (ROOT / "frontend" / page).exists()
    assert '@app.get("/api/v1/notifications")' not in main
    assert '@app.post("/api/v1/push/subscribe")' not in main
    assert '@app.get("/api/v1/worker-cards")' not in main
    assert "addEventListener('push'" not in sw


def test_frontend_core_is_split_but_published_as_one_request():
    modules = ROOT / "frontend/js/core"
    for name in ("security.js", "theme.js", "components.js", "drafts.js", "pwa.js", "layout.js",
                 "app-config.js", "ui-theme.js", "export.js", "navigation.js"):
        assert (modules / name).exists()
    for page in (ROOT / "frontend").glob("*.html"):
        text = page.read_text()
        if "js/auth.js" in text:
            assert "js/core-bundle.js" in text
            assert "js/ui.js" in text


def test_appearance_foundation_keeps_semantic_colours_separate():
    main = (ROOT / "backend/app/main.py").read_text()
    theme = (ROOT / "frontend/js/core/theme.js").read_text()
    components = (ROOT / "frontend/js/core/components.js").read_text()
    settings = (ROOT / "frontend/settings.html").read_text()
    assert '@app.get("/api/v1/appearance")' in main
    assert '@app.patch("/api/v1/appearance")' in main
    assert 'user["role"] != "admin"' in main
    for token in ("--vcms-success", "--vcms-warning", "--vcms-danger", "--vcms-brand"):
        assert token in components
    assert "@media print" in components
    assert "VCMS_APPEARANCE" in theme
    assert 'id="vcms-theme-designer"' in settings and 'id="theme-seg"' in settings
