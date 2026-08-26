from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from fastapi import APIRouter, Depends, HTTPException

from .schemas import (ActivityIn, ActivityMappingIn, ActivityPatch, ActivityTargetIn,
                      ManpowerRateIn, OtherCostIn, ResourceRateIn, SetupIn, WbsIn)


@dataclass(frozen=True)
class PlanningContext:
    get_current_user: Callable
    shared_client: Callable
    rest_url: str
    supabase_headers: Callable
    audit: Callable


def build_planning_router(c: PlanningContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/planning", tags=["planning"])

    def admin(user):
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Planning setup is administrator only")

    def headers(user, representation=False):
        h = c.supabase_headers(user["token"])
        if representation: h = {**h, "Prefer": "return=representation"}
        return h

    async def one(client, table, params, user):
        r = await client.get(f"{c.rest_url}/{table}", params=params, headers=headers(user))
        if r.status_code != 200: raise HTTPException(500, f"Could not load {table}")
        rows = r.json()
        return rows[0] if rows else None

    @router.get("/projects")
    async def projects(user: dict = Depends(c.get_current_user)):
        admin(user)
        async with c.shared_client() as client:
            r = await client.get(f"{c.rest_url}/projects", params={"select":"id,project_code,project_name,status,planned_start_date,planned_finish_date","status":"in.(draft,active,on_hold)","order":"project_name.asc"}, headers=headers(user))
            if r.status_code != 200: raise HTTPException(500,"Could not load planning projects")
            return r.json()

    @router.post("/projects/{project_id}/setup", status_code=201)
    async def setup(project_id: str, body: SetupIn, user: dict = Depends(c.get_current_user)):
        admin(user)
        async with c.shared_client() as client:
            existing = await one(client,"schedules",{"project_id":f"eq.{project_id}","select":"*","limit":"1"},user)
            if existing: return existing
            r = await client.post(f"{c.rest_url}/schedules", headers=headers(user,True), json={"project_id":project_id,"name":body.name.strip() or "Project Schedule","data_date":body.data_date.isoformat(),"status":"draft","created_by":user["user_id"],"updated_by":user["user_id"]})
            if r.status_code not in (200,201): raise HTTPException(500,"Could not initialise project schedule")
            row=r.json()[0]
            await client.post(f"{c.rest_url}/schedule_calendars",headers=headers(user,True),json={"project_id":project_id,"name":"Standard Singapore Calendar","hours_per_day":8,"is_default":True,"created_by":user["user_id"],"updated_by":user["user_id"]})
            await c.audit(client,user,"create","planning_schedule",row["id"],None,row)
            return row

    @router.get("/projects/{project_id}/workspace")
    async def workspace(project_id: str, user: dict = Depends(c.get_current_user)):
        admin(user)
        async with c.shared_client() as client:
            schedule=await one(client,"schedules",{"project_id":f"eq.{project_id}","select":"*","limit":"1"},user)
            if not schedule: return {"schedule":None,"wbs":[],"activities":[],"selected_dates":[],"exceptions":[]}
            calls=[
                client.get(f"{c.rest_url}/wbs_nodes",params={"project_id":f"eq.{project_id}","is_active":"eq.true","select":"*","order":"sort_order.asc"},headers=headers(user)),
                client.get(f"{c.rest_url}/schedule_activities",params={"project_id":f"eq.{project_id}","is_active":"eq.true","select":"*","order":"sort_order.asc"},headers=headers(user)),
                client.get(f"{c.rest_url}/planning_activity_dates",params={"project_id":f"eq.{project_id}","select":"activity_id,work_date","order":"work_date.asc"},headers=headers(user)),
                client.get(f"{c.rest_url}/calendar_exceptions",params={"project_id":f"eq.{project_id}","select":"id,exception_date,name,is_working,work_hours","order":"exception_date.asc"},headers=headers(user)),
            ]
            import asyncio
            results=await asyncio.gather(*calls)
            if any(r.status_code!=200 for r in results): raise HTTPException(500,"Could not load planning workspace")
            return {"schedule":schedule,"wbs":results[0].json(),"activities":results[1].json(),"selected_dates":results[2].json(),"exceptions":results[3].json()}

    @router.post("/projects/{project_id}/wbs", status_code=201)
    async def create_wbs(project_id: str, body: WbsIn, user: dict = Depends(c.get_current_user)):
        admin(user)
        async with c.shared_client() as client:
            schedule=await one(client,"schedules",{"project_id":f"eq.{project_id}","select":"id","limit":"1"},user)
            if not schedule: raise HTTPException(409,"Initialise the schedule first")
            r=await client.post(f"{c.rest_url}/wbs_nodes",headers=headers(user,True),json={"project_id":project_id,"schedule_id":schedule["id"],"parent_id":body.parent_id,"code":body.code.strip().upper(),"name":body.name.strip(),"created_by":user["user_id"],"updated_by":user["user_id"]})
            if r.status_code not in (200,201): raise HTTPException(400,"Could not create WBS item; check code and parent")
            return r.json()[0]

    async def replace_dates(client,user,activity_id,project_id,dates):
        r=await client.post(f"{c.rest_url}/rpc/replace_activity_dates",headers=headers(user),json={"p_activity_id":activity_id,"p_project_id":project_id,"p_dates":[d.isoformat() for d in dates]})
        if r.status_code not in (200,204): raise HTTPException(400,"Could not save selected dates")

    @router.post("/projects/{project_id}/activities", status_code=201)
    async def create_activity(project_id: str, body: ActivityIn, user: dict = Depends(c.get_current_user)):
        admin(user)
        async with c.shared_client() as client:
            schedule=await one(client,"schedules",{"project_id":f"eq.{project_id}","select":"id","limit":"1"},user)
            if not schedule: raise HTTPException(409,"Initialise the schedule first")
            first,last=body.selected_dates[0],body.selected_dates[-1]
            r=await client.post(f"{c.rest_url}/schedule_activities",headers=headers(user,True),json={"project_id":project_id,"schedule_id":schedule["id"],"wbs_id":body.wbs_id,"code":body.code.strip().upper(),"name":body.name.strip(),"activity_type":body.activity_type,"duration_days":0 if body.activity_type=="milestone" else len(body.selected_dates),"planned_start":first.isoformat(),"planned_finish":last.isoformat(),"created_by":user["user_id"],"updated_by":user["user_id"]})
            if r.status_code not in (200,201): raise HTTPException(400,"Could not create activity")
            row=r.json()[0]
            await replace_dates(client,user,row["id"],project_id,body.selected_dates)
            await c.audit(client,user,"create","planning_activity",row["id"],None,{**row,"selected_dates":[d.isoformat() for d in body.selected_dates]})
            return row

    @router.patch("/projects/{project_id}/activities/{activity_id}")
    async def update_activity(project_id: str, activity_id: str, body: ActivityPatch, user: dict = Depends(c.get_current_user)):
        admin(user)
        patch=body.model_dump(exclude_unset=True,exclude={"selected_dates"})
        if body.name is not None: patch["name"]=body.name.strip()
        patch["updated_by"]=user["user_id"]
        async with c.shared_client() as client:
            if patch:
                r=await client.patch(f"{c.rest_url}/schedule_activities",params={"id":f"eq.{activity_id}","project_id":f"eq.{project_id}"},headers=headers(user,True),json=patch)
                if r.status_code!=200 or not r.json(): raise HTTPException(404,"Activity not found")
            if body.selected_dates is not None: await replace_dates(client,user,activity_id,project_id,body.selected_dates)
            await c.audit(client,user,"update","planning_activity",activity_id,None,body.model_dump(mode="json",exclude_unset=True))
            return {"ok":True}

    @router.patch("/projects/{project_id}/activities/{activity_id}/target")
    async def set_target(project_id: str, activity_id: str, body: ActivityTargetIn,
                         user: dict = Depends(c.get_current_user)):
        admin(user)
        async with c.shared_client() as client:
            r=await client.patch(f"{c.rest_url}/schedule_activities",
                params={"id":f"eq.{activity_id}","project_id":f"eq.{project_id}"},
                headers=headers(user,True),json={"target_quantity":body.target_quantity,
                "unit":body.unit.strip(),"updated_by":user["user_id"]})
            if r.status_code!=200 or not r.json(): raise HTTPException(404,"Activity not found")
            return r.json()[0]

    @router.post("/projects/{project_id}/activities/{activity_id}/mapping", status_code=201)
    async def map_activity(project_id: str, activity_id: str, body: ActivityMappingIn,
                           user: dict = Depends(c.get_current_user)):
        admin(user)
        async with c.shared_client() as client:
            r=await client.post(f"{c.rest_url}/planning_activity_site_mappings",
                headers=headers(user,True),json={"activity_id":activity_id,"project_id":project_id,
                "site_id":body.site_id,"item_of_work":body.item_of_work,
                "effective_from":body.effective_from.isoformat(),
                "effective_to":body.effective_to.isoformat() if body.effective_to else None,
                "created_by":user["user_id"]})
            if r.status_code not in (200,201): raise HTTPException(400,"Could not map activity to site")
            return r.json()[0]

    @router.get("/dpr-options")
    async def dpr_options(site_id: str, date: str,
                          user: dict = Depends(c.get_current_user)):
        admin(user)
        async with c.shared_client() as client:
            r=await client.get(f"{c.rest_url}/planning_activity_site_mappings",params={
                "site_id":f"eq.{site_id}","is_active":"eq.true",
                "effective_from":f"lte.{date}","or":f"(effective_to.is.null,effective_to.gte.{date})",
                "select":"activity_id,item_of_work,schedule_activities(id,code,name,target_quantity,unit,percent_complete,status)",
                "order":"created_at.asc"},headers=headers(user))
            if r.status_code!=200: raise HTTPException(500,"Could not load mapped planning activities")
            rows=r.json()
            dr=await client.get(f"{c.rest_url}/daily_reports",params={"site_id":f"eq.{site_id}",
                "report_date":f"eq.{date}","select":"id","limit":"1"},headers=headers(user))
            saved={}
            if dr.status_code==200 and dr.json():
                pr=await client.get(f"{c.rest_url}/planning_dpr_progress_entries",params={
                    "daily_report_id":f"eq.{dr.json()[0]['id']}",
                    "select":"activity_id,quantity_completed,note"},headers=headers(user))
                if pr.status_code==200: saved={x["activity_id"]:x for x in pr.json()}
            for row in rows: row["saved_progress"]=saved.get(row["activity_id"])
            return rows

    @router.get("/projects/{project_id}/costing")
    async def costing(project_id: str, date_from: str | None = None, date_to: str | None = None,
                      user: dict = Depends(c.get_current_user)):
        admin(user)
        async with c.shared_client() as client:
            calls = [
                client.get(f"{c.rest_url}/planning_manpower_rates", params={"project_id":f"eq.{project_id}","select":"*","is_active":"eq.true","order":"effective_from.desc"}, headers=headers(user)),
                client.get(f"{c.rest_url}/planning_resource_rates", params={"project_id":f"eq.{project_id}","select":"*","is_active":"eq.true","order":"resource_type.asc,resource_name.asc"}, headers=headers(user)),
                client.get(f"{c.rest_url}/planning_other_direct_costs", params={"project_id":f"eq.{project_id}","select":"*","order":"cost_date.desc","limit":"200"}, headers=headers(user)),
                client.post(f"{c.rest_url}/rpc/planning_project_cost_summary", headers=headers(user), json={"p_project_id":project_id,"p_from":date_from,"p_to":date_to}),
            ]
            import asyncio
            rs=await asyncio.gather(*calls)
            if any(r.status_code not in (200,201) for r in rs): raise HTTPException(500,"Could not load private project costing")
            return {"manpower_rates":rs[0].json(),"resource_rates":rs[1].json(),"other_costs":rs[2].json(),"summary":rs[3].json()}

    @router.post("/projects/{project_id}/costing/manpower-rates", status_code=201)
    async def add_manpower_rate(project_id: str, body: ManpowerRateIn, user: dict = Depends(c.get_current_user)):
        admin(user)
        payload=body.model_dump(mode="json"); payload.update({"project_id":project_id,"trade":body.trade.strip() if body.trade else None,"created_by":user["user_id"]})
        async with c.shared_client() as client:
            r=await client.post(f"{c.rest_url}/planning_manpower_rates",headers=headers(user,True),json=payload)
            if r.status_code not in (200,201): raise HTTPException(400,"Could not save manpower rate")
            row=r.json()[0]; await c.audit(client,user,"create","planning_manpower_rate",row["id"],None,{"project_id":project_id}); return row

    @router.post("/projects/{project_id}/costing/resource-rates", status_code=201)
    async def add_resource_rate(project_id: str, body: ResourceRateIn, user: dict = Depends(c.get_current_user)):
        admin(user)
        payload=body.model_dump(mode="json"); payload.update({"project_id":project_id,"resource_name":body.resource_name.strip(),"created_by":user["user_id"]})
        async with c.shared_client() as client:
            r=await client.post(f"{c.rest_url}/planning_resource_rates",headers=headers(user,True),json=payload)
            if r.status_code not in (200,201): raise HTTPException(400,"Could not save resource rate")
            row=r.json()[0]; await c.audit(client,user,"create","planning_resource_rate",row["id"],None,{"project_id":project_id,"resource_type":body.resource_type}); return row

    @router.post("/projects/{project_id}/costing/other-costs", status_code=201)
    async def add_other_cost(project_id: str, body: OtherCostIn, user: dict = Depends(c.get_current_user)):
        admin(user)
        payload=body.model_dump(mode="json"); payload.update({"project_id":project_id,"created_by":user["user_id"]})
        async with c.shared_client() as client:
            r=await client.post(f"{c.rest_url}/planning_other_direct_costs",headers=headers(user,True),json=payload)
            if r.status_code not in (200,201): raise HTTPException(400,"Could not save direct cost")
            row=r.json()[0]; await c.audit(client,user,"create","planning_other_direct_cost",row["id"],None,{"project_id":project_id,"amount":body.amount}); return row

    return router
