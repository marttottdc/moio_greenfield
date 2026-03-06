"""
Event Router.

Routes emitted events to matching flows based on trigger_event configuration.
Evaluates conditions and starts flow executions.
"""

from __future__ import annotations

import logging
import operator
from typing import Any, Optional
from uuid import UUID

from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

OPERATORS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "contains": lambda a, b: b in a if a else False,
    "in": lambda a, b: a in b if b else False,
    "exists": lambda a, b: (a is not None) == b,
    "startswith": lambda a, b: str(a).startswith(str(b)) if a else False,
    "endswith": lambda a, b: str(a).endswith(str(b)) if a else False,
}


def _get_nested_value(data: dict, path: str) -> Any:
    """
    Get a nested value from a dict using dot notation.
    
    Example: _get_nested_value({"payload": {"amount": 100}}, "payload.amount") -> 100
    """
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def _evaluate_condition(condition: dict, event_envelope: dict) -> bool:
    """
    Evaluate a single condition against the event envelope.
    
    Condition format: {"field": "payload.amount", "op": "gt", "value": 1000}
    or simplified: {"payload.amount": {"gt": 1000}}
    """
    field: str = ""
    op_name: str = ""
    expected: Any = None
    
    if "field" in condition and "op" in condition:
        field = condition["field"]
        op_name = condition["op"]
        expected = condition.get("value")
    else:
        found = False
        for f, ops in condition.items():
            if isinstance(ops, dict):
                for o, v in ops.items():
                    field = f
                    op_name = o
                    expected = v
                    found = True
                    break
                if found:
                    break
            else:
                return False
        if not found:
            return False
    
    op_func = OPERATORS.get(op_name)
    if not op_func:
        logger.warning(f"Unknown operator: {op_name}")
        return False
    
    actual = _get_nested_value(event_envelope, field)
    
    try:
        return op_func(actual, expected)
    except Exception as e:
        logger.debug(f"Condition evaluation failed: {e}")
        return False


def _evaluate_conditions(conditions: dict | list, event_envelope: dict) -> bool:
    """
    Evaluate all conditions against the event envelope.
    
    All conditions must be satisfied (AND logic).
    """
    if not conditions:
        return True
    
    if isinstance(conditions, list):
        for condition in conditions:
            if not _evaluate_condition(condition, event_envelope):
                return False
        return True
    
    if isinstance(conditions, dict):
        for field, ops in conditions.items():
            if isinstance(ops, dict):
                for op_name, expected in ops.items():
                    condition = {"field": field, "op": op_name, "value": expected}
                    if not _evaluate_condition(condition, event_envelope):
                        return False
            else:
                condition = {"field": field, "op": "eq", "value": ops}
                if not _evaluate_condition(condition, event_envelope):
                    return False
        return True
    
    return True


def _build_event_envelope(event) -> dict:
    """Build the canonical event envelope for condition evaluation and flow input."""
    return {
        "id": str(event.id),
        "name": event.name,
        "tenant_id": str(event.tenant_id),
        "actor": event.actor,
        "entity": event.entity,
        "payload": event.payload,
        "occurred_at": event.occurred_at.isoformat(),
        "source": event.source,
        "correlation_id": str(event.correlation_id) if event.correlation_id else None,
    }


def _extract_flow_input_payload(event_envelope: Any) -> dict:
    """Extract the *domain payload* that should become FlowRun `$input.body`.

    We persist/transport events as an "envelope" (id/name/tenant/...) whose
    `payload` is meant to be the domain data. In some ingestion paths, the stored
    `payload` itself is another transport envelope (e.g. includes `path`,
    `headers`, `method`) that nests the real domain payload under `body` (or
    occasionally `payload` / `data`).

    Flow runtime contract:
    - `ctx.Event.input.body` (aka `input.body`) must be the domain payload
    - the full transport envelope remains available via `ctx.trigger.data`
      (and thus `ctx.Event.data` for backwards compatibility)
    """

    if not isinstance(event_envelope, dict):
        return {}

    raw = event_envelope.get("payload")
    if not isinstance(raw, dict):
        return {}

    def _looks_like_transport(d: dict) -> bool:
        # Heuristic: if this dict contains common transport/meta keys, it's not the domain payload.
        transport_keys = {
            "path",
            "url",
            "method",
            "headers",
            "query",
            "params",
            "route",
            "topic",
            "event",
            "event_name",
            "timestamp",
            "occurred_at",
            "source",
            "tenant_id",
            "correlation_id",
        }
        keys = set(d.keys())
        # If it has body + at least one other key, it's very likely an envelope.
        if "body" in keys and len(keys - {"body"}) > 0:
            return True
        return bool(keys & transport_keys)

    current: Any = raw
    for _ in range(3):
        if not isinstance(current, dict):
            break

        # Common case: {path: "...", body: {...}}.
        body = current.get("body")
        if isinstance(body, dict) and _looks_like_transport(current):
            return body

        # Other wrappers: {payload: {...}} or {data: {...}} around an envelope.
        nested_payload = current.get("payload")
        if isinstance(nested_payload, dict) and _looks_like_transport(current):
            current = nested_payload
            continue

        nested_data = current.get("data")
        if isinstance(nested_data, dict) and _looks_like_transport(current):
            current = nested_data
            continue

        break

    # Default: stored payload is already the domain payload.
    return raw


def _find_matching_flows(event_name: str, tenant_pk: int, include_armed_drafts: bool = True) -> list:
    """
    Find all flows with event triggers matching the event name.
    
    Looks for flows where:
    - trigger_type is 'event' (in the published or testing version)
    - trigger config event_name matches
    - For production: flow has published_version (is_enabled)
    - For preview: version is in TESTING status
    - tenant matches
    
    Uses the new FlowVersion model with FSM status.
    """
    from flows.models import Flow, FlowVersion, FlowVersionStatus
    
    matching_flows = []
    
    flows = Flow.objects.filter(
        tenant_id=tenant_pk,
    ).select_related("published_version").prefetch_related("versions")
    
    for flow in flows:
        versions_to_check = []
        
        # Published version for production
        if flow.published_version:
            versions_to_check.append(("production", flow.published_version))
        
        # Testing version for preview/sandbox
        if include_armed_drafts:
            testing_version = flow.versions.filter(status=FlowVersionStatus.TESTING).first()
            if testing_version:
                versions_to_check.append(("preview", testing_version))
        
        for execution_mode, version in versions_to_check:
            graph_data = version.graph or {}
            nodes = graph_data.get("nodes", [])
            
            for node in nodes:
                kind = node.get("kind", "")
                if kind == "trigger_event":
                    config = node.get("config", {})
                    trigger_event_name = (
                        config.get("event") or 
                        config.get("event_name") or 
                        config.get("topic")
                    )
                    if trigger_event_name == event_name:
                        conditions = config.get("conditions", {})
                        matching_flows.append({
                            "flow": flow,
                            "version": version,
                            "trigger_config": config,
                            "conditions": conditions,
                            "execution_mode": execution_mode,
                        })
                    break
    
    return matching_flows


def _start_flow_execution(
    flow, 
    version, 
    event_envelope: dict, 
    trigger_metadata: dict,
    execution_mode: str = "production"
) -> Optional[str]:
    """Start a flow execution for the matched event.
    
    Args:
        flow: The Flow instance
        version: The FlowVersion to execute
        event_envelope: The event data
        trigger_metadata: Metadata about the trigger
        execution_mode: "production" or "preview" (sandbox mode for armed drafts)
    """
    try:
        from flows.tasks import execute_flow, execute_sandbox_preview
        
        trigger_metadata["execution_mode"] = execution_mode
        trigger_metadata["version_id"] = str(version.id)
        trigger_metadata["event"] = event_envelope

        # Runtime contract: input.body must be the event payload (not the full envelope).
        event_payload = _extract_flow_input_payload(event_envelope)
        
        if execution_mode == "preview":
            from flows.models import FlowExecution
            import uuid
            
            run_id = str(uuid.uuid4())
            execution = FlowExecution.objects.create(
                flow=flow,
                status="pending",
                input_data=event_envelope,
                trigger_source="event_preview",
                execution_context={
                    "preview_mode": True,
                    "sandbox": True,
                    "preview_run_id": run_id,
                    "version_id": str(version.id),
                    "event_name": event_envelope.get("name"),
                    "trigger_metadata": trigger_metadata,
                    "preview_active": True,
                },
            )
            
            task = execute_sandbox_preview.delay(
                flow_id=str(flow.id),
                run_id=run_id,
                trigger_payload=event_payload,
                graph_payload=version.graph,
                execution_id=str(execution.id),
                trigger_metadata=trigger_metadata,
            )
            
            logger.info(
                f"Sandbox preview execution started: flow={flow.name}, event={event_envelope['name']}, "
                f"version={version.label}, run_id={run_id}, task_id={task.id}"
            )
        else:
            task = execute_flow.delay(
                str(flow.id),
                event_payload,
                trigger_source="event",
                trigger_metadata=trigger_metadata,
            )
            
            logger.info(
                f"Flow execution started: flow={flow.name}, event={event_envelope['name']}, "
                f"task_id={task.id}"
            )
        
        return task.id
    except Exception as e:
        logger.error(f"Failed to start flow execution: {e}", exc_info=True)
        return None


def route_event(event_id: UUID) -> list:
    """
    Route an event to matching flows.
    
    This is the main entry point called after event emission.
    
    1. Load the event from EventLog
    2. Find flows with matching event triggers
    3. Evaluate conditions
    4. Start flow executions for matching flows
    5. Mark event as routed
    
    Args:
        event_id: UUID of the EventLog entry
    
    Returns:
        List of flow execution task IDs
    """
    from flows.models import EventLog
    
    try:
        event = EventLog.objects.get(id=event_id)
    except EventLog.DoesNotExist:
        logger.error(f"Event not found: {event_id}")
        return []
    
    if event.routed:
        logger.info(f"Event already routed: {event_id}")
        return event.flow_executions
    
    event_envelope = _build_event_envelope(event)
    # EventLog.tenant_id is stored as a UUID (Tenant.tenant_code), but Flow.tenant_id is an int FK.
    # Resolve tenant_code -> Tenant.pk before filtering flows.
    from portal.models import Tenant
    tenant = Tenant.objects.filter(tenant_code=event.tenant_id).only("id").first()
    if not tenant:
        logger.warning(
            "No tenant found for event tenant_id=%s (expected Tenant.tenant_code UUID).",
            event.tenant_id,
        )
        event.mark_routed([])
        return []

    matching_flows = _find_matching_flows(event.name, tenant.id)
    
    if not matching_flows:
        logger.debug(f"No matching flows for event: {event.name}")
        event.mark_routed([])
        return []
    
    execution_ids = []
    
    for match in matching_flows:
        flow = match["flow"]
        version = match["version"]
        conditions = match["conditions"]
        execution_mode = match.get("execution_mode", "production")
        
        if not _evaluate_conditions(conditions, event_envelope):
            logger.debug(
                f"Conditions not met for flow {flow.name}, event {event.name}"
            )
            continue
        
        trigger_metadata = {
            "trigger_type": "event",
            "event_id": str(event.id),
            "event_name": event.name,
            "flow_version_id": str(version.id),
        }
        
        task_id = _start_flow_execution(
            flow, version, event_envelope, trigger_metadata, execution_mode
        )
        if task_id:
            execution_ids.append(task_id)
    
    event.mark_routed(execution_ids)
    
    logger.info(
        f"Event routed: {event.name} -> {len(execution_ids)} flow(s) triggered"
    )
    
    return execution_ids
