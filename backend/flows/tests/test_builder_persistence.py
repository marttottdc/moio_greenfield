import json
from copy import deepcopy

import pytest
from django.test import RequestFactory

from flows.models import FlowExecution, FlowGraphVersion
from flows.views import preview, preview_stream, publish, save


GRAPH_TEMPLATE = {
    "nodes": [
        {
            "id": "trig-1",
            "kind": "trigger_scheduled",
            "name": "Scheduled",
            "x": 0,
            "y": 0,
            "config": {},
        },
        {
            "id": "agent-1",
            "kind": "agent",
            "name": "Agent",
            "x": 160,
            "y": 0,
            "config": {"instructions": "Assist"},
        },
        {
            "id": "out-1",
            "kind": "output_function",
            "name": "Function",
            "x": 320,
            "y": 0,
            "config": {},
        },
    ],
    "edges": [
        {
            "id": "edge-1",
            "source": "trig-1",
            "target": "agent-1",
            "source_port": "out",
            "target_port": "in",
        },
        {
            "id": "edge-2",
            "source": "agent-1",
            "target": "out-1",
            "source_port": "out",
            "target_port": "in",
        },
    ],
    "meta": {"draft": True},
}


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def graph_payload():
    return deepcopy(GRAPH_TEMPLATE)


def _create_version(flow, graph):
    return FlowGraphVersion.objects.create(
        flow=flow,
        major=1,
        minor=0,
        is_published=False,
        graph=deepcopy(graph),
    )


def test_save_updates_existing_draft(rf, flow_factory, graph_payload):
    flow = flow_factory()
    draft = _create_version(flow, graph_payload)

    request = rf.post(
        "/save/",
        data=json.dumps({"graph": graph_payload}),
        content_type="application/json",
    )

    response = save(request, flow.id)

    assert response.status_code == 204

    draft.refresh_from_db()
    assert draft.minor == 1
    assert draft.graph["nodes"][1]["config"]["instructions"] == "Assist"
    trigger_ports = draft.graph["nodes"][0]["ports"]["out"][0]
    assert "trigger" in trigger_ports["schema"]["description"].lower()
    agent_input = draft.graph["nodes"][1]["ports"]["in"][0]
    assert agent_input["schema"]["properties"]["message"]["type"] == "string"
    assert agent_input["schema_preview"]

    trigger = json.loads(response["HX-Trigger"])
    assert trigger["flow-saved"]["version"].startswith("v1.")


def test_publish_promotes_draft_and_activates_flow(rf, flow_factory, graph_payload):
    flow = flow_factory(status="testing", is_enabled=False)
    draft = _create_version(flow, graph_payload)

    request = rf.post(
        "/publish/",
        data=json.dumps({"graph": graph_payload}),
        content_type="application/json",
    )

    response = publish(request, flow.id)

    assert response.status_code == 204

    draft.refresh_from_db()
    flow.refresh_from_db()

    assert draft.is_published is True
    assert flow.status == "active"
    assert flow.is_enabled is True

    trigger = json.loads(response["HX-Trigger"])
    assert trigger["flow-published"]["is_published"] is True


def test_preview_stream_emits_timeline(monkeypatch, rf, flow_factory, graph_payload):
    flow = flow_factory()
    _create_version(flow, graph_payload)

    timeline = [
        {
            "node_id": "trig-1",
                "name": "Scheduled",
            "started_at": "2024-01-01T00:00:00Z",
            "finished_at": "2024-01-01T00:00:01Z",
            "input": {"foo": "bar"},
            "output": {"step": "trigger"},
        },
        {
            "node_id": "agent-1",
            "name": "Agent",
            "started_at": "2024-01-01T00:00:01Z",
            "finished_at": "2024-01-01T00:00:02Z",
            "input": {"foo": "bar"},
            "output": {"result": "ok"},
        },
    ]

    def fake_preview_execute(graph, payload, tenant_id=None):
        return {"context": {"final": True}, "timeline": timeline}

    monkeypatch.setattr("flows.views.preview_execute", fake_preview_execute)

    request = rf.post(
        "/preview/",
        data=json.dumps({"graph": graph_payload, "payload": {"foo": "bar"}, "run_id": "run-1"}),
        content_type="application/json",
    )

    response = preview(request, flow.id)

    assert response.status_code == 204

    trigger = json.loads(response["HX-Trigger"])
    assert trigger["preview-started"]["run_id"] == "run-1"

    execution = (
        FlowExecution.objects.filter(execution_context__preview_run_id="run-1")
        .order_by("-started_at")
        .first()
    )
    assert execution is not None
    assert execution.status == "success"
    assert execution.output_data == {"final": True}
    assert execution.execution_context["timeline"] == timeline

    stream_request = rf.get("/preview/stream/", {"run_id": "run-1"})
    stream_response = preview_stream(stream_request, flow.id)

    body = b"".join(stream_response.streaming_content).decode("utf-8")
    assert "Status" in body
    assert "Scheduled" in body or "Agent" in body
