from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends

from .schemas import ActivityCreate, ActivityUpdate, BaselineCreate, CalendarCreate, CalendarExceptionCreate, CalendarUpdate, CalendarWorkweekUpdate, MasterResourceCreate, ProjectResourceCreate, RelationshipCreate, RelationshipUpdate, ResourceAssignmentCreate, ResourceAssignmentUpdate, ScheduleCalculateRequest, WbsCreate, WbsReorder, WbsUpdate
from .service import ActivityService, CalculationService, CalendarService, RelationshipService, ResourceService, WbsService


@dataclass(frozen=True)
class ScheduleModuleContext:
    get_current_user: Callable
    shared_client: Callable
    rest_url: str
    supabase_headers: Callable


def build_schedule_router(context: ScheduleModuleContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/schedule", tags=["schedule"])

    def service(client, user):
        return WbsService(client, context.rest_url, context.supabase_headers(user["token"]))

    def activity_service(client, user):
        return ActivityService(client, context.rest_url, context.supabase_headers(user["token"]))

    def relationship_service(client, user):
        return RelationshipService(client, context.rest_url, context.supabase_headers(user["token"]))

    def calendar_service(client, user):
        return CalendarService(client, context.rest_url, context.supabase_headers(user["token"]))

    def resource_service(client, user):
        return ResourceService(client, context.rest_url, context.supabase_headers(user["token"]))

    def calculation_service(client, user):
        return CalculationService(client, context.rest_url, context.supabase_headers(user["token"]))

    @router.get("/capabilities")
    async def capabilities(user: dict = Depends(context.get_current_user)):
        return {"foundation": "phase_1", "project_context_required": True, "implemented": ["wbs", "activities", "milestones", "logic", "calendars", "resources", "resource_assignments", "calculation", "gantt", "baselines"], "planned": ["progress"]}

    @router.get("/wbs")
    async def list_wbs(project_id: str, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await service(client, user).list(project_id)

    @router.post("/wbs", status_code=201)
    async def create_wbs(body: WbsCreate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await service(client, user).create(body, user)

    @router.patch("/wbs/{node_id}")
    async def update_wbs(node_id: str, body: WbsUpdate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await service(client, user).update(node_id, body, user)

    @router.post("/wbs/reorder")
    async def reorder_wbs(body: WbsReorder, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await service(client, user).reorder(body, user)

    @router.get("/activities")
    async def list_activities(project_id: str, wbs_id: str | None = None, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await activity_service(client, user).list(project_id, wbs_id)

    @router.post("/activities", status_code=201)
    async def create_activity(body: ActivityCreate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await activity_service(client, user).create(body, user)

    @router.patch("/activities/{activity_id}")
    async def update_activity(activity_id: str, body: ActivityUpdate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await activity_service(client, user).update(activity_id, body, user)

    @router.get("/relationships")
    async def list_relationships(project_id: str, activity_id: str | None = None, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await relationship_service(client, user).list(project_id, activity_id)

    @router.post("/relationships", status_code=201)
    async def create_relationship(body: RelationshipCreate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await relationship_service(client, user).create(body, user)

    @router.patch("/relationships/{relationship_id}")
    async def update_relationship(relationship_id: str, body: RelationshipUpdate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await relationship_service(client, user).update(relationship_id, body, user)

    @router.get("/calendars")
    async def list_calendars(project_id: str, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await calendar_service(client, user).list(project_id)

    @router.post("/calendars", status_code=201)
    async def create_calendar(body: CalendarCreate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await calendar_service(client, user).create(body, user)

    @router.patch("/calendars/{calendar_id}")
    async def update_calendar(calendar_id: str, body: CalendarUpdate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await calendar_service(client, user).update(calendar_id, body, user)

    @router.put("/calendars/{calendar_id}/workweek")
    async def update_workweek(calendar_id: str, body: CalendarWorkweekUpdate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await calendar_service(client, user).update_workweek(calendar_id, body, user)

    @router.post("/calendars/{calendar_id}/exceptions", status_code=201)
    async def create_calendar_exception(calendar_id: str, body: CalendarExceptionCreate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await calendar_service(client, user).create_exception(calendar_id, body, user)

    @router.get("/resources")
    async def list_resources(project_id: str, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await resource_service(client, user).list(project_id)

    @router.post("/resources/master", status_code=201)
    async def create_master_resource(body: MasterResourceCreate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await resource_service(client, user).create_master(body, user)

    @router.post("/resources/project", status_code=201)
    async def import_project_resource(body: ProjectResourceCreate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await resource_service(client, user).import_project(body, user)

    @router.post("/resources/assignments", status_code=201)
    async def create_resource_assignment(body: ResourceAssignmentCreate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await resource_service(client, user).assign(body, user)

    @router.patch("/resources/assignments/{assignment_id}")
    async def update_resource_assignment(assignment_id: str, body: ResourceAssignmentUpdate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await resource_service(client, user).update_assignment(assignment_id, body, user)

    @router.post("/calculate")
    async def calculate(body: ScheduleCalculateRequest, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client: return await calculation_service(client,user).calculate(str(body.project_id),user)

    @router.get("/baselines")
    async def list_baselines(project_id: str, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client: return await calculation_service(client,user).list_baselines(project_id)

    @router.post("/baselines",status_code=201)
    async def create_baseline(body: BaselineCreate, user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client: return await calculation_service(client,user).create_baseline(body,user)

    return router
