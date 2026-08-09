from __future__ import annotations

class ProjectRepository:
    SELECT = ("id,project_code,project_name,description,client_name,"
              "planned_start_date,planned_finish_date,actual_start_date,"
              "actual_finish_date,status,timezone,default_calendar_id,"
              "created_by,created_at,updated_at,archived_at")

    def __init__(self, client, rest_url: str, headers: dict):
        self.client = client
        self.url = f"{rest_url}/projects"
        self.headers = headers

    async def list(self, status: str | None = None):
        params = {"select": self.SELECT, "order": "project_name.asc"}
        if status:
            params["status"] = f"eq.{status}"
        response = await self.client.get(self.url, params=params, headers=self.headers)
        return response

    async def get(self, project_id: str):
        return await self.client.get(
            self.url,
            params={"id": f"eq.{project_id}", "select": self.SELECT, "limit": "1"},
            headers=self.headers,
        )

    async def create(self, values: dict):
        return await self.client.post(
            self.url,
            headers={**self.headers, "Prefer": "return=representation"},
            json=values,
        )

    async def update(self, project_id: str, values: dict):
        return await self.client.patch(
            self.url,
            params={"id": f"eq.{project_id}"},
            headers={**self.headers, "Prefer": "return=representation"},
            json=values,
        )
