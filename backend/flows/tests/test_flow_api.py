import json
import uuid
from copy import deepcopy

import pytest
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.urls import reverse
from django.utils import translation
from django.utils.timezone import now
from datetime import timedelta

from flows.models import Flow, FlowExecution, FlowGraphVersion
from flows.core.registry import NodeDefinition, registry as runtime_registry
from central_hub.signals import create_internal_contact

GRAPH_PAYLOAD = {
    "nodes": [
        {
            "id": "trig-1",
            "kind": "trigger_manual",
            "name": "Manual",
            "x": 0,
            "y": 0,
            "config": {"sample": "payload"},
        },
        {
            "id": "out-1",
            "kind": "output_function",
            "name": "Output",
            "x": 160,
            "y": 0,
            "config": {},
        },
    ],
    "edges": [
        {
            "id": "edge-1",
            "source": "trig-1",
            "target": "out-1",
            "source_port": "out",
            "target_port": "in",
        }
    ],
    "meta": {"draft": True},
}


@pytest.fixture(autouse=True)
def force_english_locale():
    with translation.override("en"):
        yield


@pytest.fixture
def auth_client(client, tenant):
    User = get_user_model()
    post_save.disconnect(create_internal_contact, sender=User)
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create_user(
        email=f"flow-owner-{suffix}@example.com",
        username=f"flow-owner-{suffix}",
        password="secret",
        tenant=tenant,
    )
    client.force_login(user)
    try:
        yield client, user
    finally:
        post_save.connect(create_internal_contact, sender=User)


@pytest.fixture
def flow_with_version(flow_factory, auth_client):
    _, user = auth_client
    flow = flow_factory(tenant=user.tenant, created_by=user)
    FlowGraphVersion.objects.create(
        flow=flow,
        major=1,
        minor=0,
        is_published=False,
        graph=deepcopy(GRAPH_PAYLOAD),
    )
    return flow


def test_api_flow_list_returns_stats(auth_client, flow_with_version):
    client, _ = auth_client
    response = client.get(reverse("flows_api:api_flow_list"))
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert any(item["id"] == str(flow_with_version.id) for item in data["flows"])
    assert "stats" in data


def test_api_flow_list_includes_execution_stats(auth_client, flow_with_version):
    client, _ = auth_client

    flow_with_version.execution_count = 7
    flow_with_version.last_execution_status = "success"
    flow_with_version.last_executed_at = flow_with_version.updated_at
    flow_with_version.save(
        update_fields=["execution_count", "last_execution_status", "last_executed_at", "updated_at"]
    )

    response = client.get(reverse("flows_api:api_flow_list"))
    assert response.status_code == 200
    data = response.json()
    flow_payload = next(
        item for item in data["flows"] if item["id"] == str(flow_with_version.id)
    )
    assert flow_payload["execution_count"] == 7
    assert flow_payload["last_execution_status"] == "success"
    assert flow_payload["last_executed_at"] is not None


def test_api_flow_list_accepts_post(auth_client):
    client, user = auth_client
    payload = {"name": "API Flow", "description": "created via API"}

    response = client.post(reverse("flows_api:api_flow_list"), data=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["id"]

    flow = Flow.objects.get(id=data["id"])
    assert flow.tenant == user.tenant
    assert FlowGraphVersion.objects.filter(flow=flow).exists()


def test_api_flow_detail_includes_graph(monkeypatch, auth_client, flow_with_version):
    client, _ = auth_client
    monkeypatch.setattr("flows.views.WebhookConfig", None, raising=False)
    response = client.get(
        reverse("flows_api:api_flow_detail", args=[flow_with_version.id])
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["flow"]["id"] == str(flow_with_version.id)
    assert payload["graph"]["nodes"]
    assert payload["api"]["save"]


def test_api_flow_detail_allows_patch_updates_flow(auth_client, flow_with_version):
    client, _ = auth_client
    url = reverse("flows_api:api_flow_detail", args=[flow_with_version.id])
    payload = {
        "name": "Updated Flow Name",
        "description": "New description",
        "status": "inactive",
        "is_enabled": False,
    }

    response = client.patch(url, data=json.dumps(payload), content_type="application/json")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["flow"]["name"] == payload["name"]
    assert data["flow"]["description"] == payload["description"]
    assert data["flow"]["status"] == payload["status"]
    assert data["flow"]["is_enabled"] is payload["is_enabled"]

    flow_with_version.refresh_from_db()
    assert flow_with_version.name == payload["name"]
    assert flow_with_version.description == payload["description"]
    assert flow_with_version.status == payload["status"]
    assert flow_with_version.is_enabled is payload["is_enabled"]


def test_api_flow_save_returns_version(auth_client, flow_with_version):
    client, _ = auth_client
    url = reverse("flows_api:api_flow_save", args=[flow_with_version.id])
    response = client.post(
        url,
        data=json.dumps({"graph": deepcopy(GRAPH_PAYLOAD)}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["version"]["label"].startswith("v")


def test_api_flow_validate_accepts_valid_graph(auth_client, flow_with_version):
    client, _ = auth_client
    url = reverse("flows_api:api_flow_validate", args=[flow_with_version.id])
    response = client.post(
        url,
        data=json.dumps({"graph": deepcopy(GRAPH_PAYLOAD)}),
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["graph"]["nodes"]


def test_api_flow_validate_reports_errors(auth_client, flow_with_version):
    client, _ = auth_client
    url = reverse("flows_api:api_flow_validate", args=[flow_with_version.id])
    invalid_graph = {"nodes": [{"id": "node-1"}], "edges": []}
    response = client.post(
        url,
        data=json.dumps({"graph": invalid_graph}),
        content_type="application/json",
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert "errors" in payload


def test_api_flow_manual_run_returns_detail(monkeypatch, auth_client, flow_with_version):
    client, _ = auth_client

    def fake_trigger(flow_id, payload):
        return {"triggered": True, "trigger_key": "manual", "canonical_key": flow_id}

    monkeypatch.setattr("flows.views.trigger_manual_flow_helper", fake_trigger)

    url = reverse("flows_api:api_flow_manual_run", args=[flow_with_version.id])
    response = client.post(url, data=json.dumps({"payload": {"foo": "bar"}}), content_type="application/json")
    assert response.status_code == 200
    detail = response.json()["detail"]
    assert detail["triggered"] is True


def test_api_flow_preview_returns_execution(monkeypatch, auth_client, flow_with_version):
    client, _ = auth_client
    timeline = [
        {
            "node_id": "trig-1",
            "name": "Manual",
            "started_at": "2024-01-01T00:00:00Z",
            "finished_at": "2024-01-01T00:00:01Z",
            "input": {"foo": "bar"},
            "output": {"step": "trigger"},
        }
    ]

    def fake_preview(graph, payload, tenant_id=None):
        return {"context": {"result": True}, "timeline": timeline}

    monkeypatch.setattr("flows.views.preview_execute", fake_preview)

    url = reverse("flows_api:api_flow_preview", args=[flow_with_version.id])
    response = client.post(
        url,
        data=json.dumps({"payload": {"foo": "bar"}}),
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    run_id = payload["run_id"]
    assert payload["execution"]["timeline"]

    status_url = reverse("flows_api:api_flow_preview_status", args=[flow_with_version.id, run_id])
    status_response = client.get(status_url)
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["execution"]["timeline"]
    assert FlowExecution.objects.filter(
        execution_context__preview_run_id=run_id
    ).exists()


def test_api_flow_execution_stats_scopes_to_flow(auth_client, flow_with_version):
    client, user = auth_client

    other_flow = Flow.objects.create(
        tenant=user.tenant,
        name=f"Other-{uuid.uuid4().hex[:6]}",
        description="",
        status="active",
        created_by=user,
    )

    # One recent success for target flow
    FlowExecution.objects.create(
        flow=flow_with_version,
        status="success",
        input_data={},
        trigger_source="manual",
        duration_ms=123,
        execution_context={"execution_mode": "production"},
    )

    # One recent failed for other flow (must not be counted)
    FlowExecution.objects.create(
        flow=other_flow,
        status="failed",
        input_data={},
        trigger_source="webhook",
        duration_ms=999,
        execution_context={"execution_mode": "production"},
    )

    url = reverse("flows_api:api_flow_execution_stats", args=[flow_with_version.id])
    response = client.get(url)
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["flow_id"] == str(flow_with_version.id)
    assert payload["total_all_time"] >= 1
    assert payload["by_status"].get("success") == 1
    assert payload["by_status"].get("failed") in (None, 0)


def test_api_flow_execution_stats_days_filters_window(auth_client, flow_with_version):
    client, _ = auth_client

    old_exec = FlowExecution.objects.create(
        flow=flow_with_version,
        status="success",
        input_data={},
        trigger_source="manual",
        duration_ms=10,
        execution_context={},
    )
    FlowExecution.objects.filter(id=old_exec.id).update(started_at=now() - timedelta(days=30))

    recent_exec = FlowExecution.objects.create(
        flow=flow_with_version,
        status="failed",
        input_data={},
        trigger_source="manual",
        duration_ms=20,
        execution_context={},
    )
    FlowExecution.objects.filter(id=recent_exec.id).update(started_at=now() - timedelta(days=1))

    url = reverse("flows_api:api_flow_execution_stats", args=[flow_with_version.id])
    response = client.get(url + "?days=7")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_window"] == 1
    assert payload["by_status"].get("failed") == 1

def test_api_node_definitions_returns_catalog(auth_client):
    client, _ = auth_client
    response = client.get(reverse("flows_api:api_flow_node_definitions"))
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["stage"]
    assert "agent" in payload["definitions"]
    agent = payload["definitions"]["agent"]
    assert agent["kind"] == "agent"
    assert agent["ports"]["in"]


def test_api_node_definitions_honours_stage_param(auth_client):
    client, _ = auth_client
    kind = "test_stage_api_node"
    definition = NodeDefinition(
        kind=kind,
        title="Stage API Node",
        icon="code",
        category="Testing",
        stages={"dev": True, "prod": False},
    )
    runtime_registry.register(definition)

    try:
        response = client.get(
            reverse("flows_api:api_flow_node_definitions"),
            {"stage": "prod"},
        )
        assert response.status_code == 200
        payload = response.json()
        node = payload["definitions"][kind]
        assert node["stage_limited"] is True
        assert node["is_available"] is False
        assert node["stages"] == {"dev": True, "prod": False}
    finally:
        runtime_registry._definitions.pop(kind, None)
