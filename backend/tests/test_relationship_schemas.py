from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.schedule.schemas import RelationshipCreate


def test_accepts_all_relationship_types_and_signed_lag():
    for kind in ("FS", "SS", "FF", "SF"):
        item = RelationshipCreate(project_id=uuid4(), predecessor_id=uuid4(), successor_id=uuid4(), relationship_type=kind, lag_days=-2)
        assert item.relationship_type == kind
        assert item.lag_days == -2


def test_rejects_self_relationship():
    activity_id = uuid4()
    with pytest.raises(ValidationError):
        RelationshipCreate(project_id=uuid4(), predecessor_id=activity_id, successor_id=activity_id)


@pytest.mark.parametrize("lag", [-3651, 3651])
def test_rejects_excessive_lead_or_lag(lag):
    with pytest.raises(ValidationError):
        RelationshipCreate(project_id=uuid4(), predecessor_id=uuid4(), successor_id=uuid4(), lag_days=lag)
