from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.roles import can_administer_projects


class ProjectService:
    def __init__(self, repository):
        self.repository = repository

    @staticmethod
    def require_admin(user: dict):
        if not can_administer_projects(user.get("role", "")):
            raise HTTPException(status_code=403, detail="Not allowed to administer projects")

    async def list(self, status: str | None):
        if status and status not in {"draft", "active", "on_hold", "completed", "archived"}:
            raise HTTPException(status_code=400, detail="Invalid project status")
        response = await self.repository.list(status)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load projects")
        return response.json()

    async def get(self, project_id: str):
        response = await self.repository.get(project_id)
        rows = response.json() if response.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=404, detail="Project not found or not accessible")
        return rows[0]

    async def create(self, body, user: dict):
        self.require_admin(user)
        values = body.model_dump(mode="json")
        values["project_code"] = body.project_code.strip().upper()
        values["project_name"] = body.project_name.strip()
        values["created_by"] = user["user_id"]
        response = await self.repository.create(values)
        if response.status_code == 409:
            raise HTTPException(status_code=409, detail="Project code already exists")
        if response.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail="Could not create project")
        rows = response.json()
        return rows[0] if rows else values

    async def update(self, project_id: str, body, user: dict):
        self.require_admin(user)
        current = await self.get(project_id)
        values = body.model_dump(exclude_unset=True, mode="json")
        if not values:
            raise HTTPException(status_code=400, detail="Nothing to update")
        planned_start = values.get("planned_start_date", current.get("planned_start_date"))
        planned_finish = values.get("planned_finish_date", current.get("planned_finish_date"))
        actual_start = values.get("actual_start_date", current.get("actual_start_date"))
        actual_finish = values.get("actual_finish_date", current.get("actual_finish_date"))
        if planned_start and planned_finish and planned_finish < planned_start:
            raise HTTPException(status_code=400, detail="planned_finish_date cannot be before planned_start_date")
        if actual_start and actual_finish and actual_finish < actual_start:
            raise HTTPException(status_code=400, detail="actual_finish_date cannot be before actual_start_date")
        if values.get("status") == "archived":
            values["archived_at"] = datetime.now(timezone.utc).isoformat()
        elif "status" in values:
            values["archived_at"] = None
        response = await self.repository.update(project_id, values)
        rows = response.json() if response.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=500, detail="Could not update project")
        return current, rows[0], values
