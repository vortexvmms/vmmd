from datetime import date
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.modules.schedule.schemas import ProgressUpdateCreate

def test_manual_progress_accepts_valid_actual_dates():
    item=ProgressUpdateCreate(project_id=uuid4(),activity_id=uuid4(),progress_date=date(2026,9,1),percent_complete=50,actual_start=date(2026,9,1))
    assert item.source=="manual" and item.percent_complete==50

def test_progress_rejects_finish_before_100_percent():
    with pytest.raises(ValidationError):
        ProgressUpdateCreate(project_id=uuid4(),activity_id=uuid4(),progress_date=date(2026,9,2),percent_complete=80,actual_start=date(2026,9,1),actual_finish=date(2026,9,2))

def test_dpr_progress_requires_report_reference():
    with pytest.raises(ValidationError):
        ProgressUpdateCreate(project_id=uuid4(),activity_id=uuid4(),progress_date=date(2026,9,2),percent_complete=20,source="dpr")
