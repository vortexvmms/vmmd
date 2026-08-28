# VCMS Assistant — natural-language data + WhatsApp drafting.
# Uses Google Gemini (free tier) with function-calling. The model may only call
# the tools below; each tool forwards the SIGNED-IN USER'S token to the existing
# VCMS endpoints, so every answer/draft is limited to what that user's role may
# see — no new data access, no permission bypass. The API key lives only here on
# the backend (env GEMINI_API_KEY) and is never exposed to the frontend.
from __future__ import annotations

import os
import json
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Depends

from .auth import get_current_user

router = APIRouter()


def _today_sgt() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
# The backend calls its own public endpoints so all role-scoping/logic is reused.
SELF_BASE = os.environ.get("BACKEND_SELF_URL", "https://vmms-backend-sg.onrender.com").rstrip("/")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# ---- Tool catalogue: name -> (HTTP path builder, description, parameters) ----
# Every path is an existing GET endpoint. site_name is resolved to an id here so
# the model can speak in plain site names.

TOOL_DECLARATIONS = [
    {"name": "get_day_attendance",
     "description": "Present count and leave breakdown (MC/AL/UL) for a single date. Optional site name to narrow to one site.",
     "parameters": {"type": "object", "properties": {
         "date": {"type": "string", "description": "Date YYYY-MM-DD"},
         "site_name": {"type": "string", "description": "Optional exact or partial site name"}},
         "required": ["date"]}},
    {"name": "get_attendance_report",
     "description": "Attendance and leave per worker across a date range. Use for questions like 'who took the most leave' or leave totals over a period.",
     "parameters": {"type": "object", "properties": {
         "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
         "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
         "site_name": {"type": "string", "description": "Optional site name"}},
         "required": ["date_from", "date_to"]}},
    {"name": "get_manhours",
     "description": "Normal and OT manhours for a calendar month, per worker and per site. Use for hours of one worker, one/two sites, or comparisons.",
     "parameters": {"type": "object", "properties": {
         "month": {"type": "string", "description": "Month YYYY-MM"}},
         "required": ["month"]}},
    {"name": "get_resource_summary",
     "description": "Monthly resource usage rolled up from DPRs for one site.",
     "parameters": {"type": "object", "properties": {
         "site_name": {"type": "string", "description": "Site name"},
         "month": {"type": "string", "description": "Month YYYY-MM"}},
         "required": ["site_name", "month"]}},
    {"name": "get_dashboard",
     "description": "Top-line KPIs for today (allocated, present, on leave, OT month-to-date).",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_missing_dpr",
     "description": "Active sites that have no Daily Progress Report recently.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "list_sites",
     "description": "List site names and ids the user can access. Use to resolve or confirm a site name.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "draft_allocation_message",
     "description": "Generate the ready-to-send WhatsApp allocation message for a date.",
     "parameters": {"type": "object", "properties": {
         "date": {"type": "string", "description": "Date YYYY-MM-DD"}}, "required": ["date"]}},
    {"name": "draft_site_update_message",
     "description": "Generate the WhatsApp site-update message for a date and site.",
     "parameters": {"type": "object", "properties": {
         "date": {"type": "string", "description": "Date YYYY-MM-DD"},
         "site_name": {"type": "string", "description": "Site name"}},
         "required": ["date", "site_name"]}},
    {"name": "draft_leave_message",
     "description": "Generate the WhatsApp message listing who is on leave (home leave).",
     "parameters": {"type": "object", "properties": {
         "date": {"type": "string", "description": "Optional date YYYY-MM-DD"}}}},
    {"name": "draft_requests_message",
     "description": "Generate the WhatsApp message summarising outstanding manpower requests.",
     "parameters": {"type": "object", "properties": {}}},
]

SYSTEM_PROMPT = (
    "You are the VCMS Assistant for Vortex Construction Management System, used by a "
    "Singapore-based construction team. Answer questions about workforce, attendance, "
    "leave (MC/AL/UL), manhours (normal and OT), allocations, requests, resources and "
    "Daily Progress Reports, and draft WhatsApp messages when asked.\n"
    "RULES:\n"
    "- Only use the provided tools for facts. Never invent numbers, names or dates. If a "
    "tool returns nothing, say so plainly.\n"
    "- Dates are DD/MM/YYYY in replies; pass YYYY-MM-DD to tools. Today's date is given below.\n"
    "- Be concise and practical, like a site manager. Use short lines or small lists. "
    "Metric units, SGD, times in SGT.\n"
    "- The user only receives data their role permits; do not claim access to more.\n"
    "- For WhatsApp drafts, return the message text exactly as the tool provides it, in a "
    "code-style block, and remind the user to review before sending. You never send messages.\n"
)


async def _resolve_site_id(client: httpx.AsyncClient, headers: dict, site_name: str):
    if not site_name:
        return ""
    try:
        r = await client.get(f"{SELF_BASE}/api/v1/sites", headers=headers)
        if r.status_code != 200:
            return ""
        want = site_name.strip().lower()
        rows = r.json() or []
        for s in rows:
            if str(s.get("site_name", "")).strip().lower() == want:
                return s.get("id", "")
        for s in rows:  # fall back to partial match
            if want in str(s.get("site_name", "")).strip().lower():
                return s.get("id", "")
    except Exception:
        pass
    return ""


async def _run_tool(client, headers, name, args):
    """Execute one tool as an HTTP GET to an existing endpoint. Returns JSON-able."""
    args = args or {}
    async def get(path, params=None):
        r = await client.get(f"{SELF_BASE}{path}", params=params or {}, headers=headers)
        if r.status_code != 200:
            return {"error": f"data unavailable ({r.status_code})"}
        try:
            return r.json()
        except Exception:
            return {"error": "bad response"}

    if name == "get_dashboard":
        return await get("/api/v1/dashboard")
    if name == "get_missing_dpr":
        return await get("/api/v1/dpr/missing")
    if name == "list_sites":
        data = await get("/api/v1/sites")
        if isinstance(data, list):
            return [{"id": s.get("id"), "site_name": s.get("site_name")} for s in data]
        return data
    if name == "get_manhours":
        return await get("/api/v1/reports/manhours", {"month": args.get("month", "")})
    if name == "get_day_attendance":
        sid = await _resolve_site_id(client, headers, args.get("site_name", ""))
        return await get("/api/v1/attendance", {"date": args.get("date", ""), "site_id": sid})
    if name == "get_attendance_report":
        sid = await _resolve_site_id(client, headers, args.get("site_name", ""))
        return await get("/api/v1/reports/attendance",
                         {"dfrom": args.get("date_from", ""), "dto": args.get("date_to", ""), "site_id": sid})
    if name == "get_resource_summary":
        sid = await _resolve_site_id(client, headers, args.get("site_name", ""))
        if not sid:
            return {"error": "site not found"}
        return await get("/api/v1/resource-summary", {"site_id": sid, "month": args.get("month", "")})
    if name == "draft_allocation_message":
        return await get("/api/v1/messages/allocation", {"date": args.get("date", "")})
    if name == "draft_site_update_message":
        sid = await _resolve_site_id(client, headers, args.get("site_name", ""))
        if not sid:
            return {"error": "site not found"}
        return await get("/api/v1/messages/update", {"date": args.get("date", ""), "site_id": sid})
    if name == "draft_leave_message":
        return await get("/api/v1/messages/home_leave", {"date": args.get("date", "")})
    if name == "draft_requests_message":
        return await get("/api/v1/messages/requests")
    return {"error": f"unknown tool {name}"}


def _cap(obj, limit=6000):
    """Keep tool payloads small so the model stays fast and cheap."""
    try:
        s = json.dumps(obj, default=str)
    except Exception:
        s = str(obj)
    if len(s) > limit:
        s = s[:limit] + " …(truncated)"
    return s


async def run_assistant(message: str, user: dict, today: str) -> dict:
    """Main entry: returns {'reply': str} or {'reply': str, 'error': True}."""
    message = (message or "").strip()
    if not message:
        return {"reply": "Ask me about attendance, leave, manhours, resources or a WhatsApp draft."}
    if not GEMINI_API_KEY:
        return {"reply": "The assistant isn't switched on yet — an administrator needs to add the "
                         "GEMINI_API_KEY on the server.", "error": True}

    token = user.get("token", "")
    role = user.get("role", "")
    headers = {"Authorization": f"Bearer {token}"}
    sys_text = SYSTEM_PROMPT + f"\nToday: {today}. The user's role is: {role}."

    contents = [{"role": "user", "parts": [{"text": message}]}]
    tools = [{"function_declarations": TOOL_DECLARATIONS}]
    payload = {
        "system_instruction": {"parts": [{"text": sys_text}]},
        "tools": tools,
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 900},
    }

    async with httpx.AsyncClient(timeout=45) as client:
        for _ in range(5):  # up to 5 tool rounds
            payload["contents"] = contents
            try:
                r = await client.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=payload)
            except Exception:
                return {"reply": "The assistant timed out. Please try again.", "error": True}
            if r.status_code != 200:
                return {"reply": "The assistant is unavailable right now. Please try again shortly.",
                        "error": True}
            data = r.json()
            cand = (data.get("candidates") or [{}])[0]
            parts = (cand.get("content") or {}).get("parts") or []
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if calls:
                contents.append({"role": "model", "parts": parts})
                tool_parts = []
                for call in calls:
                    result = await _run_tool(client, headers, call.get("name", ""), call.get("args") or {})
                    tool_parts.append({"functionResponse": {
                        "name": call.get("name", ""),
                        "response": {"result": _cap(result)}}})
                contents.append({"role": "user", "parts": tool_parts})
                continue
            text = "".join(p.get("text", "") for p in parts).strip()
            return {"reply": text or "I couldn't find an answer for that."}
    return {"reply": "That needed too many steps. Please narrow the question.", "error": True}


@router.post("/api/v1/assistant")
async def assistant_endpoint(payload: dict, user: dict = Depends(get_current_user)):
    """Chat assistant. Body: {"message": "..."}. Role-scoped via the user's token."""
    return await run_assistant((payload or {}).get("message", ""), user, _today_sgt())
