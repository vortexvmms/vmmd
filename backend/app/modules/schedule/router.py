from fastapi import APIRouter, Depends


def build_schedule_router(get_current_user) -> APIRouter:
    router = APIRouter(prefix="/api/v1/schedule", tags=["schedule"])

    @router.get("/capabilities")
    async def schedule_capabilities(user: dict = Depends(get_current_user)):
        return {
            "foundation": "phase_0",
            "project_context_required": True,
            "implemented": [],
            "planned": ["wbs", "activities", "calendars", "logic", "resources", "baseline", "progress"],
        }

    return router
