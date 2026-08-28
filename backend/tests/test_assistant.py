from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASSISTANT = (ROOT / "backend/app/assistant.py").read_text()
MAIN = (ROOT / "backend/app/main.py").read_text()
LAYOUT = (ROOT / "frontend/js/core/layout.js").read_text()
WIDGET = (ROOT / "frontend/js/chatbot.js").read_text()
SW = (ROOT / "frontend/sw.js").read_text()


def test_assistant_is_authenticated_role_scoped_and_server_keyed():
    assert "Depends(get_current_user)" in ASSISTANT
    assert 'headers = {"Authorization": f"Bearer {token}"}' in ASSISTANT
    assert 'os.environ.get("GEMINI_API_KEY"' in ASSISTANT
    assert "GEMINI_API_KEY" not in WIDGET
    assert "app.include_router(assistant_router)" in MAIN


def test_assistant_has_cost_and_abuse_guards():
    assert "max_length=1200" in ASSISTANT
    assert "_RATE_MAX_REQUESTS = 6" in ASSISTANT
    assert "status_code=429" in ASSISTANT
    assert "payload.get(\"model\"" not in ASSISTANT
    assert "model or GEMINI_MODEL" not in ASSISTANT
    assert "maxOutputTokens" in ASSISTANT
    assert "_cap(result)" in ASSISTANT


def test_site_wide_widget_is_published_without_local_chat_storage():
    assert 'assistant.src="js/chatbot.js?v=20260828-1"' in LAYOUT
    assert "/api/v1/assistant" in WIDGET
    assert "vmmsApi" in WIDGET
    assert "localStorage.setItem" not in WIDGET
    assert "textContent = text" in WIDGET
    assert "vcms-v51-assistant" in SW
    assert "js/chatbot.js?v=20260828-1" in SW
