import asyncio
import uuid
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import HTTPException

from app import main


@pytest.mark.parametrize("visible", [True, False])
def test_sic_r2_read_requires_attachment_visibility(monkeypatch, visible):
    attachment_id = uuid.uuid4()
    record_id = str(uuid.uuid4())
    key = f"{record_id}/{uuid.uuid4()}"
    calls = []
    payload = b"sample image"

    def handle(request):
        calls.append(request)
        if request.url.host == "db.example":
            assert request.headers["authorization"] == "Bearer test"
            assert request.url.params["id"] == f"eq.{attachment_id}"
            attachment = {"record_id": record_id, "object_key": key, "mime_type": "image/png"}
            return httpx.Response(200, json=[attachment] if visible else [])
        assert request.url.host == "images.example"
        assert request.url.path == "/sic-cards/" + key
        assert "authorization" not in request.headers
        return httpx.Response(200, content=payload, headers={"content-type": "image/png"})

    @asynccontextmanager
    async def shared():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            yield client

    monkeypatch.setattr(main, "shared_client", shared)
    monkeypatch.setattr(main, "REST", "https://db.example/rest/v1")
    monkeypatch.setattr(main, "PRIVATE_IMAGES_R2_ENABLED", True)
    monkeypatch.setattr(main, "private_image_url", lambda b, k, m: f"https://images.example/{b}/{k}")
    if visible:
        response = asyncio.run(main.sic_attachment_image(attachment_id, {"token": "test"}))
        assert response.body == payload
        assert response.headers["cache-control"] == "private, no-store"
        assert len(calls) == 2
    else:
        with pytest.raises(HTTPException) as failure:
            asyncio.run(main.sic_attachment_image(attachment_id, {"token": "test"}))
        assert failure.value.status_code == 404
        assert len(calls) == 1
