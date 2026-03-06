"""Compile persisted builder graphs into FlowConnector definitions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Optional

from django.utils.text import slugify

from ..models import Flow, FlowVersion, FlowVersionStatus
from .connector import (
    FlowDefinition,
    FlowHandler,
    FlowTrigger,
    HandlerType,
    TriggerType,
    flow_connector,
)
from .schema import FlowGraph


class FlowCompilationError(Exception):
    """Raised when a graph cannot be transformed into a runtime definition."""


_TRIGGER_KIND_MAP: Dict[str, TriggerType] = {
    "trigger_manual": TriggerType.MANUAL,
    "trigger_webhook": TriggerType.WEBHOOK,
    "trigger_scheduled": TriggerType.SCHEDULED,
    "trigger_event": TriggerType.EVENT,
}


def _extract_trigger_id(flow: Flow, kind: str, config: Dict[str, Any]) -> str:
    """Derive a stable trigger identifier for the runtime connector."""

    config = config or {}

    if kind == "trigger_manual":
        return config.get("external_id") or f"manual:{flow.id}"

    if kind == "trigger_webhook":
        candidate = config.get("webhook_id") or config.get("webhook_name")
        if candidate:
            return str(candidate)
        raise FlowCompilationError("Webhook trigger requires `webhook_id` or `webhook_name` in its config")

    if kind == "trigger_scheduled":
        candidate = config.get("schedule") or config.get("schedule_name")
        if candidate:
            return str(candidate)
        cron = config.get("cron_expression")
        if cron:
            slug = slugify(cron)
            return f"schedule:{slug}" if slug else cron
        raise FlowCompilationError("Scheduled trigger requires `schedule_name` or `cron_expression` in its config")

    if kind == "trigger_event":
        candidate = config.get("event") or config.get("event_name") or config.get("topic")
        if candidate:
            return str(candidate)
        raise FlowCompilationError("Event trigger requires `event_name` or `topic` in its config")

    raise FlowCompilationError(f"Unsupported trigger kind '{kind}'")


def _ensure_output(nodes: Iterable[Dict[str, Any]]) -> None:
    if not any(node.get("kind", "").startswith("output_") for node in nodes):
        raise FlowCompilationError("Flow graph must contain at least one output node")


def compile_flow_graph(
    flow: Flow,
    graph: Dict[str, Any],
    *,
    version: Optional[FlowVersion] = None,
) -> FlowDefinition:
    """Translate a graph payload into a :class:`FlowDefinition`."""

    graph_model = FlowGraph.model_validate(graph)
    nodes = [node.model_dump(mode="python") for node in graph_model.nodes]

    trigger_nodes = [node for node in nodes if node.get("kind", "").startswith("trigger_")]
    if not trigger_nodes:
        raise FlowCompilationError("Flow graph requires a trigger node")
    if len(trigger_nodes) > 1:
        raise FlowCompilationError(
            f"Flow graph must contain exactly one trigger node, found {len(trigger_nodes)}"
        )

    trigger_node = trigger_nodes[0]
    trigger_kind = trigger_node.get("kind")
    trigger_type = _TRIGGER_KIND_MAP.get(trigger_kind)
    if trigger_type is None:
        raise FlowCompilationError(f"Unsupported trigger node kind '{trigger_kind}'")

    trigger_config = deepcopy(trigger_node.get("config") or {})
    trigger_id = _extract_trigger_id(flow, trigger_kind, trigger_config)
    conditions = trigger_config.pop("conditions", None)
    if not isinstance(conditions, dict):
        conditions = {}

    _ensure_output(nodes)

    handler_parameters = {
        "flow_id": str(flow.id),
        "trigger_type": trigger_type.value,
    }
    if version is not None:
        handler_parameters["graph_version_id"] = str(version.id)

    handler = FlowHandler(
        handler_type=HandlerType.FUNCTION,
        handler_path="flows.handlers.flow_connector_handler",
        parameters=handler_parameters,
    )

    trigger = FlowTrigger(
        trigger_type=trigger_type,
        trigger_id=trigger_id,
        conditions=conditions,
        metadata=trigger_config,
    )

    definition = FlowDefinition(
        flow_id=str(flow.id),
        name=flow.name,
        description=flow.description,
        trigger=trigger,
        handlers=[handler],
        enabled=flow.is_enabled,
        tenant_id=str(flow.tenant_id) if flow.tenant_id else None,
        created_by=str(flow.created_by_id) if flow.created_by_id else None,
    )

    return definition


def compile_published_version(flow: Flow) -> FlowDefinition:
    """Compile the published version for *flow*."""

    version = flow.published_version
    if version is None:
        version = flow.versions.filter(status=FlowVersionStatus.PUBLISHED).first()
    if version is None:
        raise FlowCompilationError("Flow does not have a published graph")
    return compile_flow_graph(flow, version.graph, version=version)


def register_definition(flow: Flow, definition: FlowDefinition) -> None:
    """Register *definition* with the shared connector for *flow*."""

    flow_connector.unregister_flow(str(flow.id))
    flow_connector.register_flow(definition)


def unregister_flow(flow: Flow) -> None:
    """Remove *flow* from the shared connector if it was registered."""

    flow_connector.unregister_flow(str(flow.id))


__all__ = [
    "FlowCompilationError",
    "compile_flow_graph",
    "compile_published_version",
    "register_definition",
    "unregister_flow",
]
