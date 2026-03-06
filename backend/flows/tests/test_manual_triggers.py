import json
import uuid
from copy import deepcopy

import pytest
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import RequestFactory
from django.urls import reverse

from flows.core.compiler import compile_flow_graph, register_definition
from flows.core.connector import flow_connector, trigger_manual_flow
from flows.models import Flow, FlowExecution, FlowGraphVersion
from flows.views import manual_run
from portal.signals import create_internal_contact


SIMPLE_MANUAL_GRAPH = {
    "nodes": [
        {
            "id": "trig-1",
            "kind": "trigger_manual",
            "name": "Manual",
            "config": {"sample": "payload"},
        },
        {
            "id": "out-1",
            "kind": "output_function",
            "name": "Output",
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
    "meta": {"draft": False},
}


@pytest.fixture(autouse=True)
def reset_flow_connector():
    flow_connector.flows.clear()
    flow_connector.trigger_registry.clear()
    flow_connector.manual_trigger_index.clear()
    yield
    flow_connector.flows.clear()
    flow_connector.trigger_registry.clear()
    flow_connector.manual_trigger_index.clear()


@pytest.fixture(autouse=True)
def disable_internal_contact_signal():
    User = get_user_model()
    post_save.disconnect(create_internal_contact, sender=User)
    yield
    post_save.connect(create_internal_contact, sender=User)


@pytest.fixture
def user_factory(tenant):
    User = get_user_model()

    def factory(**overrides):
        email = overrides.pop("email", f"user-{uuid.uuid4().hex[:8]}@example.com")
        username = overrides.pop("username", f"user-{uuid.uuid4().hex[:8]}")
        password = overrides.pop("password", "test-pass")
        extra = overrides.copy()
        extra.setdefault("tenant", tenant)

        return User.objects.create_user(
            email=email,
            username=username,
            password=password,
            **extra,
        )

    return factory


def test_manual_trigger_creates_execution(flow_factory):
    flow = flow_factory(is_enabled=True)
    version = FlowGraphVersion.objects.create(
        flow=flow,
        major=1,
        minor=0,
        is_published=True,
        graph=deepcopy(SIMPLE_MANUAL_GRAPH),
    )

    definition = compile_flow_graph(flow, version.graph, version=version)
    register_definition(flow, definition)

    payload = {"foo": "bar"}
    result = trigger_manual_flow(str(flow.id), payload)

    assert result["triggered"] is True
    assert flow_connector.manual_trigger_index.get(str(flow.id))
    assert str(flow.id) in flow_connector.trigger_registry.get(f"manual:{flow.id}", [])

    executions = FlowExecution.objects.filter(flow=flow)
    assert executions.count() == 1
    execution = executions.first()
    assert execution.trigger_source == "manual"
    assert execution.input_data == payload


def test_manual_trigger_skips_disabled_flow(flow_factory):
    flow = flow_factory(is_enabled=False)
    version = FlowGraphVersion.objects.create(
        flow=flow,
        major=1,
        minor=0,
        is_published=True,
        graph=deepcopy(SIMPLE_MANUAL_GRAPH),
    )

    definition = compile_flow_graph(flow, version.graph, version=version)
    register_definition(flow, definition)

    result = trigger_manual_flow(str(flow.id), {"foo": "bar"})

    assert result["triggered"] is False
    assert result["reason"] == "disabled"
    assert FlowExecution.objects.filter(flow=flow).count() == 0


def test_manual_run_view_triggers_flow(tenant, flow_factory, user_factory):
    user = user_factory(email="owner@example.com", username="owner", tenant=tenant)

    flow = flow_factory(is_enabled=True, tenant=tenant, created_by=user)
    version = FlowGraphVersion.objects.create(
        flow=flow,
        major=1,
        minor=0,
        is_published=True,
        graph=deepcopy(SIMPLE_MANUAL_GRAPH),
    )

    definition = compile_flow_graph(flow, version.graph, version=version)
    register_definition(flow, definition)

    url = reverse("flows:manual_run", args=[flow.id])
    request = RequestFactory().post(
        url,
        data=json.dumps({"payload": {"hello": "world"}}),
        content_type="application/json",
    )
    request.user = user

    response = manual_run(request, str(flow.id))

    assert response.status_code == 200
    trigger_header = response.headers.get("HX-Trigger")
    assert trigger_header
    detail = json.loads(trigger_header)["flow-manual-run"]
    assert detail["triggered"] is True
    execution_id = detail.get("execution_id")
    assert execution_id

    execution = FlowExecution.objects.get(id=execution_id)
    assert execution.trigger_source == "manual"
    assert execution.input_data == {"hello": "world"}


def test_manual_run_view_skips_disabled_flow(tenant, flow_factory, user_factory):
    user = user_factory(email="owner2@example.com", username="owner2", tenant=tenant)

    flow = flow_factory(is_enabled=False, tenant=tenant, created_by=user)
    version = FlowGraphVersion.objects.create(
        flow=flow,
        major=1,
        minor=0,
        is_published=True,
        graph=deepcopy(SIMPLE_MANUAL_GRAPH),
    )

    definition = compile_flow_graph(flow, version.graph, version=version)
    register_definition(flow, definition)

    url = reverse("flows:manual_run", args=[flow.id])
    request = RequestFactory().post(
        url,
        data=json.dumps({"payload": {"hello": "world"}}),
        content_type="application/json",
    )
    request.user = user

    response = manual_run(request, str(flow.id))

    assert response.status_code == 200
    detail = json.loads(response.headers.get("HX-Trigger"))["flow-manual-run"]
    assert detail["triggered"] is False
    assert detail["reason"] == "disabled"
    assert FlowExecution.objects.filter(flow=flow).count() == 0
