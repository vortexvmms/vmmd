import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.schedule.schemas import CalendarWorkweekUpdate
from app.modules.schedule.service import CalendarService


class FakeClient:
    def __init__(self, response): self.response, self.calls = response, []
    async def post(self, url, **kwargs): self.calls.append((url, kwargs)); return self.response


def standard_week():
    return CalendarWorkweekUpdate(rules=[{"day_of_week": d, "is_working": 1 <= d <= 5, "work_hours": 8 if 1 <= d <= 5 else 0} for d in range(7)])


def test_workweek_uses_one_atomic_rpc_call():
    client = FakeClient(SimpleNamespace(status_code=200, json=lambda: 7))
    service = CalendarService(client, "https://example.test/rest/v1", {})
    result = asyncio.run(service.update_workweek(str(uuid4()), standard_week(), {"role": "admin"}))
    assert result == {"updated": 7}
    assert client.calls[0][0].endswith("/rpc/set_calendar_workweek")
    assert len(client.calls[0][1]["json"]["p_rules"]) == 7


def test_workweek_denies_read_only_role():
    client = FakeClient(None)
    service = CalendarService(client, "https://example.test/rest/v1", {})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.update_workweek(str(uuid4()), standard_week(), {"role": "site_sup"}))
    assert exc.value.status_code == 403
    assert client.calls == []
