from __future__ import annotations

# PCS Multi-Location DPR — Stage 2 backend: manager daily planning workspace,
# publish/revision workflow, the PCS dashboard aggregation, and the WhatsApp
# plan-message audit trail. Deterministic: the WhatsApp text is built by the
# client from saved plan data; this module only persists and audits it — no
# external AI service is involved. No cost/rate data is exposed here.

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

MANAGEMENT_ROLES = {
    "admin", "general_manager", "operation_manager", "hr_assistant",
    "main_sup", "wshc_lead",
}


@dataclass(frozen=True)
class PcsPlanContext:
    get_current_user: Callable
    shared_client: Callable
    rest_url: str
    supabase_headers: Callable
    audit: Callable


class ActivityIn(BaseModel):
    location_id: str
    description: str = Field(min_length=1)
    previous_completion: Optional[float] = None
    supervisor_id: Optional[str] = None
    priority: str = Field(default="normal", pattern="^(normal|urgent|critical)$")
    planned_manpower: Optional[int] = None
    display_order: int = 0
    remarks: Optional[str] = None


class ActivityPatch(BaseModel):
    location_id: Optional[str] = None
    description: Optional[str] = None
    previous_completion: Optional[float] = None
    supervisor_id: Optional[str] = None
    priority: Optional[str] = Field(default=None, pattern="^(normal|urgent|critical)$")
    planned_manpower: Optional[int] = None
    status: Optional[str] = Field(default=None,
        pattern="^(draft|published|accepted|in_progress|completed|deferred|cancelled)$")
    display_order: Optional[int] = None
    remarks: Optional[str] = None


class PlanRef(BaseModel):
    site_id: Optional[str] = None
    project_id: Optional[str] = None
    plan_date: str


class WhatsAppIn(BaseModel):
    site_id: Optional[str] = None
    project_id: Optional[str] = None
    plan_date: str
    format: str = Field(default="detailed", pattern="^(short|detailed)$")
    generated_text: Optional[str] = None
    edited_text: Optional[str] = None
    final_text: Optional[str] = None


class PlannedResourceIn(BaseModel):
    location_id: Optional[str] = None
    item_name: str = Field(min_length=1)
    quantity: Optional[float] = None
    unit: Optional[str] = None


def build_pcs_plan_router(c: PcsPlanContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/pcs", tags=["pcs-plan"])

    def management(user):
        if user.get("role") not in MANAGEMENT_ROLES:
            raise HTTPException(status_code=403,
                                detail="PCS planning is manager/administrator only")

    def headers(user, representation=False):
        h = c.supabase_headers(user["token"])
        if representation:
            h = {**h, "Prefer": "return=representation"}
        return h

    async def resolve_pid(client, user, project_id, site_id):
        if project_id:
            return project_id
        if site_id:
            r = await client.get(f"{c.rest_url}/sites",
                                 params={"id": f"eq.{site_id}", "select": "project_id", "limit": "1"},
                                 headers=headers(user))
            if r.status_code == 200 and r.json():
                pid = r.json()[0].get("project_id")
                if pid:
                    return pid
        raise HTTPException(status_code=400, detail="A valid project_id or site_id is required")

    async def get_plan_row(client, user, pid, plan_date):
        r = await client.get(f"{c.rest_url}/pcs_daily_plans",
                             params={"project_id": f"eq.{pid}", "plan_date": f"eq.{plan_date}",
                                     "select": "*", "limit": "1"},
                             headers=headers(user))
        if r.status_code != 200:
            raise HTTPException(status_code=500, detail="Could not load plan")
        rows = r.json()
        return rows[0] if rows else None

    # ---- Plan read / create ----------------------------------------------
    @router.get("/plan")
    async def get_plan(plan_date: str, project_id: Optional[str] = None,
                       site_id: Optional[str] = None, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            pid = await resolve_pid(client, user, project_id, site_id)
            plan = await get_plan_row(client, user, pid, plan_date)
            activities, materials, plant = [], [], []
            if plan:
                ra = await client.get(f"{c.rest_url}/pcs_planned_activities",
                                     params={"plan_id": f"eq.{plan['id']}", "select": "*",
                                             "order": "display_order.asc"},
                                     headers=headers(user))
                if ra.status_code == 200:
                    activities = ra.json()
                rm = await client.get(f"{c.rest_url}/pcs_planned_materials",
                                      params={"plan_id": f"eq.{plan['id']}", "select": "*"},
                                      headers=headers(user))
                if rm.status_code == 200:
                    materials = rm.json()
                re = await client.get(f"{c.rest_url}/pcs_planned_plant",
                                      params={"plan_id": f"eq.{plan['id']}", "select": "*"},
                                      headers=headers(user))
                if re.status_code == 200:
                    plant = re.json()
            return {"project_id": pid, "plan": plan, "activities": activities,
                    "materials": materials, "plant": plant}

    @router.post("/plan", status_code=201)
    async def ensure_plan(body: PlanRef, user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            pid = await resolve_pid(client, user, body.project_id, body.site_id)
            existing = await get_plan_row(client, user, pid, body.plan_date)
            if existing:
                return existing
            r = await client.post(f"{c.rest_url}/pcs_daily_plans", headers=headers(user, True),
                                  json={"project_id": pid, "plan_date": body.plan_date,
                                        "status": "draft", "revision": 1,
                                        "created_by": user["user_id"], "updated_by": user["user_id"]})
            if r.status_code not in (200, 201):
                raise HTTPException(status_code=400, detail="Could not create plan")
            row = r.json()[0]
            await c.audit(client, user, "create", "pcs_daily_plan", row["id"], None, row)
            return row

    # ---- Planned activities ----------------------------------------------
    @router.post("/plan/{plan_id}/activities", status_code=201)
    async def add_activity(plan_id: str, body: ActivityIn, user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            payload = {"plan_id": plan_id, "location_id": body.location_id,
                       "description": body.description.strip(),
                       "previous_completion": body.previous_completion,
                       "supervisor_id": body.supervisor_id, "priority": body.priority,
                       "planned_manpower": body.planned_manpower,
                       "display_order": body.display_order, "remarks": body.remarks,
                       "status": "draft",
                       "created_by": user["user_id"], "updated_by": user["user_id"]}
            r = await client.post(f"{c.rest_url}/pcs_planned_activities",
                                  headers=headers(user, True), json=payload)
            if r.status_code not in (200, 201):
                raise HTTPException(status_code=400, detail="Could not add activity")
            row = r.json()[0]
            await c.audit(client, user, "create", "pcs_planned_activity", row["id"], None, row)
            return row

    @router.patch("/plan/activities/{activity_id}")
    async def edit_activity(activity_id: str, body: ActivityPatch,
                            user: dict = Depends(c.get_current_user)):
        management(user)
        patch = body.model_dump(exclude_unset=True)
        if "description" in patch and patch["description"] is not None:
            patch["description"] = patch["description"].strip()
        if not patch:
            return {"ok": True}
        patch["updated_by"] = user["user_id"]
        async with c.shared_client() as client:
            r = await client.patch(f"{c.rest_url}/pcs_planned_activities",
                                   params={"id": f"eq.{activity_id}"},
                                   headers=headers(user, True), json=patch)
            if r.status_code != 200 or not r.json():
                raise HTTPException(status_code=404, detail="Activity not found")
            await c.audit(client, user, "update", "pcs_planned_activity", activity_id, None, patch)
            return r.json()[0]

    @router.delete("/plan/activities/{activity_id}")
    async def delete_activity(activity_id: str, user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            r = await client.delete(f"{c.rest_url}/pcs_planned_activities",
                                    params={"id": f"eq.{activity_id}"}, headers=headers(user))
            if r.status_code not in (200, 204):
                raise HTTPException(status_code=400, detail="Could not delete activity")
            await c.audit(client, user, "delete", "pcs_planned_activity", activity_id, None, None)
            return {"ok": True}

    @router.post("/plan/{plan_id}/material", status_code=201)
    async def add_planned_material(plan_id: str, body: PlannedResourceIn,
                                   user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            payload = body.model_dump()
            payload.update({"plan_id": plan_id, "item_name": body.item_name.strip(),
                            "created_by": user["user_id"]})
            row = await insert_resource(client, user, "pcs_planned_materials", payload,
                                        "Could not add planned material")
            await c.audit(client, user, "create", "pcs_planned_material", row["id"], None, row)
            return row

    @router.post("/plan/{plan_id}/plant", status_code=201)
    async def add_planned_plant(plan_id: str, body: PlannedResourceIn,
                                user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            payload = body.model_dump(exclude={"unit"})
            payload.update({"plan_id": plan_id, "item_name": body.item_name.strip(),
                            "created_by": user["user_id"]})
            row = await insert_resource(client, user, "pcs_planned_plant", payload,
                                        "Could not add planned plant/equipment")
            await c.audit(client, user, "create", "pcs_planned_plant", row["id"], None, row)
            return row

    async def insert_resource(client, user, table, payload, message):
        r = await client.post(f"{c.rest_url}/{table}", headers=headers(user, True), json=payload)
        if r.status_code not in (200, 201) or not r.json():
            raise HTTPException(status_code=400, detail=message)
        return r.json()[0]

    @router.delete("/plan/resource/{kind}/{resource_id}")
    async def delete_planned_resource(kind: str, resource_id: str,
                                      user: dict = Depends(c.get_current_user)):
        management(user)
        table = {"material": "pcs_planned_materials", "plant": "pcs_planned_plant"}.get(kind)
        if not table:
            raise HTTPException(status_code=400, detail="Unknown resource type")
        async with c.shared_client() as client:
            r = await client.delete(f"{c.rest_url}/{table}", params={"id": f"eq.{resource_id}"},
                                    headers=headers(user))
            if r.status_code not in (200, 204):
                raise HTTPException(status_code=400, detail="Could not remove planned resource")
            await c.audit(client, user, "delete", "pcs_planned_resource", resource_id, None,
                          {"kind": kind})
            return {"ok": True}

    @router.patch("/plan/resource/{kind}/{resource_id}")
    async def edit_planned_resource(kind: str, resource_id: str, body: PlannedResourceIn,
                                    user: dict = Depends(c.get_current_user)):
        management(user)
        table = {"material": "pcs_planned_materials", "plant": "pcs_planned_plant"}.get(kind)
        if not table:
            raise HTTPException(status_code=400, detail="Unknown resource type")
        patch = body.model_dump(exclude={"unit"} if kind == "plant" else set())
        patch["item_name"] = body.item_name.strip()
        async with c.shared_client() as client:
            r = await client.patch(f"{c.rest_url}/{table}", params={"id": f"eq.{resource_id}"},
                                   headers=headers(user, True), json=patch)
            if r.status_code != 200 or not r.json():
                raise HTTPException(status_code=404, detail="Planned resource not found")
            await c.audit(client, user, "update", "pcs_planned_resource", resource_id, None,
                          {"kind": kind, **patch})
            return r.json()[0]

    @router.post("/plan/{plan_id}/reopen")
    async def reopen_plan(plan_id: str, user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            r = await client.patch(f"{c.rest_url}/pcs_daily_plans",
                                   params={"id": f"eq.{plan_id}"}, headers=headers(user, True),
                                   json={"status": "draft", "updated_by": user["user_id"]})
            if r.status_code != 200 or not r.json():
                raise HTTPException(status_code=404, detail="Plan not found")
            await c.audit(client, user, "reopen", "pcs_daily_plan", plan_id, None, None)
            return r.json()[0]

    # ---- Publish + revision snapshot -------------------------------------
    @router.post("/plan/{plan_id}/publish")
    async def publish_plan(plan_id: str, user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            rp = await client.get(f"{c.rest_url}/pcs_daily_plans",
                                 params={"id": f"eq.{plan_id}", "select": "*", "limit": "1"},
                                 headers=headers(user))
            if rp.status_code != 200 or not rp.json():
                raise HTTPException(status_code=404, detail="Plan not found")
            plan = rp.json()[0]
            ra = await client.get(f"{c.rest_url}/pcs_planned_activities",
                                 params={"plan_id": f"eq.{plan_id}", "select": "*",
                                         "order": "display_order.asc"}, headers=headers(user))
            activities = ra.json() if ra.status_code == 200 else []
            rm = await client.get(f"{c.rest_url}/pcs_planned_materials",
                                  params={"plan_id": f"eq.{plan_id}", "select": "*"},
                                  headers=headers(user))
            re = await client.get(f"{c.rest_url}/pcs_planned_plant",
                                  params={"plan_id": f"eq.{plan_id}", "select": "*"},
                                  headers=headers(user))
            revno = int(plan.get("revision") or 1)
            snapshot = {"plan": plan, "activities": activities,
                        "materials": rm.json() if rm.status_code == 200 else [],
                        "plant": re.json() if re.status_code == 200 else []}
            rr = await client.post(f"{c.rest_url}/pcs_daily_plan_revisions",
                                   headers=headers(user, True),
                                   json={"plan_id": plan_id, "revision": revno,
                                         "snapshot": snapshot, "published_by": user["user_id"]})
            if rr.status_code not in (200, 201):
                raise HTTPException(status_code=400, detail="Could not snapshot plan revision")
            up = await client.patch(f"{c.rest_url}/pcs_daily_plans",
                                    params={"id": f"eq.{plan_id}"}, headers=headers(user, True),
                                    json={"status": "published", "revision": revno + 1,
                                          "published_by": user["user_id"],
                                          "published_at": _now_iso(), "updated_by": user["user_id"]})
            if up.status_code != 200:
                raise HTTPException(status_code=400, detail="Could not publish plan")
            await client.patch(f"{c.rest_url}/pcs_planned_activities",
                               params={"plan_id": f"eq.{plan_id}", "status": "eq.draft"},
                               headers=headers(user), json={"status": "published"})
            await c.audit(client, user, "publish", "pcs_daily_plan", plan_id, None,
                          {"revision": revno, "activity_count": len(activities)})
            return {"ok": True, "revision": revno}

    # ---- Dashboard aggregation -------------------------------------------
    @router.get("/dashboard")
    async def dashboard(date: str, project_id: Optional[str] = None,
                        site_id: Optional[str] = None, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            pid = await resolve_pid(client, user, project_id, site_id)

            async def q(path, params):
                r = await client.get(f"{c.rest_url}/{path}", params=params, headers=headers(user))
                return r.json() if r.status_code == 200 else []

            locations = await q("pcs_work_locations",
                                {"project_id": f"eq.{pid}", "select": "*", "order": "display_order.asc"})
            plan = await get_plan_row(client, user, pid, date)
            plan_activities = []
            planned_materials = []
            planned_plant = []
            if plan:
                plan_activities = await q("pcs_planned_activities",
                                          {"plan_id": f"eq.{plan['id']}", "select": "*"})
                planned_materials = await q("pcs_planned_materials",
                                            {"plan_id": f"eq.{plan['id']}", "select": "*"})
                planned_plant = await q("pcs_planned_plant",
                                        {"plan_id": f"eq.{plan['id']}", "select": "*"})
            parent = await q("pcs_daily_reports",
                             {"project_id": f"eq.{pid}", "report_date": f"eq.{date}",
                              "select": "*,pcs_location_reports(id,location_id,status,supervisor_id)", "limit": "1"})
            location_reports = parent[0].get("pcs_location_reports", []) if parent else []
            requests = await q("pcs_resource_requests",
                               {"project_id": f"eq.{pid}",
                                "status": "in.(requested,reviewed,approved,partially_arranged)",
                                "select": "id,request_type,item_name,priority,status,required_by"})
            distributions = await q("pcs_worker_distributions",
                                    {"project_id": f"eq.{pid}", "distribution_date": f"eq.{date}",
                                     "select": "id,location_id,worker_id,segment"})

            active_locs = [l for l in locations if l.get("status") == "active"]
            submitted = [r for r in location_reports if r.get("status") == "submitted"]
            return {
                "project_id": pid, "date": date,
                "locations": locations,
                "active_location_count": len(active_locs),
                "plan": plan, "plan_activities": plan_activities,
                "planned_materials": planned_materials, "planned_plant": planned_plant,
                "location_reports": location_reports,
                "submitted_count": len(submitted),
                "pending_count": max(0, len(active_locs) - len(submitted)),
                "distribution_count": len(distributions),
                "open_requests": requests,
            }

    # ---- WhatsApp plan message audit -------------------------------------
    @router.post("/whatsapp", status_code=201)
    async def save_whatsapp(body: WhatsAppIn, user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            pid = await resolve_pid(client, user, body.project_id, body.site_id)
            r = await client.post(f"{c.rest_url}/pcs_whatsapp_plan_messages",
                                  headers=headers(user, True),
                                  json={"project_id": pid, "plan_date": body.plan_date,
                                        "format": body.format,
                                        "generated_text": body.generated_text,
                                        "edited_text": body.edited_text,
                                        "final_text": body.final_text,
                                        "generated_by": user["user_id"]})
            if r.status_code not in (200, 201):
                raise HTTPException(status_code=400, detail="Could not save WhatsApp message")
            row = r.json()[0]
            await c.audit(client, user, "create", "pcs_whatsapp_plan_message", row["id"], None,
                          {"plan_date": body.plan_date, "format": body.format})
            return row

    return router
