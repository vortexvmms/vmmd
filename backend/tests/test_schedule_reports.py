import asyncio
from types import SimpleNamespace
from app.modules.schedule.service import ReportService

class FakeClient:
    def __init__(self,responses): self.responses=list(responses)
    async def get(self,url,**kwargs): return SimpleNamespace(status_code=200,json=lambda:self.responses.pop(0))

def test_project_controls_summary_and_filters():
    activities=[{"id":"a1","code":"A100","name":"Start","activity_type":"task","duration_days":4,"planned_start":"2026-09-01","planned_finish":"2026-09-04","early_start":"2026-09-01","early_finish":"2026-09-05","actual_start":"2026-09-01","actual_finish":None,"is_critical":True,"total_float":0,"status":"in_progress","percent_complete":50,"wbs_nodes":{"code":"1","name":"Works"}},{"id":"a2","code":"A200","name":"Finish","activity_type":"task","duration_days":2,"planned_start":"2026-09-06","planned_finish":"2026-09-07","early_start":"2026-09-06","early_finish":"2026-09-07","actual_start":None,"actual_finish":None,"is_critical":False,"total_float":2,"status":"not_started","percent_complete":0,"wbs_nodes":{"code":"1","name":"Works"}}]
    assignments=[{"activity_id":"a1","budgeted_cost":200},{"activity_id":"a1","budgeted_cost":50}]
    baselines=[{"id":"b1","name":"Original","data_date":"2026-09-01","created_at":"2026-09-01T00:00:00Z","baseline_activity_snapshots":[{"activity_id":"a1","early_finish":"2026-09-04"}]}]
    result=asyncio.run(ReportService(FakeClient([activities,assignments,baselines]),"https://example.test",{}).project_controls("p1","critical","2026-09-06",14))
    assert result["summary"]["total_activities"]==2 and result["summary"]["budgeted_cost"]==250
    assert result["summary"]["overall_percent"]==33.33
    assert len(result["rows"])==1 and result["rows"][0]["finish_variance_days"]==1
