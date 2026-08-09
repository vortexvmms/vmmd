from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends

from .repository import ProjectRepository
from .schemas import ProjectCreate, ProjectUpdate
from .service import ProjectService


@dataclass(frozen=True)
class ProjectModuleContext:
    get_current_user: Callable
    shared_client: Callable
    rest_url: str
    supabase_headers: Callable
    audit: Callable


def build_projects_router(context: ProjectModuleContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

    def service(client, user):
        return ProjectService(ProjectRepository(
            client, context.rest_url, context.supabase_headers(user["token"])))

    @router.get("")
    async def list_projects(status: str | None = None,
                            user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await service(client, user).list(status)

    @router.get("/{project_id}")
    async def get_project(project_id: str,
                          user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            return await service(client, user).get(project_id)

    @router.post("", status_code=201)
    async def create_project(body: ProjectCreate,
                             user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            row = await service(client, user).create(body, user)
            await context.audit(client, user, "create", "project", row.get("id", ""), None, row)
            return row

    @router.patch("/{project_id}")
    async def update_project(project_id: str, body: ProjectUpdate,
                             user: dict = Depends(context.get_current_user)):
        async with context.shared_client() as client:
            old, row, changes = await service(client, user).update(project_id, body, user)
            await context.audit(client, user, "update", "project", project_id, old, changes)
            return row

    return router
