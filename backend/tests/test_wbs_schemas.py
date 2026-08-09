from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.schedule.schemas import WbsCreate, WbsReorder


def test_wbs_create_normal_contract():
    body = WbsCreate(project_id=uuid4(), code="1.1", name="Drainage")
    assert body.sort_order == 1000
    assert body.parent_id is None


def test_wbs_rejects_blank_name():
    with pytest.raises(ValidationError):
        WbsCreate(project_id=uuid4(), code="1", name="")


def test_reorder_requires_at_least_one_item():
    with pytest.raises(ValidationError):
        WbsReorder(project_id=uuid4(), items=[])
