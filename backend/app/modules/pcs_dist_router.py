from __future__ import annotations

# PCS Multi-Location DPR — Stage 4 backend: operational worker distribution
# across work locations (with time-overlap conflict detection) and the PCS
# report readiness summary. Distribution is operational reporting only and does
# does not modify workforce source-of-truth records. The picker reads the
# selected site's daily allocation so managers cannot accidentally distribute a
# worker who was not allocated to PCS. No cost data is exposed.

from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

MANAGEMENT_ROLES = {
    "admin", "general_manager", "operation_manager", "hr_assistant",
    "main_sup", "wshc_lead",
}

# Canonical segment windows (hour-of-day) for overlap checks; custom uses times.
SEGMENTS = {"morning": (6, 12), "afternoon": (12, 18), "night": (18, 24)}


@dataclass(frozen=True)
class PcsDistContext:
    get_current_user: Callable
    shared_client: Callable
    rest_url: str
    supabase_headers: Callable
    audit: Callable


class DistIn(BaseModel):
    site_id: Optional[str] = None
    project_id: Optional[str] = None
    distribution_date: str
    location_id: str
    worker_id: str
    segment: str = Field(default="custom", pattern="^(morning|afternoon|night|custom)$")
    start_time: Optional[str] = None   # "HH:MM"
    end_time: Optional[str] = None
    remarks: Optional[str] = None


def _minutes(hhmm):
    try:
        h, m = str(hhmm).split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _window(seg, start_time, end_time):
    """Return (start_min, end_min) for a distribution row, or None if unknown."""
    if seg in SEGMENTS:
        a, b = SEGMENTS[seg]
        return (a * 60, b * 60)
    s, e = _minutes(start_time), _minutes(end_time)
    if s is None or e is None or e <= s:
        return None
    return (s, e)


def _overlap(w1, w2):
    if not w1 or not w2:
        return False
    return w1[0] < w2[1] and w2[0] < w1[1]


def build_pcs_dist_router(c: PcsDistContext) -> APIRouter:
    router = APIRouter(prefix="/api/v1/pcs", tags=["pcs-dist"])

    def management(user):
        if user.get("role") not in MANAGEMENT_ROLES:
            raise HTTPException(status_code=403, detail="Distribution is manager/administrator only")

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

    @router.get("/distribution")
    async def list_distribution(distribution_date: str, project_id: Optional[str] = None,
                                site_id: Optional[str] = None, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            pid = await resolve_pid(client, user, project_id, site_id)

            async def q(path, params):
                r = await client.get(f"{c.rest_url}/{path}", params=params, headers=headers(user))
                return r.json() if r.status_code == 200 else []

            dist = await q("pcs_worker_distributions",
                           {"project_id": f"eq.{pid}", "distribution_date": f"eq.{distribution_date}",
                            "select": "*", "order": "location_id.asc"})
            locations = await q("pcs_work_locations",
                                {"project_id": f"eq.{pid}", "status": "eq.active",
                                 "select": "id,name,status", "order": "display_order.asc"})
            # Worker choices are deliberately limited to the PCS site's main
            # allocation for this date. This is a read-only dependency: location
            # distribution never changes the source roster.
            resolved_site_id = site_id
            if not resolved_site_id:
                sites = await q("sites", {"project_id": f"eq.{pid}", "select": "id", "limit": "1"})
                resolved_site_id = sites[0].get("id") if sites else None
            allocations = []
            if resolved_site_id:
                allocations = await q(
                    "allocations",
                    {"site_id": f"eq.{resolved_site_id}",
                     "work_date": f"eq.{distribution_date}", "status": "eq.allocated",
                     "select": "worker_id,workers(id,name,worker_code,status)"},
                )
            workers = []
            seen = set()
            for allocation in allocations:
                worker = allocation.get("workers") or {}
                worker_id = worker.get("id") or allocation.get("worker_id")
                if worker_id and worker_id not in seen:
                    seen.add(worker_id)
                    workers.append({"id": worker_id, "name": worker.get("name") or "?",
                                    "worker_code": worker.get("worker_code") or "",
                                    "status": worker.get("status") or ""})
            workers.sort(key=lambda row: (row.get("name") or "").lower())
            # Flag duplicate/overlap conflicts for the same worker on this date.
            by_worker = {}
            for d in dist:
                by_worker.setdefault(d.get("worker_id"), []).append(d)
            conflicts = []
            for wid, rows in by_worker.items():
                for i in range(len(rows)):
                    for j in range(i + 1, len(rows)):
                        wa = _window(rows[i].get("segment"), rows[i].get("start_time"), rows[i].get("end_time"))
                        wb = _window(rows[j].get("segment"), rows[j].get("start_time"), rows[j].get("end_time"))
                        if _overlap(wa, wb):
                            conflicts.append({"worker_id": wid, "a": rows[i]["id"], "b": rows[j]["id"]})
            return {"project_id": pid, "distributions": dist, "locations": locations,
                    "workers": workers, "allocated_worker_count": len(workers),
                    "conflicts": conflicts}

    @router.post("/distribution", status_code=201)
    async def add_distribution(body: DistIn, user: dict = Depends(c.get_current_user)):
        management(user)
        neww = _window(body.segment, body.start_time, body.end_time)
        if neww is None:
            raise HTTPException(status_code=400, detail="Provide a valid segment or start/end time")
        async with c.shared_client() as client:
            pid = await resolve_pid(client, user, body.project_id, body.site_id)
            resolved_site_id = body.site_id
            if not resolved_site_id:
                sr = await client.get(f"{c.rest_url}/sites",
                                      params={"project_id": f"eq.{pid}", "select": "id", "limit": "1"},
                                      headers=headers(user))
                resolved_site_id = sr.json()[0].get("id") if sr.status_code == 200 and sr.json() else None
            roster = await client.get(
                f"{c.rest_url}/allocations",
                params={"site_id": f"eq.{resolved_site_id}",
                        "work_date": f"eq.{body.distribution_date}",
                        "worker_id": f"eq.{body.worker_id}", "status": "eq.allocated",
                        "select": "id", "limit": "1"},
                headers=headers(user))
            if roster.status_code != 200 or not roster.json():
                raise HTTPException(status_code=422,
                                    detail="Choose a worker allocated to PCS for this date.")
            ex = await client.get(f"{c.rest_url}/pcs_worker_distributions",
                                  params={"project_id": f"eq.{pid}", "distribution_date": f"eq.{body.distribution_date}",
                                          "worker_id": f"eq.{body.worker_id}", "select": "*"}, headers=headers(user))
            for d in (ex.json() if ex.status_code == 200 else []):
                if _overlap(neww, _window(d.get("segment"), d.get("start_time"), d.get("end_time"))):
                    raise HTTPException(status_code=409,
                                        detail="This worker already has an overlapping assignment that day.")
            payload = {"project_id": pid, "distribution_date": body.distribution_date,
                       "location_id": body.location_id, "worker_id": body.worker_id,
                       "segment": body.segment, "start_time": body.start_time,
                       "end_time": body.end_time, "remarks": body.remarks,
                       "created_by": user["user_id"], "updated_by": user["user_id"]}
            r = await client.post(f"{c.rest_url}/pcs_worker_distributions",
                                  headers=headers(user, True), json=payload)
            if r.status_code not in (200, 201) or not r.json():
                raise HTTPException(status_code=400, detail="Could not save distribution")
            row = r.json()[0]
            await c.audit(client, user, "create", "pcs_worker_distribution", row["id"], None, row)
            return row

    @router.delete("/distribution/{did}")
    async def del_distribution(did: str, user: dict = Depends(c.get_current_user)):
        management(user)
        async with c.shared_client() as client:
            r = await client.delete(f"{c.rest_url}/pcs_worker_distributions",
                                    params={"id": f"eq.{did}"}, headers=headers(user))
            if r.status_code not in (200, 204):
                raise HTTPException(status_code=400, detail="Could not remove distribution")
            await c.audit(client, user, "delete", "pcs_worker_distribution", did, None, None)
            return {"ok": True}

    @router.get("/readiness")
    async def readiness(report_date: str, project_id: Optional[str] = None,
                        site_id: Optional[str] = None, user: dict = Depends(c.get_current_user)):
        async with c.shared_client() as client:
            pid = await resolve_pid(client, user, project_id, site_id)

            async def q(path, params):
                r = await client.get(f"{c.rest_url}/{path}", params=params, headers=headers(user))
                return r.json() if r.status_code == 200 else []

            locations = await q("pcs_work_locations", {"project_id": f"eq.{pid}", "select": "id,name,status"})
            active = [l for l in locations if l.get("status") == "active"]
            excluded = [l for l in locations if l.get("status") in ("stopped", "completed")]
            parent = await q("pcs_daily_reports",
                             {"project_id": f"eq.{pid}", "report_date": f"eq.{report_date}",
                              "select": "id,status,completion_override,override_reason,"
                                        "pcs_location_reports(location_id,status)", "limit": "1"})
            lrs = parent[0].get("pcs_location_reports", []) if parent else []
            submitted_ids = {r["location_id"] for r in lrs if r.get("status") == "submitted"}
            active_ids = {l["id"] for l in active}
            pending = [l for l in active if l["id"] not in submitted_ids]
            override = parent[0].get("completion_override") if parent else False
            return {
                "project_id": pid, "report_date": report_date,
                "expected_locations": len(active),
                "submitted_locations": len(active_ids & submitted_ids),
                "pending_locations": [{"id": l["id"], "name": l["name"]} for l in pending],
                "excluded_locations": [{"id": l["id"], "name": l["name"], "status": l["status"]} for l in excluded],
                "overall_ready": len(pending) == 0 and len(active) > 0,
                "completion_override": bool(override),
            }

    return router
