from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

from app.core.roles import can_administer_projects
from .scheduler import calculate_schedule


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
    SELECT = "id,project_id,schedule_id,wbs_id,calendar_id,code,name,description,activity_type,duration_days,planned_start,planned_finish,early_start,early_finish,late_start,late_finish,total_float,is_critical,calculated_at,actual_start,actual_finish,status,percent_complete,sort_order,is_active,created_at,updated_at"

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


class ResourceService:
    def __init__(self, client, rest_url: str, headers: dict):
        self.client, self.rest, self.headers = client, rest_url, headers

    @staticmethod
    def require_editor(user: dict):
        if not can_administer_projects(user.get("role", "")): raise HTTPException(status_code=403, detail="Not allowed to edit resources")

    async def list(self, project_id: str):
        common = {"headers": self.headers}
        master = await self.client.get(f"{self.rest}/resource_master_library", params={"is_active":"eq.true","select":"id,code,name,category,classification,unit,standard_rate","order":"category.asc,code.asc"}, **common)
        project = await self.client.get(f"{self.rest}/project_resources", params={"project_id":f"eq.{project_id}","is_active":"eq.true","select":"id,project_id,master_resource_id,project_rate,is_active","order":"created_at.asc"}, **common)
        assignments = await self.client.get(f"{self.rest}/activity_resource_assignments", params={"project_id":f"eq.{project_id}","is_active":"eq.true","select":"id,project_id,schedule_id,activity_id,project_resource_id,planned_quantity,unit_rate,budgeted_cost,is_active","order":"created_at.asc"}, **common)
        if any(r.status_code != 200 for r in (master,project,assignments)): raise HTTPException(status_code=500, detail="Could not load resources")
        return {"master_resources":master.json(),"project_resources":project.json(),"assignments":assignments.json()}

    async def create_master(self, body, user: dict):
        self.require_editor(user); values=body.model_dump(mode="json"); values.update(code=body.code.strip().upper(),name=body.name.strip(),unit=body.unit.strip(),created_by=user["user_id"],updated_by=user["user_id"])
        r=await self.client.post(f"{self.rest}/resource_master_library",headers={**self.headers,"Prefer":"return=representation"},json=values); rows=r.json() if r.status_code in(200,201) else []
        if not rows: raise HTTPException(status_code=409 if r.status_code==409 else 400,detail="Could not create master resource")
        return rows[0]


    async def import_project(self, body, user: dict):
        self.require_editor(user); values=body.model_dump(mode="json"); values.update(created_by=user["user_id"],updated_by=user["user_id"])
        r=await self.client.post(f"{self.rest}/project_resources",headers={**self.headers,"Prefer":"return=representation"},json=values); rows=r.json() if r.status_code in(200,201) else []
        if not rows: raise HTTPException(status_code=409 if r.status_code==409 else 400,detail="Could not import resource into project")
        return rows[0]

    async def assign(self, body, user: dict):
        self.require_editor(user); activity=await self.client.get(f"{self.rest}/schedule_activities",params={"id":f"eq.{body.activity_id}","project_id":f"eq.{body.project_id}","is_active":"eq.true","select":"id,schedule_id","limit":"1"},headers=self.headers); rows=activity.json() if activity.status_code==200 else []
        if not rows: raise HTTPException(status_code=400,detail="Select an active activity from this project")
        values=body.model_dump(mode="json"); values.update(schedule_id=rows[0]["schedule_id"],created_by=user["user_id"],updated_by=user["user_id"])
        r=await self.client.post(f"{self.rest}/activity_resource_assignments",headers={**self.headers,"Prefer":"return=representation"},json=values); result=r.json() if r.status_code in(200,201) else []
        if not result: raise HTTPException(status_code=409 if r.status_code==409 else 400,detail="Could not assign resource to activity")
        return result[0]

    async def update_assignment(self, assignment_id: str, body, user: dict):
        self.require_editor(user); values=body.model_dump(exclude_unset=True,mode="json")
        if not values: raise HTTPException(status_code=400,detail="Nothing to update")
        if values.get("is_active") is False: values["archived_at"]=datetime.now(timezone.utc).isoformat()
        values["updated_by"]=user["user_id"]
        r=await self.client.patch(f"{self.rest}/activity_resource_assignments",params={"id":f"eq.{assignment_id}"},headers={**self.headers,"Prefer":"return=representation"},json=values); rows=r.json() if r.status_code==200 else []
        if not rows: raise HTTPException(status_code=404,detail="Resource assignment not found")
        return rows[0]


class CalculationService:
    def __init__(self, client, rest_url: str, headers: dict): self.client,self.rest,self.headers=client,rest_url,headers
    @staticmethod
    def require_editor(user):
        if not can_administer_projects(user.get("role","")): raise HTTPException(status_code=403,detail="Not allowed to calculate schedules")
    async def calculate(self, project_id: str, user: dict):
        self.require_editor(user)
        async def get(table,params):
            r=await self.client.get(f"{self.rest}/{table}",params=params,headers=self.headers)
            if r.status_code!=200: raise HTTPException(status_code=500,detail=f"Could not load {table}")
            return r.json()
        activities=await get("schedule_activities",{"project_id":f"eq.{project_id}","is_active":"eq.true","select":ActivityService.SELECT,"order":"sort_order.asc,code.asc"})
        relationships=await get("activity_relationships",{"project_id":f"eq.{project_id}","is_active":"eq.true","select":"*"})
        calendars=await get("schedule_calendars",{"project_id":f"eq.{project_id}","is_active":"eq.true","select":"id"})
        ids=",".join(c["id"] for c in calendars)
        workweeks=await get("calendar_workweek",{"calendar_id":f"in.({ids})","select":"calendar_id,day_of_week,is_working,work_hours"}) if ids else []
        exceptions=await get("calendar_exceptions",{"project_id":f"eq.{project_id}","select":"calendar_id,exception_date,is_working"})
        try: result=calculate_schedule(activities,relationships,calendars,workweeks,exceptions)
        except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc
        now=datetime.now(timezone.utc).isoformat()
        for activity_id,values in result.items():
            values["calculated_at"]=now
            r=await self.client.patch(f"{self.rest}/schedule_activities",params={"id":f"eq.{activity_id}"},headers=self.headers,json=values)
            if r.status_code not in(200,204): raise HTTPException(status_code=500,detail="Could not save calculated dates")
        await self.client.patch(f"{self.rest}/schedules",params={"project_id":f"eq.{project_id}"},headers=self.headers,json={"last_calculated_at":now,"updated_by":user["user_id"]})
        return {"calculated":len(result),"activities":result,"calculated_at":now}
    async def list_baselines(self, project_id: str):
        r=await self.client.get(f"{self.rest}/schedule_baselines",params={"project_id":f"eq.{project_id}","select":"id,project_id,schedule_id,name,description,data_date,status,created_at,baseline_activity_snapshots(*)","order":"created_at.desc"},headers=self.headers)
        if r.status_code!=200: raise HTTPException(status_code=500,detail="Could not load baselines")
        return {"baselines":r.json()}
    async def create_baseline(self, body, user: dict):
        self.require_editor(user)
        r=await self.client.post(f"{self.rest}/rpc/create_schedule_baseline",headers=self.headers,json={"p_project_id":str(body.project_id),"p_name":body.name.strip(),"p_description":body.description,"p_data_date":body.data_date.isoformat()})
        if r.status_code!=200: raise HTTPException(status_code=400,detail="Could not create baseline; calculate the schedule and use a unique name")
        return {"baseline_id":r.json()}


class ProgressService:
    SELECT="id,project_id,schedule_id,activity_id,progress_date,percent_complete,actual_start,actual_finish,quantity_completed,remarks,source,dpr_report_id,created_by,created_at,updated_at"
    def __init__(self,client,rest_url: str,headers: dict): self.client,self.rest,self.headers=client,rest_url,headers
    async def list(self,project_id: str,activity_id: str|None=None):
        params={"project_id":f"eq.{project_id}","select":self.SELECT,"order":"progress_date.desc,updated_at.desc"}
        if activity_id: params["activity_id"]=f"eq.{activity_id}"
        r=await self.client.get(f"{self.rest}/activity_progress_updates",params=params,headers=self.headers)
        if r.status_code!=200: raise HTTPException(status_code=500,detail="Could not load activity progress")
        return {"progress":r.json()}
    async def record(self,body):
        values=body.model_dump(mode="json")
        r=await self.client.post(f"{self.rest}/rpc/record_activity_progress",headers=self.headers,json={f"p_{key}":value for key,value in values.items()})
        if r.status_code!=200: raise HTTPException(status_code=400,detail="Could not save activity progress")
        return {"progress_id":r.json()}


class ReportService:
    TYPES={"summary","lookahead","critical","progress","overdue","variance","resources"}
    def __init__(self,client,rest_url: str,headers: dict): self.client,self.rest,self.headers=client,rest_url,headers
    async def _get(self,table,params):
        r=await self.client.get(f"{self.rest}/{table}",params=params,headers=self.headers)
        if r.status_code!=200: raise HTTPException(status_code=500,detail=f"Could not load report {table}")
        return r.json()
    async def project_controls(self,project_id: str,report_type: str,data_date: str|None,lookahead_days: int):
        if report_type not in self.TYPES: raise HTTPException(status_code=400,detail="Unknown project-controls report")
        if lookahead_days<1 or lookahead_days>90: raise HTTPException(status_code=400,detail="Lookahead must be between 1 and 90 days")
        try: as_of=date.fromisoformat(data_date) if data_date else date.today()
        except ValueError as exc: raise HTTPException(status_code=400,detail="Invalid report data date") from exc
        activities=await self._get("schedule_activities",{"project_id":f"eq.{project_id}","is_active":"eq.true","select":ActivityService.SELECT+",wbs_nodes(code,name)","order":"sort_order.asc,code.asc"})
        assignments=await self._get("activity_resource_assignments",{"project_id":f"eq.{project_id}","is_active":"eq.true","select":"activity_id,budgeted_cost"})
        baselines=await self._get("schedule_baselines",{"project_id":f"eq.{project_id}","status":"eq.active","select":"id,name,data_date,created_at,baseline_activity_snapshots(activity_id,early_finish)","order":"created_at.desc","limit":"1"})
        costs={}
        for item in assignments: costs[item["activity_id"]]=costs.get(item["activity_id"],0)+float(item.get("budgeted_cost") or 0)
        baseline=baselines[0] if baselines else None; baseline_dates={}
        if baseline:
            for snap in baseline.get("baseline_activity_snapshots") or []: baseline_dates[snap["activity_id"]]=snap.get("early_finish")
        rows=[]
        for a in activities:
            current_start=a.get("early_start") or a["planned_start"]; current_finish=a.get("early_finish") or a["planned_finish"]
            finish_date=date.fromisoformat(current_finish); base_finish=baseline_dates.get(a["id"])
            variance=(finish_date-date.fromisoformat(base_finish)).days if base_finish else None
            rows.append({"activity_id":a["id"],"code":a["code"],"name":a["name"],"wbs_code":(a.get("wbs_nodes") or {}).get("code",""),"wbs_name":(a.get("wbs_nodes") or {}).get("name",""),"activity_type":a["activity_type"],"status":a["status"],"percent_complete":float(a.get("percent_complete") or 0),"planned_start":a["planned_start"],"planned_finish":a["planned_finish"],"current_start":current_start,"current_finish":current_finish,"actual_start":a.get("actual_start"),"actual_finish":a.get("actual_finish"),"is_critical":bool(a.get("is_critical")),"total_float":a.get("total_float"),"baseline_finish":base_finish,"finish_variance_days":variance,"budgeted_cost":round(costs.get(a["id"],0),2),"is_overdue":a["status"]!="complete" and finish_date<as_of})
        all_rows=list(rows); end=as_of+timedelta(days=lookahead_days)
        if report_type=="lookahead": rows=[r for r in rows if r["status"]!="complete" and date.fromisoformat(r["current_start"])<=end and date.fromisoformat(r["current_finish"])>=as_of]
        elif report_type=="critical": rows=[r for r in rows if r["is_critical"] and r["status"]!="complete"]
        elif report_type=="progress": rows=[r for r in rows if r["percent_complete"]>0 or r["actual_start"]]
        elif report_type=="overdue": rows=[r for r in rows if r["is_overdue"]]
        elif report_type=="variance": rows=[r for r in rows if r["finish_variance_days"] not in(None,0)]
        elif report_type=="resources": rows=[r for r in rows if r["budgeted_cost"]>0]
        total_weight=sum(max(1,int(a.get("duration_days") or 0)) for a in activities) or 1
        earned=sum(max(1,int(a.get("duration_days") or 0))*float(a.get("percent_complete") or 0) for a in activities)
        summary={"total_activities":len(all_rows),"not_started":sum(r["status"]=="not_started" for r in all_rows),"in_progress":sum(r["status"]=="in_progress" for r in all_rows),"complete":sum(r["status"]=="complete" for r in all_rows),"critical_open":sum(r["is_critical"] and r["status"]!="complete" for r in all_rows),"overdue":sum(r["is_overdue"] for r in all_rows),"overall_percent":round(earned/total_weight,2),"budgeted_cost":round(sum(r["budgeted_cost"] for r in all_rows),2)}
        return {"report_type":report_type,"data_date":as_of.isoformat(),"lookahead_days":lookahead_days,"baseline":baseline and {k:baseline.get(k) for k in("id","name","data_date")},"summary":summary,"rows":rows}
