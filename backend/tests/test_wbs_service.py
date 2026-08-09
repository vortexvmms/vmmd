import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.schedule.schemas import WbsReorder
from app.modules.schedule.service import WbsService


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_reorder_uses_one_atomic_rpc_call():
    client = FakeClient(SimpleNamespace(status_code=200, json=lambda: 2))
    service = WbsService(client, "https://example.test/rest/v1", {"Authorization": "Bearer test"})
    project_id, first, second = uuid4(), uuid4(), uuid4()
    body = WbsReorder(project_id=project_id, items=[
        {"id": first, "parent_id": None, "sort_order": 1000},
        {"id": second, "parent_id": first, "sort_order": 1000},
    ])
    result = asyncio.run(service.reorder(body, {"role": "admin"}))
    assert result == {"updated": 2}
    assert len(client.calls) == 1
    url, kwargs = client.calls[0]
    assert url.endswith("/rpc/reorder_wbs_nodes")
    assert kwargs["json"]["p_project_id"] == str(project_id)
    assert len(kwargs["json"]["p_items"]) == 2


def test_reorder_denies_supervisor_before_database_call():
    client = FakeClient(None)
    service = WbsService(client, "https://example.test/rest/v1", {})
    body = WbsReorder(project_id=uuid4(), items=[{"id": uuid4(), "sort_order": 1000}])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.reorder(body, {"role": "site_sup"}))
    assert exc.value.status_code == 403
    assert client.calls == []
