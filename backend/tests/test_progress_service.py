import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.modules.schedule.schemas import ProgressUpdateCreate
from app.modules.schedule.service import ProgressService


class FakeClient:
    def __init__(self): self.calls=[]
    async def post(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return SimpleNamespace(status_code=200,json=lambda:"progress-id")


def test_record_progress_calls_secured_rpc_with_typed_payload():
    project_id,activity_id=uuid4(),uuid4();client=FakeClient()
    body=ProgressUpdateCreate(project_id=project_id,activity_id=activity_id,progress_date="2026-09-02",percent_complete=35,actual_start="2026-09-01",quantity_completed=12.5,remarks="DPR quantity")
    result=asyncio.run(ProgressService(client,"https://example.test/rest/v1",{}).record(body))
    assert result=={"progress_id":"progress-id"}
    url,call=client.calls[0]
    assert url.endswith("/rpc/record_activity_progress")
    assert call["json"]["p_project_id"]==str(project_id)
    assert call["json"]["p_activity_id"]==str(activity_id)
    assert call["json"]["p_percent_complete"]==35
