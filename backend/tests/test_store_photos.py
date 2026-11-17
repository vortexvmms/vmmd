from contextlib import asynccontextmanager
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.modules.store import router as store

ASSET = UUID("40000000-0000-0000-0000-000000000001")
PHOTO = UUID("60000000-0000-0000-0000-000000000001")
JPEG = b"\xff\xd8\xffsample"
PATH = f"/api/v1/store/photos/{PHOTO}"
USER = {"role": "admin", "token": "test"}


def fixture(monkeypatch, rpc, transport):
    async def identity():
        return USER

    @asynccontextmanager
    async def client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as session:
            yield session

    monkeypatch.setattr(store, "PRIVATE_IMAGES_R2_ENABLED", True)
    monkeypatch.setattr(store, "call_store", rpc)
    monkeypatch.setattr(store, "shared_client", client)
    monkeypatch.setattr(store, "private_image_url", lambda bucket, key, method: f"https://r2.example/{bucket}/{key}")
    app = FastAPI()
    app.include_router(store.router)
    app.dependency_overrides[store.get_current_user] = identity
    return TestClient(app)


def test_asset_photo_written_to_private_r2_and_attached(monkeypatch):
    calls = []

    async def rpc(function, data, user):
        calls.append((function, data))
        return [] if function == "store_photo_list" else str(PHOTO)

    def object_storage(request):
        assert request.method == "PUT"
        assert request.url.path == f"/store/assets/{ASSET}/{PHOTO}"
        assert request.content == JPEG
        assert request.headers["if-none-match"] == "*"
        return httpx.Response(200)

    client = fixture(monkeypatch, rpc, object_storage)
    response = client.put(PATH, params={"asset": str(ASSET)}, content=JPEG)
    assert response.status_code == 201
    assert response.json() == {"id": str(PHOTO)}
    assert [name for name, _ in calls] == ["store_photo_list", "store_photo_attach"]
    assert calls[-1][1]["p_mime"] == "image/jpeg"


def test_photo_read_refuses_access_before_fetching_r2(monkeypatch):
    async def rpc(function, data, user):
        assert function == "store_photo_read"
        raise HTTPException(403, "Photo access is unavailable for this record.")

    def unexpected(_):
        raise AssertionError("An unauthorized request must never reach R2")

    response = fixture(monkeypatch, rpc, unexpected).get(PATH)
    assert response.status_code == 403


def test_private_photo_response_is_not_cached(monkeypatch):
    async def rpc(function, data, user):
        assert function == "store_photo_read"
        return {"key": f"assets/{ASSET}/{PHOTO}", "mime": "image/jpeg"}

    def object_storage(request):
        assert request.method == "GET"
        assert request.url.path == f"/store/assets/{ASSET}/{PHOTO}"
        return httpx.Response(200, content=JPEG)

    response = fixture(monkeypatch, rpc, object_storage).get(PATH)
    assert response.content == JPEG
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
