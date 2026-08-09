from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.roles import can_administer_projects


class WbsService:
    SELECT = "id,project_id,schedule_id,parent_id,code,name,description,sort_order,depth,is_active,created_at,updated_at"

    def __init__(self, client, rest_url: str, headers: dict):
        self.client, self.rest, self.headers = client, rest_url, headers

    @staticmethod
    def require_editor(user: dict):
        if not can_administer_projects(user.get("role", "")):
            raise HTTPException(status_code=403, detail="Not allowed to edit the WBS")

    async def schedule(self, project_id: str, user: dict, create: bool = False):
        r = await self.client.get(f"{self.rest}/schedules", params={"project_id": f"eq.{project_id}", "select": "*", "limit": "1"}, headers=self.headers)
        rows = r.json() if r.status_code == 200 else []
        if rows or not create:
            return rows[0] if rows else None
        self.require_editor(user)
        r = await self.client.post(f"{self.rest}/schedules", headers={**self.headers, "Prefer": "return=representation"}, json={"project_id": project_id, "created_by": user["user_id"], "updated_by": user["user_id"]})
        rows = r.json() if r.status_code in (200, 201) else []
        if not rows:
            raise HTTPException(status_code=500, detail="Could not create project schedule")
        return rows[0]

    async def list(self, project_id: str):
        schedule = await self.schedule(project_id, {}, False)
        if not schedule:
            return {"schedule": None, "nodes": []}
        r = await self.client.get(f"{self.rest}/wbs_nodes", params={"project_id": f"eq.{project_id}", "is_active": "eq.true", "select": self.SELECT, "order": "sort_order.asc,code.asc"}, headers=self.headers)
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load WBS")
        return {"schedule": schedule, "nodes": r.json()}

    async def create(self, body, user: dict):
        self.require_editor(user)
        project_id = str(body.project_id)
        schedule = await self.schedule(project_id, user, True)
        values = body.model_dump(mode="json")
        values.update(schedule_id=schedule["id"], code=body.code.strip().upper(), name=body.name.strip(), created_by=user["user_id"], updated_by=user["user_id"])
        r = await self.client.post(f"{self.rest}/wbs_nodes", headers={**self.headers, "Prefer": "return=representation"}, json=values)
        if r.status_code == 409:
            raise HTTPException(status_code=409, detail="WBS code already exists in this schedule")
        rows = r.json() if r.status_code in (200, 201) else []
        if not rows:
            raise HTTPException(status_code=400, detail="Could not create WBS node")
        return rows[0]

    async def update(self, node_id: str, body, user: dict):
        self.require_editor(user)
        values = body.model_dump(exclude_unset=True, mode="json")
        if not values:
            raise HTTPException(status_code=400, detail="Nothing to update")
        if "code" in values: values["code"] = values["code"].strip().upper()
        if "name" in values: values["name"] = values["name"].strip()
        if values.get("is_active") is False:
            values["archived_at"] = datetime.now(timezone.utc).isoformat()
        elif values.get("is_active") is True:
            values["archived_at"] = None
        values["updated_by"] = user["user_id"]
        r = await self.client.patch(f"{self.rest}/wbs_nodes", params={"id": f"eq.{node_id}"}, headers={**self.headers, "Prefer": "return=representation"}, json=values)
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=404, detail="WBS node not found or update rejected")
        return rows[0]

    async def reorder(self, body, user: dict):
        self.require_editor(user)
        items = [item.model_dump(mode="json") for item in body.items]
        r = await self.client.post(
            f"{self.rest}/rpc/reorder_wbs_nodes",
            headers=self.headers,
            json={"p_project_id": str(body.project_id), "p_items": items},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not save WBS order")
        return {"updated": r.json()}
