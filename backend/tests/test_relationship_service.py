import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.schedule.schemas import RelationshipCreate
from app.modules.schedule.service import RelationshipService


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    async def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.responses.pop(0)

    async def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)


def response(status, rows):
    return SimpleNamespace(status_code=status, json=lambda: rows)


def test_create_resolves_both_activities_before_posting_relationship():
    project, schedule, predecessor, successor, user = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    activity = {"project_id": str(project), "schedule_id": str(schedule)}
    client = FakeClient([response(200, [{"id": str(predecessor), **activity}]), response(200, [{"id": str(successor), **activity}]), response(201, [{"id": "logic-1"}])])
    service = RelationshipService(client, "https://example.test/rest/v1", {})
    body = RelationshipCreate(project_id=project, predecessor_id=predecessor, successor_id=successor, relationship_type="SS", lag_days=-1)
    assert asyncio.run(service.create(body, {"role": "admin", "user_id": str(user)}))["id"] == "logic-1"
    assert client.calls[-1][2]["json"]["schedule_id"] == str(schedule)
    assert client.calls[-1][2]["json"]["relationship_type"] == "SS"


def test_create_denies_read_only_role_without_database_call():
    client = FakeClient([])
    service = RelationshipService(client, "https://example.test/rest/v1", {})
    body = RelationshipCreate(project_id=uuid4(), predecessor_id=uuid4(), successor_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create(body, {"role": "site_sup", "user_id": str(uuid4())}))
    assert exc.value.status_code == 403
    assert client.calls == []
