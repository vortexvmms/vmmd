from __future__ import annotations

# PCS Multi-Location DPR — Stage 1 backend: DPR mode configuration and the
# work-location directory (with supervisor assignment). Every mutation is
# role-checked here AND enforced by RLS in the database, and is written to the
# audit log. No cost/rate data is exposed on any endpoint in this module.

from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# Roles allowed to manage PCS configuration and the location directory.
MANAGEMENT_ROLES = {
    "admin", "general_manager", "operation_manager", "hr_assistant",
    "main_sup", "wshc_lead",
}
SUPERVISOR_ROLES = {"site_sup", "safety_sup", "wshc", "logistics_sup"}


@dataclass(frozen=True)
class PcsContext:
    get_current_user: Callable
    shared_client: Callable
    rest_url: str
    supabase_headers: Callable
    audit: Callable


class DprModeIn(BaseModel):
    project_id: str
    dpr_mode: str = Field(pattern="^(standard|multi_location)$")


class LocationIn(BaseModel):
    project_id: Optional[str] = None
    site_id: Optional[str] = None
    name: str = Field(min_length=1, max_length=200)
    code: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    planned_completion_date: Optional[str] = None
    actual_completion_date: Optional[str] = None
    status: str = Field(default="active", pattern="^(active|stopped|completed)$")
    dpr_reminder: bool = True
    display_order: int = 0
    remarks: Optional[str] = None


class LocationPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    code: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    planned_completion_date: Optional[str] = None
    actual_completion_date: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(active|stopped|completed)$")
    dpr_reminder: Optional[bool] = None
    display_order: Optional[int] = None
    remarks: Optional[str] = None


class SupervisorsIn(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


def build_pcs_router(c: PcsContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/pcs", tags=["pcs"])

    def management(user):
        if user.get("role") not in MANAGEMENT_ROLES:
            raise HTTPException(status_code=403,
                                detail="PCS configuration is manager/administrator only")

    def headers(user, representation=False):
        h = c.supabase_headers(user["token"])
        if representation:
            h = {**h, "Prefer": "return=representation"}
        return h

    async def resolve_project_id(client, user, project_id, site_id):
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

    # ---- DPR mode configuration ------------------------------------------
    @router.get("/dpr-config")
    async def get_dpr_config(project_id: Optional[str] = None, site_id: Optional[str] = None,
                             user: dict = Depends(c.get_current_user)):
        """Return the DPR mode for a project (or the project behind a site).
        Any signed-in user may read this so the DPR page can pick the interface."""
        async with c.shared_client() as client:
            pid = await resolve_project_id(client, user, project_id, site_id)
            r = await client.get(f"{c.rest_url}/projects",
                                 params={"id": f"eq.{pid}", "select": "id,dpr_mode", "limit": "1"},
                                 headers=headers(user))
            if r.status_code != 200 or not r.json():
                raise HTTPException(status_code=404, detail="Project not found")
            row = r.json()[0]
            return {"project_id": row["id"], "dpr_mode": row.get("dpr_mode") or "standard"}

    @router.put("/dpr-config")
    async def set_dpr_config(body: DprModeIn, user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            before = await client.get(f"{c.rest_url}/projects",
                                      params={"id": f"eq.{body.project_id}", "select": "id,dpr_mode", "limit": "1"},
                                      headers=headers(user))
            old = before.json()[0] if before.status_code == 200 and before.json() else None
            r = await client.patch(f"{c.rest_url}/projects",
                                   params={"id": f"eq.{body.project_id}"},
                                   headers=headers(user, True),
                                   json={"dpr_mode": body.dpr_mode})
            if r.status_code != 200 or not r.json():
                raise HTTPException(status_code=404, detail="Project not found")
            row = r.json()[0]
            await c.audit(client, user, "update", "pcs_dpr_mode", body.project_id, old,
                          {"dpr_mode": body.dpr_mode})
            return {"project_id": row["id"], "dpr_mode": row.get("dpr_mode")}

    # ---- Work-location directory -----------------------------------------
    @router.get("/locations")
    async def list_locations(project_id: Optional[str] = None, site_id: Optional[str] = None,
                             include_inactive: bool = True,
                             user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            pid = await resolve_project_id(client, user, project_id, site_id)
            params = {"project_id": f"eq.{pid}",
                      "select": "*,pcs_location_supervisors(user_id)",
                      "order": "display_order.asc,name.asc"}
            if not include_inactive:
                params["status"] = "eq.active"
            r = await client.get(f"{c.rest_url}/pcs_work_locations",
                                 params=params, headers=headers(user))
            if r.status_code != 200:
                raise HTTPException(status_code=500, detail="Could not load work locations")
            rows = r.json()
            # A PCS supervisor works only on locations explicitly assigned to
            # them. Managers retain the complete directory for consolidation.
            if user.get("role") in SUPERVISOR_ROLES:
                uid = user.get("user_id")
                rows = [row for row in rows if any(
                    assignment.get("user_id") == uid
                    for assignment in (row.get("pcs_location_supervisors") or [])
                )]
            return rows

    @router.post("/locations", status_code=201)
    async def create_location(body: LocationIn, user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            pid = await resolve_project_id(client, user, body.project_id, body.site_id)
            payload = {
                "project_id": pid,
                "name": body.name.strip(),
                "code": (body.code or "").strip() or None,
                "description": body.description,
                "start_date": body.start_date,
                "planned_completion_date": body.planned_completion_date,
                "actual_completion_date": body.actual_completion_date,
                "status": body.status,
                "dpr_reminder": body.dpr_reminder,
                "display_order": body.display_order,
                "remarks": body.remarks,
                "created_by": user["user_id"],
                "updated_by": user["user_id"],
            }
            r = await client.post(f"{c.rest_url}/pcs_work_locations",
                                  headers=headers(user, True), json=payload)
            if r.status_code not in (200, 201):
                raise HTTPException(status_code=400,
                                    detail="Could not create location (name may already exist)")
            row = r.json()[0]
            await c.audit(client, user, "create", "pcs_work_location", row["id"], None, row)
            return row

    @router.patch("/locations/{location_id}")
    async def update_location(location_id: str, body: LocationPatch,
                              user: dict = Depends(c.get_current_user)):
        management(user)
        patch = body.model_dump(exclude_unset=True)
        if "name" in patch and patch["name"] is not None:
            patch["name"] = patch["name"].strip()
        if not patch:
            return {"ok": True}
        patch["updated_by"] = user["user_id"]
        async with c.shared_client() as client:
            r = await client.patch(f"{c.rest_url}/pcs_work_locations",
                                   params={"id": f"eq.{location_id}"},
                                   headers=headers(user, True), json=patch)
            if r.status_code != 200 or not r.json():
                raise HTTPException(status_code=404, detail="Location not found")
            row = r.json()[0]
            await c.audit(client, user, "update", "pcs_work_location", location_id, None, patch)
            return row

    @router.get("/locations/{location_id}/supervisors")
    async def list_supervisors(location_id: str, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            r = await client.get(f"{c.rest_url}/pcs_location_supervisors",
                                 params={"location_id": f"eq.{location_id}", "select": "user_id"},
                                 headers=headers(user))
            if r.status_code != 200:
                raise HTTPException(status_code=500, detail="Could not load supervisors")
            return r.json()

    @router.post("/locations/{location_id}/supervisors")
    async def set_supervisors(location_id: str, body: SupervisorsIn,
                              user: dict = Depends(c.get_current_user)):
        """Replace the supervisor set for a location."""
        management(user)
        async with c.shared_client() as client:
            await client.delete(f"{c.rest_url}/pcs_location_supervisors",
                                params={"location_id": f"eq.{location_id}"},
                                headers=headers(user))
            uniq = [u for u in dict.fromkeys(body.user_ids) if u]
            if uniq:
                rows = [{"location_id": location_id, "user_id": uid,
                         "created_by": user["user_id"]} for uid in uniq]
                r = await client.post(f"{c.rest_url}/pcs_location_supervisors",
                                      headers=headers(user, True), json=rows)
                if r.status_code not in (200, 201):
                    raise HTTPException(status_code=400, detail="Could not assign supervisors")
            await c.audit(client, user, "update", "pcs_location_supervisors", location_id,
                          None, {"user_ids": uniq})
            return {"ok": True, "user_ids": uniq}

    return router
