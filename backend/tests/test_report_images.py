from contextlib import asynccontextmanager
from io import BytesIO

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.modules import report_images

SITE = "10000000-0000-0000-0000-000000000001"
KEY = f"{SITE}/2026-11-14/photo.png"
OLD_HOST = "lqnbdemtgkermhaqfboh.supabase.co"


@pytest.fixture
def api(monkeypatch):
    calls = []
    state = {"sites": [SITE], "role": "site_sup", "r2_status": 200}
    payload = BytesIO()
    Image.new("RGB", (2, 2)).save(payload, "PNG")

    def transport(request):
        calls.append(request)
        if request.url.path.endswith("/rpc/my_site_ids"):
            assert request.headers["Authorization"] == "Bearer test"
            return httpx.Response(200, json=state["sites"])
        assert "Authorization" not in request.headers
        if request.method == "PUT":
            assert request.headers["If-None-Match"] == "*"
            assert request.headers["Content-Type"] == "image/png"
            assert request.content == payload.getvalue()
            return httpx.Response(200)
        return httpx.Response(state["r2_status"] if request.url.host == "r2.example" else 200,
                              content=payload.getvalue())

    @asynccontextmanager
    async def shared():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            yield client

    monkeypatch.setattr(report_images, "shared_client", shared)
    monkeypatch.setattr(report_images, "PRIVATE_IMAGES_R2_ENABLED", True)
    monkeypatch.setattr(report_images, "SUPABASE_URL", "https://active.supabase.co")
    monkeypatch.setattr(report_images, "REST", "https://active.supabase.co/rest/v1")
    monkeypatch.setattr(report_images, "private_image_url", lambda b, k, m: f"https://r2.example/{b}/{k}")
    app = FastAPI()
    app.include_router(report_images.router)
    app.dependency_overrides[report_images.get_current_user] = lambda: {"role": state["role"], "token": "test"}
    return TestClient(app), state, calls, payload.getvalue()


def test_migrated_report_is_read_from_r2_and_retains_legacy_fallback(api):
    client, state, calls, data = api
    ref = f"https://{OLD_HOST}/storage/v1/object/public/dpr-photos/{KEY}"
    response = client.get("/api/v1/report-images", params={"ref": ref})
    assert response.content == data
    assert response.headers["Cache-Control"] == "private, no-store"
    assert [x.url.host for x in calls] == ["active.supabase.co", "r2.example"]
    state["r2_status"] = 404
    response = client.get("/api/v1/report-images", params={"ref": ref})
    assert response.content == data
    assert calls[-1].url.host == "active.supabase.co"


def test_report_upload_and_access_check(api):
    client, state, calls, data = api
    resp = client.put("/api/v1/report-images", params={"path": KEY}, content=data)
    assert resp.status_code == 200
    ref = resp.json()["reference"]
    assert ref.startswith(f"vcms-report-image:{SITE}/2026-11-14/")
    assert ref.endswith(".png") and ref != "vcms-report-image:" + KEY
    assert client.get("/api/v1/report-images", params={"ref": ref}).content == data
    calls.clear()
    state["sites"] = []
    assert client.get("/api/v1/report-images", params={"ref": ref}).status_code == 404
    assert client.put("/api/v1/report-images", params={"path": KEY}, content=data).status_code == 404
    assert all(req.url.host == "active.supabase.co" for req in calls)


@pytest.mark.parametrize("ref", [
    "https://unknown.example/storage/v1/object/public/dpr-photos/" + KEY,
    "vcms-report-image:" + SITE + "/2026-11-14/../other.png",
    "vcms-report-image:worker-cards/private.png",
])
def test_report_image_path_validation(api, ref):
    client, _, calls, _ = api
    assert client.get("/api/v1/report-images", params={"ref": ref}).status_code == 400
    assert not calls
