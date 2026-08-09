from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.modules.schedule.schemas import MasterResourceCreate, ResourceAssignmentCreate

def test_accepts_resource_categories_and_positive_assignment():
    for category in ("labour","equipment","material","subcontractor"):
        assert MasterResourceCreate(code="R1",name="Resource",category=category,unit="hour").category==category
    assert ResourceAssignmentCreate(project_id=uuid4(),activity_id=uuid4(),project_resource_id=uuid4(),planned_quantity=2,unit_rate=10).planned_quantity==2

@pytest.mark.parametrize("quantity",[0,-1])
def test_rejects_nonpositive_assignment_quantity(quantity):
    with pytest.raises(ValidationError): ResourceAssignmentCreate(project_id=uuid4(),activity_id=uuid4(),project_resource_id=uuid4(),planned_quantity=quantity,unit_rate=10)
