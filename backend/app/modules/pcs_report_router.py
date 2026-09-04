from __future__ import annotations

# PCS Multi-Location DPR — Stage 3 backend: the supervisor location-report flow.
# Parent report shell, per-location child reports, today/tomorrow activities,
# actual materials/plant, resource requests, and an idempotent submit guarded by
# optimistic record_version concurrency so two supervisors never overwrite each
# other. Writes are role/RLS scoped to the user's assigned locations. No cost
# data is exposed. Reads reuse the user's token, so supervisors see only what
# their role permits.

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PcsReportContext:
    get_current_user: Callable
    shared_client: Callable
    rest_url: str
    supabase_headers: Callable
    audit: Callable


class ReportRef(BaseModel):
    site_id: Optional[str] = None
    project_id: Optional[str] = None
    report_date: str


class LocationRef(BaseModel):
    location_id: str


class ActivityIn(BaseModel):
    kind: str = Field(pattern="^(today|tomorrow)$")
    description: str = Field(min_length=1)
    percent_complete: Optional[float] = None
    previous_percent: Optional[float] = None
    source_plan_activity_id: Optional[str] = None
    origin: str = Field(default="manual", pattern="^(planned|manual)$")
    activity_status: Optional[str] = None
    remark: Optional[str] = None
    reduction_reason: Optional[str] = None
    display_order: int = 0


class ActivityPatch(BaseModel):
    description: Optional[str] = None
    percent_complete: Optional[float] = None
    previous_percent: Optional[float] = None
    activity_status: Optional[str] = None
    remark: Optional[str] = None
    reduction_reason: Optional[str] = None
    display_order: Optional[int] = None


class ActualMaterialIn(BaseModel):
    item_name: str = Field(min_length=1)
    quantity: Optional[float] = None
    unit: Optional[str] = None
    delivery_ref: Optional[str] = None
    remarks: Optional[str] = None


class ActualPlantIn(BaseModel):
    item_name: str = Field(min_length=1)
    quantity: Optional[float] = None
    usage_hours: Optional[float] = None
    usage_days: Optional[float] = None
    provider: Optional[str] = None
    remarks: Optional[str] = None


class ResourceRequestIn(BaseModel):
    site_id: Optional[str] = None
    project_id: Optional[str] = None
    location_id: Optional[str] = None
    location_report_id: Optional[str] = None
    request_type: str = Field(pattern="^(material|plant)$")
    item_name: str = Field(min_length=1)
    quantity: Optional[float] = None
    unit: Optional[str] = None
    required_by: Optional[str] = None
    required_from: Optional[str] = None
    required_until: Optional[str] = None
    priority: str = Field(default="normal", pattern="^(normal|urgent|critical)$")


class SubmitIn(BaseModel):
    record_version: int


def build_pcs_report_router(c: PcsReportContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/pcs", tags=["pcs-report"])

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

    async def insert(client, user, table, payload, err):
        r = await client.post(f"{c.rest_url}/{table}", headers=headers(user, True), json=payload)
        if r.status_code not in (200, 201) or not r.json():
            raise HTTPException(status_code=400, detail=err)
        return r.json()[0]

    # ---- Parent + location report shells ---------------------------------
    @router.post("/report/ensure", status_code=201)
    async def ensure_report(body: ReportRef, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            pid = await resolve_pid(client, user, body.project_id, body.site_id)
            ex = await client.get(f"{c.rest_url}/pcs_daily_reports",
                                  params={"project_id": f"eq.{pid}", "report_date": f"eq.{body.report_date}",
                                          "select": "*", "limit": "1"}, headers=headers(user))
            if ex.status_code == 200 and ex.json():
                return ex.json()[0]
            row = await insert(client, user, "pcs_daily_reports",
                               {"project_id": pid, "report_date": body.report_date, "status": "open",
                                "created_by": user["user_id"], "updated_by": user["user_id"]},
                               "Could not open the PCS report")
            await c.audit(client, user, "create", "pcs_daily_report", row["id"], None, row)
            return row

    @router.get("/report")
    async def get_report(report_date: str, project_id: Optional[str] = None,
                         site_id: Optional[str] = None, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            pid = await resolve_pid(client, user, project_id, site_id)
            rp = await client.get(f"{c.rest_url}/pcs_daily_reports",
                                  params={"project_id": f"eq.{pid}", "report_date": f"eq.{report_date}",
                                          "select": "*,pcs_location_reports(*,pcs_location_activities(*),"
                                                    "pcs_actual_materials(*),pcs_actual_plant(*),pcs_location_photos(*))",
                                          "limit": "1"}, headers=headers(user))
            if rp.status_code != 200:
                raise HTTPException(status_code=500, detail="Could not load report")
            rows = rp.json()
            return {"project_id": pid, "report": rows[0] if rows else None}

    @router.post("/report/{parent_id}/location", status_code=201)
    async def ensure_location_report(parent_id: str, body: LocationRef,
                                     user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            ex = await client.get(f"{c.rest_url}/pcs_location_reports",
                                  params={"parent_id": f"eq.{parent_id}", "location_id": f"eq.{body.location_id}",
                                          "select": "*", "limit": "1"}, headers=headers(user))
            if ex.status_code == 200 and ex.json():
                return ex.json()[0]
            row = await insert(client, user, "pcs_location_reports",
                               {"parent_id": parent_id, "location_id": body.location_id,
                                "reported_by": user["user_id"], "supervisor_id": user["user_id"],
                                "status": "draft", "record_version": 1,
                                "created_by": user["user_id"], "last_updated_by": user["user_id"]},
                               "Could not start this location report (it may already exist)")
            await c.audit(client, user, "create", "pcs_location_report", row["id"], None, row)
            return row

    @router.get("/location-report/{lr_id}")
    async def get_location_report(lr_id: str, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            r = await client.get(f"{c.rest_url}/pcs_location_reports",
                                 params={"id": f"eq.{lr_id}",
                                         "select": "*,pcs_location_activities(*),pcs_actual_materials(*),"
                                                   "pcs_actual_plant(*),pcs_location_photos(*)", "limit": "1"},
                                 headers=headers(user))
            if r.status_code != 200 or not r.json():
                raise HTTPException(status_code=404, detail="Location report not found")
            return r.json()[0]

    @router.post("/location-report/{lr_id}/reset-draft")
    async def reset_location_draft(lr_id: str, body: SubmitIn,
                                   user: dict = Depends(c.get_current_user)):
        """Make a retry replace-safe before the client re-sends draft rows.

        A weak connection can stop after some child rows were written.  Clearing
        the still-draft children makes the next attempt deterministic instead of
        duplicating activities/resources. Submitted reports are never cleared.
        """
        async with c.shared_client() as client:
            cur = await client.get(
                f"{c.rest_url}/pcs_location_reports",
                params={"id": f"eq.{lr_id}", "select": "id,status,record_version", "limit": "1"},
                headers=headers(user))
            if cur.status_code != 200 or not cur.json():
                raise HTTPException(status_code=404, detail="Location report not found")
            row = cur.json()[0]
            if row.get("status") == "submitted":
                return {"ok": True, "status": "submitted", "idempotent": True}
            if int(row.get("record_version") or 1) != int(body.record_version):
                raise HTTPException(status_code=409, detail="This location changed. Reload before retrying.")
            for table in ("pcs_location_activities", "pcs_actual_materials",
                          "pcs_actual_plant", "pcs_resource_requests",
                          "pcs_location_photos"):
                r = await client.delete(
                    f"{c.rest_url}/{table}",
                    params={"location_report_id": f"eq.{lr_id}"}, headers=headers(user))
                if r.status_code not in (200, 204):
                    raise HTTPException(status_code=500, detail="Could not safely prepare this draft for retry")
            return {"ok": True, "status": "draft", "record_version": row.get("record_version")}

    # ---- Activities (today / tomorrow) -----------------------------------
    @router.post("/location-report/{lr_id}/activity", status_code=201)
    async def add_activity(lr_id: str, body: ActivityIn, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            payload = body.model_dump()
            payload["description"] = payload["description"].strip()
            payload.update({"location_report_id": lr_id,
                            "created_by": user["user_id"], "updated_by": user["user_id"]})
            row = await insert(client, user, "pcs_location_activities", payload, "Could not add activity")
            await c.audit(client, user, "create", "pcs_location_activity", row["id"], None, row)
            return row

    @router.patch("/location-activity/{act_id}")
    async def edit_activity(act_id: str, body: ActivityPatch, user: dict = Depends(c.get_current_user)):
        patch = body.model_dump(exclude_unset=True)
        if "description" in patch and patch["description"] is not None:
            patch["description"] = patch["description"].strip()
        if not patch:
            return {"ok": True}
        patch["updated_by"] = user["user_id"]
        async with c.shared_client() as client:
            r = await client.patch(f"{c.rest_url}/pcs_location_activities",
                                   params={"id": f"eq.{act_id}"}, headers=headers(user, True), json=patch)
            if r.status_code != 200 or not r.json():
                raise HTTPException(status_code=404, detail="Activity not found")
            await c.audit(client, user, "update", "pcs_location_activity", act_id, None, patch)
            return r.json()[0]

    @router.delete("/location-activity/{act_id}")
    async def delete_activity(act_id: str, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            r = await client.delete(f"{c.rest_url}/pcs_location_activities",
                                    params={"id": f"eq.{act_id}"}, headers=headers(user))
            if r.status_code not in (200, 204):
                raise HTTPException(status_code=400, detail="Could not delete activity")
            await c.audit(client, user, "delete", "pcs_location_activity", act_id, None, None)
            return {"ok": True}

    # ---- Actual materials / plant ----------------------------------------
    @router.post("/location-report/{lr_id}/actual-material", status_code=201)
    async def add_actual_material(lr_id: str, body: ActualMaterialIn,
                                  user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            payload = body.model_dump()
            payload["item_name"] = payload["item_name"].strip()
            payload.update({"location_report_id": lr_id, "created_by": user["user_id"]})
            row = await insert(client, user, "pcs_actual_materials", payload, "Could not record material")
            await c.audit(client, user, "create", "pcs_actual_material", row["id"], None, row)
            return row

    @router.post("/location-report/{lr_id}/actual-plant", status_code=201)
    async def add_actual_plant(lr_id: str, body: ActualPlantIn, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            payload = body.model_dump()
            payload["item_name"] = payload["item_name"].strip()
            payload.update({"location_report_id": lr_id, "created_by": user["user_id"]})
            row = await insert(client, user, "pcs_actual_plant", payload, "Could not record plant/equipment")
            await c.audit(client, user, "create", "pcs_actual_plant", row["id"], None, row)
            return row

    @router.delete("/actual-material/{mid}")
    async def del_actual_material(mid: str, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            r = await client.delete(f"{c.rest_url}/pcs_actual_materials",
                                    params={"id": f"eq.{mid}"}, headers=headers(user))
            if r.status_code not in (200, 204):
                raise HTTPException(status_code=400, detail="Could not delete material")
            return {"ok": True}

    @router.delete("/actual-plant/{pid}")
    async def del_actual_plant(pid: str, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            r = await client.delete(f"{c.rest_url}/pcs_actual_plant",
                                    params={"id": f"eq.{pid}"}, headers=headers(user))
            if r.status_code not in (200, 204):
                raise HTTPException(status_code=400, detail="Could not delete plant/equipment")
            return {"ok": True}

    # ---- Resource requests (no cost) -------------------------------------
    @router.post("/resource-request", status_code=201)
    async def add_request(body: ResourceRequestIn, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            pid = await resolve_pid(client, user, body.project_id, body.site_id)
            payload = {"project_id": pid, "location_id": body.location_id,
                       "location_report_id": body.location_report_id,
                       "request_type": body.request_type, "item_name": body.item_name.strip(),
                       "quantity": body.quantity, "unit": body.unit,
                       "required_by": body.required_by, "required_from": body.required_from,
                       "required_until": body.required_until, "priority": body.priority,
                       "status": "requested",
                       "created_by": user["user_id"], "updated_by": user["user_id"]}
            row = await insert(client, user, "pcs_resource_requests", payload, "Could not submit request")
            await c.audit(client, user, "create", "pcs_resource_request", row["id"], None, row)
            return row

    # ---- Submit with optimistic concurrency + idempotency ----------------
    @router.post("/location-report/{lr_id}/submit")
    async def submit_location_report(lr_id: str, body: SubmitIn,
                                     user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            cur = await client.get(f"{c.rest_url}/pcs_location_reports",
                                   params={"id": f"eq.{lr_id}", "select": "id,status,record_version", "limit": "1"},
                                   headers=headers(user))
            if cur.status_code != 200 or not cur.json():
                raise HTTPException(status_code=404, detail="Location report not found")
            row = cur.json()[0]
            if row.get("status") == "submitted":
                return {"ok": True, "status": "submitted", "record_version": row.get("record_version"),
                        "idempotent": True}
            if int(row.get("record_version") or 1) != int(body.record_version):
                raise HTTPException(status_code=409,
                                    detail="This location was updated by someone else. Reload before submitting.")
            upd = await client.patch(f"{c.rest_url}/pcs_location_reports",
                                     params={"id": f"eq.{lr_id}",
                                             "record_version": f"eq.{body.record_version}"},
                                     headers=headers(user, True),
                                     json={"status": "submitted", "submitted_by": user["user_id"],
                                           "submitted_at": _now_iso(),
                                           "last_updated_by": user["user_id"],
                                           "record_version": int(body.record_version) + 1})
            if upd.status_code != 200 or not upd.json():
                raise HTTPException(status_code=409, detail="Submit conflict. Reload and try again.")
            await c.audit(client, user, "submit", "pcs_location_report", lr_id, None,
                          {"record_version": int(body.record_version) + 1})
            return {"ok": True, "status": "submitted", "record_version": int(body.record_version) + 1}

    return router
