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


class ActivityService:
    SELECT = "id,project_id,schedule_id,wbs_id,calendar_id,code,name,description,activity_type,duration_days,planned_start,planned_finish,status,percent_complete,sort_order,is_active,created_at,updated_at"

    def __init__(self, client, rest_url: str, headers: dict):
        self.client, self.rest, self.headers = client, rest_url, headers

    @staticmethod
    def require_editor(user: dict):
        if not can_administer_projects(user.get("role", "")):
            raise HTTPException(status_code=403, detail="Not allowed to edit activities")

    async def list(self, project_id: str, wbs_id: str | None = None):
        params = {"project_id": f"eq.{project_id}", "is_active": "eq.true", "select": self.SELECT, "order": "sort_order.asc,code.asc"}
        if wbs_id:
            params["wbs_id"] = f"eq.{wbs_id}"
        r = await self.client.get(f"{self.rest}/schedule_activities", params=params, headers=self.headers)
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load activities")
        return {"activities": r.json()}

    async def _wbs(self, wbs_id: str, project_id: str):
        r = await self.client.get(f"{self.rest}/wbs_nodes", params={"id": f"eq.{wbs_id}", "project_id": f"eq.{project_id}", "is_active": "eq.true", "select": "id,project_id,schedule_id", "limit": "1"}, headers=self.headers)
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=400, detail="Select an active WBS node from this project")
        return rows[0]


    @staticmethod
    def _validate(values: dict):
        start, finish = values.get("planned_start"), values.get("planned_finish")
        if start and finish and finish < start:
            raise HTTPException(status_code=422, detail="Planned finish cannot be before planned start")
        if values.get("activity_type") == "milestone":
            if values.get("duration_days") != 0 or start != finish:
                raise HTTPException(status_code=422, detail="A milestone must have zero duration and one planned date")
        elif values.get("duration_days", 0) < 1:
            raise HTTPException(status_code=422, detail="A task must have a duration of at least one day")

    async def create(self, body, user: dict):
        self.require_editor(user)
        project_id = str(body.project_id)
        wbs = await self._wbs(str(body.wbs_id), project_id)
        values = body.model_dump(mode="json")
        values.update(schedule_id=wbs["schedule_id"], code=body.code.strip().upper(), name=body.name.strip(), created_by=user["user_id"], updated_by=user["user_id"])
        r = await self.client.post(f"{self.rest}/schedule_activities", headers={**self.headers, "Prefer": "return=representation"}, json=values)
        if r.status_code == 409:
            raise HTTPException(status_code=409, detail="Activity code already exists in this schedule")
        rows = r.json() if r.status_code in (200, 201) else []
        if not rows:
            raise HTTPException(status_code=400, detail="Could not create activity")
        return rows[0]

    async def update(self, activity_id: str, body, user: dict):
        self.require_editor(user)
        current_response = await self.client.get(f"{self.rest}/schedule_activities", params={"id": f"eq.{activity_id}", "select": self.SELECT, "limit": "1"}, headers=self.headers)
        rows = current_response.json() if current_response.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=404, detail="Activity not found")
        current = rows[0]
        values = body.model_dump(exclude_unset=True, mode="json")
        if not values:
            raise HTTPException(status_code=400, detail="Nothing to update")
        if "wbs_id" in values:
            wbs = await self._wbs(values["wbs_id"], current["project_id"])
            values["schedule_id"] = wbs["schedule_id"]
        if "code" in values: values["code"] = values["code"].strip().upper()
        if "name" in values: values["name"] = values["name"].strip()
        merged = {**current, **values}
        self._validate(merged)
        if values.get("is_active") is False:
            values["archived_at"] = datetime.now(timezone.utc).isoformat()
        elif values.get("is_active") is True:
            values["archived_at"] = None
        values["updated_by"] = user["user_id"]
        r = await self.client.patch(f"{self.rest}/schedule_activities", params={"id": f"eq.{activity_id}"}, headers={**self.headers, "Prefer": "return=representation"}, json=values)
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=400, detail="Could not update activity")
        return rows[0]


class RelationshipService:
    SELECT = "id,project_id,schedule_id,predecessor_id,successor_id,relationship_type,lag_days,is_active,created_at,updated_at"

    def __init__(self, client, rest_url: str, headers: dict):
        self.client, self.rest, self.headers = client, rest_url, headers

    @staticmethod
    def require_editor(user: dict):
        if not can_administer_projects(user.get("role", "")):
            raise HTTPException(status_code=403, detail="Not allowed to edit activity logic")

    async def list(self, project_id: str, activity_id: str | None = None):
        params = {"project_id": f"eq.{project_id}", "is_active": "eq.true", "select": self.SELECT, "order": "created_at.asc"}
        if activity_id:
            params["or"] = f"(predecessor_id.eq.{activity_id},successor_id.eq.{activity_id})"
        r = await self.client.get(f"{self.rest}/activity_relationships", params=params, headers=self.headers)
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load activity logic")
        return {"relationships": r.json()}

    async def _activity(self, activity_id: str, project_id: str):
        r = await self.client.get(f"{self.rest}/schedule_activities", params={"id": f"eq.{activity_id}", "project_id": f"eq.{project_id}", "is_active": "eq.true", "select": "id,project_id,schedule_id", "limit": "1"}, headers=self.headers)
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=400, detail="Select active activities from this project")
        return rows[0]


    async def create(self, body, user: dict):
        self.require_editor(user)
        project_id = str(body.project_id)
        predecessor = await self._activity(str(body.predecessor_id), project_id)
        successor = await self._activity(str(body.successor_id), project_id)
        if predecessor["schedule_id"] != successor["schedule_id"]:
            raise HTTPException(status_code=400, detail="Activities must belong to the same schedule")
        values = body.model_dump(mode="json")
        values.update(schedule_id=predecessor["schedule_id"], created_by=user["user_id"], updated_by=user["user_id"])
        r = await self.client.post(f"{self.rest}/activity_relationships", headers={**self.headers, "Prefer": "return=representation"}, json=values)
        if r.status_code == 409:
            raise HTTPException(status_code=409, detail="This activity relationship already exists")
        rows = r.json() if r.status_code in (200, 201) else []
        if not rows:
            raise HTTPException(status_code=400, detail="Relationship rejected; check for circular logic")
        return rows[0]

    async def update(self, relationship_id: str, body, user: dict):
        self.require_editor(user)
        values = body.model_dump(exclude_unset=True, mode="json")
        if not values:
            raise HTTPException(status_code=400, detail="Nothing to update")
        if values.get("is_active") is False:
            values["archived_at"] = datetime.now(timezone.utc).isoformat()
        elif values.get("is_active") is True:
            values["archived_at"] = None
        values["updated_by"] = user["user_id"]
        r = await self.client.patch(f"{self.rest}/activity_relationships", params={"id": f"eq.{relationship_id}"}, headers={**self.headers, "Prefer": "return=representation"}, json=values)
        rows = r.json() if r.status_code == 200 else []
        if not rows:
            raise HTTPException(status_code=404, detail="Activity relationship not found")
        return rows[0]


class CalendarService:
    SELECT = "id,project_id,name,hours_per_day,is_default,is_active,created_at,updated_at,calendar_workweek(day_of_week,is_working,work_hours),calendar_exceptions(id,exception_date,name,is_working,work_hours)"

    def __init__(self, client, rest_url: str, headers: dict):
        self.client, self.rest, self.headers = client, rest_url, headers

    @staticmethod
    def require_editor(user: dict):
        if not can_administer_projects(user.get("role", "")):
            raise HTTPException(status_code=403, detail="Not allowed to edit project calendars")

    async def list(self, project_id: str):
        r = await self.client.get(f"{self.rest}/schedule_calendars", params={"project_id": f"eq.{project_id}", "is_active": "eq.true", "select": self.SELECT, "order": "is_default.desc,name.asc"}, headers=self.headers)
        if r.status_code != 200: raise HTTPException(status_code=500, detail="Could not load project calendars")
        return {"calendars": r.json()}

    async def create(self, body, user: dict):
        self.require_editor(user)
        values = body.model_dump(mode="json")
        values.update(name=body.name.strip(), created_by=user["user_id"], updated_by=user["user_id"])
        r = await self.client.post(f"{self.rest}/schedule_calendars", headers={**self.headers, "Prefer": "return=representation"}, json=values)
        rows = r.json() if r.status_code in (200, 201) else []
        if not rows: raise HTTPException(status_code=400, detail="Could not create project calendar")
        return rows[0]

    async def update(self, calendar_id: str, body, user: dict):
        self.require_editor(user)
        values = body.model_dump(exclude_unset=True, mode="json")
        if not values: raise HTTPException(status_code=400, detail="Nothing to update")
        if "name" in values: values["name"] = values["name"].strip()
        if values.get("is_active") is False: values["archived_at"] = datetime.now(timezone.utc).isoformat()
        values["updated_by"] = user["user_id"]
        r = await self.client.patch(f"{self.rest}/schedule_calendars", params={"id": f"eq.{calendar_id}"}, headers={**self.headers, "Prefer": "return=representation"}, json=values)
        rows = r.json() if r.status_code == 200 else []
        if not rows: raise HTTPException(status_code=404, detail="Project calendar not found")
        return rows[0]

    async def update_workweek(self, calendar_id: str, body, user: dict):
        self.require_editor(user)
        r = await self.client.post(f"{self.rest}/rpc/set_calendar_workweek", headers=self.headers, json={"p_calendar_id": calendar_id, "p_rules": [rule.model_dump(mode="json") for rule in body.rules]})
        if r.status_code != 200: raise HTTPException(status_code=400, detail="Could not save working-day rules")
        return {"updated": r.json()}

    async def create_exception(self, calendar_id: str, body, user: dict):
        self.require_editor(user)
        calendar_response = await self.client.get(f"{self.rest}/schedule_calendars", params={"id": f"eq.{calendar_id}", "is_active": "eq.true", "select": "id,project_id", "limit": "1"}, headers=self.headers)
        calendars = calendar_response.json() if calendar_response.status_code == 200 else []
        if not calendars: raise HTTPException(status_code=404, detail="Project calendar not found")
        values = body.model_dump(mode="json")
        values.update(calendar_id=calendar_id, project_id=calendars[0]["project_id"], created_by=user["user_id"], updated_by=user["user_id"])
        r = await self.client.post(f"{self.rest}/calendar_exceptions", headers={**self.headers, "Prefer": "return=representation"}, json=values)
        rows = r.json() if r.status_code in (200, 201) else []
        if not rows: raise HTTPException(status_code=400, detail="Could not add calendar exception")
        return rows[0]
