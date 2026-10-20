"""Worker corrections through the public API, with the database boundary simulated."""
from copy import deepcopy
from contextlib import asynccontextmanager
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def api(monkeypatch):
    state = {
        "row": {"id": "worker-1", "worker_code": "OLD01", "name": "Original Name", "status": "active"},
        "role": "admin", "writes": [], "audits": [], "read_status": 200,
    }

    def transport(request):
        assert request.headers["Authorization"] == "Bearer test"
        if request.url.path.endswith("/audit_log"):
            state["audits"].append(json.loads(request.content))
            return httpx.Response(201, json={})
        assert request.url.path.endswith("/workers")
        if request.method == "GET":
            return httpx.Response(state["read_status"], json=[deepcopy(state["row"])] if state["row"] else [])
        assert request.method == "PATCH"
        assert request.url.params["id"] == "eq.worker-1"
        payload = json.loads(request.content)
        assert "id" not in payload
        if payload.get("worker_code") == "TAKEN":
            return httpx.Response(409, json={"code": "23505"})
        state["writes"].append(payload)
        state["row"].update(payload)
        return httpx.Response(200, json=[deepcopy(state["row"])])

    @asynccontextmanager
    async def shared_client():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            yield client

    def current_user():
        return {"role": state["role"], "token": "test", "user_id": "user-1"}

    monkeypatch.setattr(main, "REST", "https://test.supabase.co/rest/v1")
    monkeypatch.setattr(main, "shared_client", shared_client)
    main.app.dependency_overrides[main.get_current_user] = current_user
    try:
        with TestClient(main.app) as client:
            yield client, state
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)


@pytest.mark.parametrize("role", sorted(main.FULL_ROLES))
def test_correction_preserves_identity_and_audits_old_and_new_values(api, role):
    client, state = api
    state["role"] = role
    response = client.patch("/api/v1/workers/worker-1", json={"worker_code": " emp-050 ", "name": " Corrected Name "})
    assert response.status_code == 200
    assert response.json()["id"] == "worker-1"
    assert response.json()["worker_code"] == "EMP-050"
    assert response.json()["name"] == "Corrected Name"
    assert state["row"]["status"] == "active"
    audit = state["audits"][0]
    assert audit["entity_id"] == "worker-1" and audit["user_id"] == "user-1"
    assert audit["old_value"]["worker_code"] == "OLD01"
    assert audit["old_value"]["name"] == "Original Name"
    assert audit["new_value"] == {"worker_code": "EMP-050", "name": "Corrected Name"}


def test_duplicate_id_rejects_entire_correction(api):
    client, state = api
    response = client.patch("/api/v1/workers/worker-1", json={"worker_code": "taken", "name": "Changed"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Worker ID TAKEN already exists"
    assert state["row"]["name"] == "Original Name"
    assert not state["writes"] and not state["audits"]


@pytest.mark.parametrize("role", sorted(set(main.ALL_ROLES) - set(main.FULL_ROLES)))
def test_other_roles_cannot_correct_workers(api, role):
    client, state = api
    state["role"] = role
    assert client.patch("/api/v1/workers/worker-1", json={"worker_code": "NEW", "name": "Changed"}).status_code == 403
    assert not state["writes"] and not state["audits"]


@pytest.mark.parametrize("field", ["worker_code", "name"])
@pytest.mark.parametrize("value", ["", "  ", None])
def test_explicit_empty_identity_values_are_rejected(api, field, value):
    client, state = api
    assert client.patch("/api/v1/workers/worker-1", json={field: value, "status": "inactive"}).status_code == 400
    assert not state["writes"]


def test_partial_updates_keep_omitted_identity_fields(api):
    client, state = api
    assert client.patch("/api/v1/workers/worker-1", json={"name": "New Name"}).status_code == 200
    assert state["row"]["worker_code"] == "OLD01"
    assert client.patch("/api/v1/workers/worker-1", json={"status": "on_leave"}).status_code == 200
    assert state["row"]["name"] == "New Name"


def test_missing_worker_and_database_read_failure_are_distinct(api):
    client, state = api
    state["read_status"] = 503
    assert client.patch("/api/v1/workers/worker-1", json={"worker_code": "NEW"}).status_code == 503
    state["read_status"] = 200
    state["row"] = None
    assert client.patch("/api/v1/workers/worker-1", json={"worker_code": "NEW"}).status_code == 404
    assert not state["writes"] and not state["audits"]
