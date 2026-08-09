import pytest
from app.modules.schedule.scheduler import calculate_schedule

CAL=[{"id":"cal"}]
WEEK=[{"calendar_id":"cal","day_of_week":d,"is_working":1<=d<=5} for d in range(7)]

def activity(identifier,start,duration=1):
    return {"id":identifier,"calendar_id":"cal","planned_start":start,"duration_days":duration}

def test_fs_relationship_skips_weekend_and_marks_chain_critical():
    result=calculate_schedule([activity("a","2026-08-14"),activity("b","2026-08-14")],[{"predecessor_id":"a","successor_id":"b","relationship_type":"FS","lag_days":0}],CAL,WEEK,[])
    assert result["a"]["early_finish"]=="2026-08-14"
    assert result["b"]["early_start"]=="2026-08-17"
    assert result["a"]["is_critical"] and result["b"]["is_critical"]

def test_exception_pushes_successor_to_next_working_day():
    result=calculate_schedule([activity("a","2026-08-17"),activity("b","2026-08-17")],[{"predecessor_id":"a","successor_id":"b","relationship_type":"FS","lag_days":0}],CAL,WEEK,[{"calendar_id":"cal","exception_date":"2026-08-18","is_working":False}])
    assert result["b"]["early_start"]=="2026-08-19"

def test_cycle_is_rejected():
    rels=[{"predecessor_id":"a","successor_id":"b","relationship_type":"FS","lag_days":0},{"predecessor_id":"b","successor_id":"a","relationship_type":"FS","lag_days":0}]
    with pytest.raises(ValueError): calculate_schedule([activity("a","2026-08-17"),activity("b","2026-08-17")],rels,CAL,WEEK,[])
