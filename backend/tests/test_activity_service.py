import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.schedule.schemas import ActivityCreate
from app.modules.schedule.service import ActivityService


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.responses.pop(0)

    async def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)


def response(status, rows):
    return SimpleNamespace(status_code=status, json=lambda: rows)


def test_create_resolves_schedule_from_selected_project_wbs():
    project_id, wbs_id, schedule_id, user_id = uuid4(), uuid4(), uuid4(), uuid4()
    client = FakeClient([response(200, [{"id": str(wbs_id), "project_id": str(project_id), "schedule_id": str(schedule_id)}]), response(201, [{"id": "activity-1"}])])
    service = ActivityService(client, "https://example.test/rest/v1", {})
    body = ActivityCreate(project_id=project_id, wbs_id=wbs_id, code=" a100 ", name="Mobilisation", duration_days=2, planned_start="2026-08-10", planned_finish="2026-08-11")
    result = asyncio.run(service.create(body, {"role": "admin", "user_id": str(user_id)}))
    assert result["id"] == "activity-1"
    posted = client.calls[1][2]["json"]
    assert posted["schedule_id"] == str(schedule_id)
    assert posted["code"] == "A100"


def test_create_denies_read_only_role_before_database_call():
    client = FakeClient([])
    service = ActivityService(client, "https://example.test/rest/v1", {})
    body = ActivityCreate(project_id=uuid4(), wbs_id=uuid4(), code="A100", name="Mobilisation", duration_days=1, planned_start="2026-08-10", planned_finish="2026-08-10")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create(body, {"role": "site_sup", "user_id": str(uuid4())}))
    assert exc.value.status_code == 403
    assert client.calls == []
