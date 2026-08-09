from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends

from .schemas import WbsCreate, WbsReorder, WbsUpdate
from .service import WbsService


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

    @router.get("/capabilities")
    async def capabilities(user: dict = Depends(context.get_current_user)):
        return {"foundation": "phase_1", "project_context_required": True, "implemented": ["wbs"], "planned": ["activities", "calendars", "logic", "resources", "baseline", "progress"]}

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

    return router
