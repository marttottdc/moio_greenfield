"""
Celery tasks for flow execution
"""
import html
import json
import logging
import time
from celery import shared_task
from django.utils.timezone import now

from moio_platform.settings import FLOWS_Q
from websockets_app.services.publisher import WebSocketEventPublisher
from .models import Flow, FlowExecution, FlowVersionStatus
from .core.schema import validate_graph_payload
from .core.runtime import FlowRun
from .validation import normalize_graph


logger = logging.getLogger(__name__)


def execute_flow_sync(
    flow_id: str,
    payload: dict | None = None,
    *,
    trigger_source: str = "webhook",
    trigger_metadata: dict | None = None,
    version_id: str | None = None,
    sandbox: bool | None = None,
):
    """
    Synchronously execute a specific flow version with the given payload.
    Emits WebSocket events for real-time monitoring.
    
    This function executes a single version of a flow. For webhooks that need to
    trigger both published and testing versions, use execute_flow_webhook which
    calls this function twice (once for each version).
    
    Args:
        flow_id: UUID of the flow to execute
        payload: Input data for the flow (typically webhook payload)
        trigger_source: Source that triggered the execution (webhook, api, manual, etc.)
        trigger_metadata: Additional metadata about the trigger
        version_id: Optional specific version ID to execute
        sandbox: Override sandbox mode (None = auto-detect based on version status)
    
    Returns:
        dict: Execution result snapshot
    
    Note:
        Draft versions are never executed. Only published (production) and 
        testing (sandbox) versions can be triggered by webhooks/events.
    """
    payload = dict(payload or {})
    trigger_metadata = dict(trigger_metadata or {})
    
    try:
        flow = Flow.objects.get(id=flow_id)
    except Flow.DoesNotExist:
        logger.error(f"Flow not found: {flow_id}")
        return {"error": f"Flow not found: {flow_id}"}
    
    # If specific version requested, use it
    if version_id:
        version = flow.versions.filter(id=version_id).first()
        if not version:
            logger.error(f"Version not found: {version_id}")
            return {"error": f"Version not found: {version_id}"}
    else:
        # Default: try published version first
        version = flow.published_version
        if not version:
            version = flow.versions.filter(status=FlowVersionStatus.PUBLISHED).first()
        # If no published, try testing version
        if not version:
            version = flow.versions.filter(status=FlowVersionStatus.TESTING).first()
    
    if not version:
        logger.error(f"No executable version found for flow: {flow_id} (only published/testing versions can execute)")
        return {"error": f"No executable version found for flow: {flow_id}"}
    
    # Draft versions cannot be executed via webhooks/events
    if version.status == FlowVersionStatus.DRAFT:
        logger.error(f"Cannot execute draft version: {version.id}")
        return {"error": f"Draft versions cannot be executed via webhooks/events"}
    
    # Determine sandbox mode: testing versions run in sandbox, published in production
    if sandbox is not None:
        is_sandbox = sandbox
    else:
        is_sandbox = version.status == FlowVersionStatus.TESTING
    
    # Determine execution_mode for WebSocket events
    execution_mode = "testing" if is_sandbox else "production"
    
    logger.info(f"=" * 80)
    logger.info(f"FLOW EXECUTION START (via {trigger_source})")
    logger.info(f"Flow: {flow.name} (ID: {flow_id})")
    logger.info(f"Version: {version.label}")
    logger.info(f"Sandbox mode: {is_sandbox}")
    logger.info(f"Input payload: {json.dumps(payload, indent=2)}")
    logger.info(f"=" * 80)
    
    # Create execution log
    status_log = [{"status": "running", "at": now().isoformat()}]
    trace_id = trigger_metadata.get("trace_id") if trigger_metadata else None
    
    execution_context = {
        "graph_version": version.label,
        "version_id": str(version.id),
        "version_status": version.status,
        "status_log": status_log,
        "trigger_source": trigger_source,
        "sandbox": is_sandbox,
        "execution_mode": execution_mode,
        "trace_id": trace_id,
    }
    if trigger_metadata:
        execution_context["trigger_metadata"] = trigger_metadata
    
    logger.info(f"[FLOW_TRACE:{trace_id or 'direct'}] EXECUTION_START flow={flow.name} version={version.label} mode={execution_mode}")

    exec_log = FlowExecution.objects.create(
        flow=flow,
        status="running",
        input_data=payload,
        trigger_source=trigger_source,
        execution_context=execution_context,
    )
    
    tenant_id = str(flow.tenant_id) if flow.tenant_id else "public"
    
    def publish_event(event_type: str, payload_data: dict):
        """Publish execution event via WebSocket."""
        payload_data["execution_mode"] = execution_mode
        WebSocketEventPublisher.publish_flow_preview_event(
            tenant_id=tenant_id,
            flow_id=flow_id,
            run_id=str(exec_log.id),
            event_type=event_type,
            payload=payload_data,
        )
    
    timeline: list[dict] = []
    
    def emit_step(step: dict, index: int):
        """Callback for each step executed."""
        timeline.append(step)
        node_id = step.get("node_id", "")
        node_name = step.get("node_label", step.get("node_type", ""))
        step_status = step.get("status", "completed")
        
        if step_status == "error":
            publish_event("node_error", {
                "node_id": node_id,
                "node_name": node_name,
                "error": step.get("error", "Unknown error"),
                "step_index": index,
            })
        else:
            publish_event("node_finished", {
                "node_id": node_id,
                "node_name": node_name,
                "output": step.get("output"),
                "step_index": index,
            })
    
    t0 = time.time()
    publish_event("execution_started", {"flow_id": flow_id, "execution_id": str(exec_log.id)})
    
    try:
        graph = validate_graph_payload(version.graph).as_dict()
        trigger_obj = {"source": trigger_source, "metadata": trigger_metadata}
        # If the trigger metadata includes a full event envelope, expose it as trigger.data for expressions/templates.
        if isinstance(trigger_metadata, dict) and isinstance(trigger_metadata.get("event"), dict):
            trigger_obj["data"] = trigger_metadata["event"]

        run = FlowRun(
            graph,
            payload,
            config=getattr(version, "config_values", None),
            tenant_id=tenant_id,
            trigger=trigger_obj,
            on_step=emit_step,
            sandbox=is_sandbox,
            execution_id=str(exec_log.id),
        )
        result = run.execute()

        exec_log.status = "success"
        exec_log.output_data = result
        exec_log.error_data = {}
        status_log.append({"status": "success", "at": now().isoformat()})
        
        duration_ms = int((time.time() - t0) * 1000)
        logger.info(f"[FLOW_TRACE:{trace_id or 'direct'}] EXECUTION_SUCCESS flow={flow.name} duration_ms={duration_ms}")
        logger.debug(f"Output: {json.dumps(result, indent=2)}")

        flow.execution_count += 1
        flow.last_executed_at = now()
        flow.last_execution_status = "success"
        flow.save(update_fields=["execution_count", "last_executed_at", "last_execution_status"])

        exec_log.execution_context["status_log"] = status_log
        exec_log.execution_context["timeline"] = timeline
        exec_log.save(update_fields=[
            "status",
            "output_data",
            "error_data",
            "execution_context",
        ])

        publish_event("execution_completed", {
            "status": "success",
            "duration_ms": duration_ms,
            "execution_id": str(exec_log.id),
        })

        return result

    except Exception as e:
        error_message = str(e)
        logger.error(f"[FLOW_TRACE:{trace_id or 'direct'}] EXECUTION_FAILED flow={flow.name} error={error_message}", exc_info=True)

        exec_log.status = "failed"
        snapshot = run.snapshot() if "run" in locals() else {}
        exec_log.output_data = snapshot
        exec_log.error_data = {
            "message": error_message,
            "type": e.__class__.__name__,
        }
        status_log.append({"status": "failed", "at": now().isoformat()})

        duration_ms = int((time.time() - t0) * 1000)
        logger.error(f"[FLOW_TRACE:{trace_id or 'direct'}] duration_ms={duration_ms}")

        # Update flow execution stats
        flow.execution_count += 1
        flow.last_executed_at = now()
        flow.last_execution_status = "failed"
        flow.save(update_fields=["execution_count", "last_executed_at", "last_execution_status"])

        exec_log.execution_context["status_log"] = status_log
        exec_log.execution_context["timeline"] = timeline
        exec_log.save(update_fields=[
            "status",
            "output_data",
            "error_data",
            "execution_context",
        ])

        publish_event("execution_completed", {
            "status": "failed",
            "duration_ms": duration_ms,
            "error": error_message,
            "execution_id": str(exec_log.id),
        })

        return {"error": error_message}

    finally:
        exec_log.completed_at = now()
        exec_log.duration_ms = int((time.time() - t0) * 1000)
        exec_log.execution_context["status_log"] = status_log
        exec_log.save(update_fields=["completed_at", "duration_ms", "execution_context"])

        # Emit canonical flow execution completion event (best-effort).
        try:
            from moio_platform.core.events import emit_event
            from moio_platform.core.events.snapshots import snapshot_flow_execution

            tenant_code = flow.tenant.tenant_code if getattr(flow, "tenant", None) else None
            if tenant_code:
                ctx = exec_log.execution_context or {}
                emit_event(
                    name="flow.execution_completed",
                    tenant_id=tenant_code,
                    actor={"type": "system", "id": "flows.tasks.execute_flow_sync"},
                    entity={"type": "flow_execution", "id": str(exec_log.id)},
                    payload={
                        "flow_id": str(flow.id),
                        "execution_id": str(exec_log.id),
                        "status": exec_log.status,
                        "trigger_source": exec_log.trigger_source or ctx.get("trigger_source"),
                        "execution_mode": ctx.get("execution_mode"),
                        "sandbox": ctx.get("sandbox"),
                        "started_at": exec_log.started_at.isoformat() if exec_log.started_at else None,
                        "completed_at": exec_log.completed_at.isoformat() if exec_log.completed_at else None,
                        "duration_ms": exec_log.duration_ms,
                        "version_id": ctx.get("version_id"),
                        "trace_id": ctx.get("trace_id"),
                        "input": exec_log.input_data or {},
                        "output": exec_log.output_data or {},
                        "error": exec_log.error_data or {},
                        "execution": snapshot_flow_execution(exec_log),
                    },
                    source="flows",
                )
        except Exception:
            pass


@shared_task(name="flows.tasks.execute_flow", queue=FLOWS_Q)
def execute_flow(
    flow_id: str,
    payload: dict = None,
    trigger_source: str = "task",
    trigger_metadata: dict | None = None,
    version_id: str | None = None,
    sandbox: bool | None = None,
):
    """
    Celery task wrapper for flow execution.
    Delegates to execute_flow_sync for the actual execution logic.
    
    Args:
        flow_id: UUID of the flow to execute
        payload: Input data for the flow
        trigger_source: Source that triggered the execution
        trigger_metadata: Additional metadata about the trigger
        version_id: Optional specific version ID to execute
        sandbox: Override sandbox mode (None = auto-detect)
    
    Returns:
        dict: Execution result
    """
    return execute_flow_sync(
        flow_id,
        payload,
        trigger_source=trigger_source,
        trigger_metadata=trigger_metadata,
        version_id=version_id,
        sandbox=sandbox,
    )


@shared_task(name="flows.tasks.preview_flow", queue=FLOWS_Q)
def preview_flow(
    flow_id: str,
    run_id: str,
    trigger_payload: dict | None,
    *,
    graph_payload: dict | None = None,
    execution_id: str,
):
    """Execute a preview run asynchronously and emit live events via WebSocket channel layer."""

    from .views import _format_preview_entry_html, _graph_model_to_dict, _preview_summary_html
    from jsonschema import validate as jsonschema_validate
    from jsonschema import ValidationError as JSONSchemaError

    # Preview executions always use "preview" mode
    execution_mode = "preview"

    def publish_event(event_type: str, payload: dict):
        """Publish preview event via WebSocket channel layer."""
        payload["execution_mode"] = execution_mode
        WebSocketEventPublisher.publish_flow_preview_event(
            tenant_id=tenant_id,
            flow_id=flow_id,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
        )

    try:
        flow = Flow.objects.get(id=flow_id)
    except Flow.DoesNotExist:
        logger.error("Preview flow not found: %s", flow_id)
        return

    tenant_id = str(flow.tenant_id) if flow.tenant_id else "public"

    execution = FlowExecution.objects.filter(id=execution_id, flow=flow).first()
    if not execution:
        logger.error("Preview execution not found: %s", execution_id)
        return

    status_log = execution.execution_context.get("status_log") or []
    status_log.append({"status": "running", "at": now().isoformat()})
    execution.status = "running"
    execution.execution_context["status_log"] = status_log
    execution.execution_context["preview_active"] = True
    execution.execution_context["execution_mode"] = execution_mode
    execution.execution_context["preview_started_at"] = (
        execution.execution_context.get("preview_started_at") or now().isoformat()
    )
    execution.save(update_fields=["status", "execution_context"])

    publish_event("stream_started", {"run_id": run_id, "flow_id": flow_id})

    version = flow.versions.order_by("-created_at").first()
    if graph_payload is None:
        if not version:
            publish_event("error", {"message": "No graph available to preview."})
            return
        graph_payload = version.graph

    try:
        graph_model = normalize_graph(graph_payload)
        graph = _graph_model_to_dict(graph_model)
    except Exception as exc:  # pragma: no cover - validation errors
        error_msg = html.escape(str(exc))
        execution.status = "failed"
        execution.error_data = {"message": str(exc)}
        status_log.append({"status": "failed", "at": now().isoformat()})
        execution.execution_context["status_log"] = status_log
        execution.execution_context["preview_active"] = False
        execution.execution_context["preview_finished_at"] = now().isoformat()
        execution.completed_at = now()
        execution.save(
            update_fields=[
                "status",
                "error_data",
                "execution_context",
                "completed_at",
            ]
        )
        publish_event("error", {"message": f"Graph error: {error_msg}"})
        return

    # If this graph uses a webhook trigger and it carries an expected_schema, validate the preview payload
    # before executing. This keeps preview behavior aligned with production webhook ingestion.
    webhook_nodes = [
        node for node in (graph.get("nodes") or [])
        if isinstance(node, dict) and node.get("kind") == "trigger_webhook"
    ]
    if webhook_nodes:
        expected_schema_raw = (webhook_nodes[0].get("config") or {}).get("expected_schema")
        if expected_schema_raw and isinstance(trigger_payload, dict):
            try:
                schema = json.loads(expected_schema_raw) if isinstance(expected_schema_raw, str) else expected_schema_raw
                if isinstance(schema, dict):
                    jsonschema_validate(trigger_payload, schema)
            except JSONSchemaError as exc:
                execution.status = "failed"
                execution.error_data = {"message": f"Schema validation failed: {exc}"}
                status_log.append({"status": "failed", "at": now().isoformat()})
                execution.execution_context["status_log"] = status_log
                execution.execution_context["preview_active"] = False
                execution.execution_context["preview_finished_at"] = now().isoformat()
                execution.completed_at = now()
                execution.save(
                    update_fields=[
                        "status",
                        "error_data",
                        "execution_context",
                        "completed_at",
                    ]
                )
                publish_event("error", {"message": f"Schema validation failed: {html.escape(str(exc))}"})
                return
            except Exception as exc:
                # If schema parsing fails, fail loud so misconfigured schemas are fixed.
                execution.status = "failed"
                execution.error_data = {"message": f"Invalid expected_schema: {exc}"}
                status_log.append({"status": "failed", "at": now().isoformat()})
                execution.execution_context["status_log"] = status_log
                execution.execution_context["preview_active"] = False
                execution.execution_context["preview_finished_at"] = now().isoformat()
                execution.completed_at = now()
                execution.save(
                    update_fields=[
                        "status",
                        "error_data",
                        "execution_context",
                        "completed_at",
                    ]
                )
                publish_event("error", {"message": f"Invalid expected_schema: {html.escape(str(exc))}"})
                return

    timeline: list[dict] = []

    def emit_step(step: dict, index: int):
        timeline.append(step)
        node_id = step.get("node_id", "")
        node_name = step.get("node_label", step.get("node_type", ""))
        step_status = step.get("status", "completed")
        
        if step_status == "error":
            publish_event("node_error", {
                "node_id": node_id,
                "node_name": node_name,
                "error": step.get("error", "Unknown error"),
                "step_index": index,
                "step": step,
            })
        else:
            publish_event("node_finished", {
                "node_id": node_id,
                "node_name": node_name,
                "output": step.get("output"),
                "step_index": index,
                "step": step,
            })

    t0 = time.time()
    try:
        run = FlowRun(
            graph,
            trigger_payload or {},
            config=getattr(version, "config_values", {}) if version else {},
            tenant_id=tenant_id,
            trigger={"source": "preview", "run_id": run_id},
            on_step=emit_step,
        )
        result = run.execute()
        execution.status = "success"
        execution.output_data = result.get("snapshot", {}) or result
        execution.error_data = {}
        status_log.append({"status": "success", "at": now().isoformat()})
    except Exception as exc:  # pragma: no cover - runtime errors
        execution.status = "failed"
        execution.error_data = {"message": str(exc)}
        execution.output_data = execution.output_data or {}
        status_log.append({"status": "failed", "at": now().isoformat()})
    finally:
        execution.execution_context["timeline"] = timeline
        execution.execution_context["status_log"] = status_log
        execution.execution_context["preview_active"] = False
        execution.execution_context["preview_finished_at"] = now().isoformat()
        execution.completed_at = now()
        execution.duration_ms = int((time.time() - t0) * 1000)
        execution.save()

    publish_event("preview_completed", {
        "status": execution.status,
        "duration_ms": execution.duration_ms,
        "summary": {
            "steps_count": len(timeline),
            "status": execution.status,
        },
    })


@shared_task(name="flows.tasks.execute_sandbox_preview", queue=FLOWS_Q)
def execute_sandbox_preview(
    flow_id: str,
    run_id: str,
    trigger_payload: dict | None,
    *,
    graph_payload: dict | None = None,
    execution_id: str,
    trigger_metadata: dict | None = None,
):
    """
    Execute a flow in sandbox mode for armed draft preview.
    
    This is triggered when an armed draft receives a real event. The execution
    runs in sandbox mode where external actions (WhatsApp, email, HTTP, CRM) are
    simulated instead of executed. Results are streamed via WebSocket.
    
    Args:
        flow_id: UUID of the flow
        run_id: Unique run identifier for WebSocket channel
        trigger_payload: Event payload that triggered the execution
        graph_payload: Optional graph to use (falls back to armed version)
        execution_id: UUID of the FlowExecution record
    """
    from .views import _graph_model_to_dict
    from jsonschema import validate as jsonschema_validate
    from jsonschema import ValidationError as JSONSchemaError

    # Sandbox previews run in "testing" mode
    execution_mode = "testing"

    def publish_event(event_type: str, payload: dict):
        """Publish preview event via WebSocket channel layer."""
        payload["execution_mode"] = execution_mode
        WebSocketEventPublisher.publish_flow_preview_event(
            tenant_id=tenant_id,
            flow_id=flow_id,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
        )

    try:
        flow = Flow.objects.get(id=flow_id)
    except Flow.DoesNotExist:
        logger.error("Sandbox preview flow not found: %s", flow_id)
        return

    tenant_id = str(flow.tenant_id) if flow.tenant_id else "public"

    execution = FlowExecution.objects.filter(id=execution_id, flow=flow).first()
    if not execution:
        logger.error("Sandbox preview execution not found: %s", execution_id)
        return

    status_log = execution.execution_context.get("status_log") or []
    status_log.append({"status": "running", "at": now().isoformat()})
    execution.status = "running"
    execution.execution_context["status_log"] = status_log
    execution.execution_context["preview_active"] = True
    execution.execution_context["execution_mode"] = execution_mode
    execution.execution_context["preview_started_at"] = now().isoformat()
    execution.save(update_fields=["status", "execution_context"])

    publish_event("sandbox_started", {
        "run_id": run_id,
        "flow_id": flow_id,
        "event_name": trigger_payload.get("name") if trigger_payload else None,
        "sandbox": True,
    })

    if graph_payload is None:
        # Look for version in testing status (armed)
        armed_version = flow.versions.filter(status=FlowVersionStatus.TESTING).first()
        if armed_version:
            graph_payload = armed_version.graph
        else:
            version = flow.versions.order_by("-created_at").first()
            if not version:
                publish_event("error", {"message": "No graph available for sandbox preview."})
                return
            graph_payload = version.graph
    # Use the same version source to supply deterministic config values.
    config_values = {}
    if "armed_version" in locals() and armed_version:
        config_values = getattr(armed_version, "config_values", {}) or {}
    elif "version" in locals() and version:
        config_values = getattr(version, "config_values", {}) or {}

    try:
        graph_model = normalize_graph(graph_payload)
        graph = _graph_model_to_dict(graph_model)
    except Exception as exc:
        error_msg = str(exc)
        execution.status = "failed"
        execution.error_data = {"message": error_msg}
        status_log.append({"status": "failed", "at": now().isoformat()})
        execution.execution_context["status_log"] = status_log
        execution.execution_context["preview_active"] = False
        execution.execution_context["preview_finished_at"] = now().isoformat()
        execution.completed_at = now()
        execution.save(update_fields=["status", "error_data", "execution_context", "completed_at"])
        publish_event("error", {"message": f"Graph validation error: {error_msg}"})
        return

    # Align sandbox preview with production webhook behavior: validate payload against webhook expected_schema
    # when the graph uses a webhook trigger.
    webhook_nodes = [
        node for node in (graph.get("nodes") or [])
        if isinstance(node, dict) and node.get("kind") == "trigger_webhook"
    ]
    if webhook_nodes:
        expected_schema_raw = (webhook_nodes[0].get("config") or {}).get("expected_schema")
        if expected_schema_raw and isinstance(trigger_payload, dict):
            try:
                schema = json.loads(expected_schema_raw) if isinstance(expected_schema_raw, str) else expected_schema_raw
                if isinstance(schema, dict):
                    jsonschema_validate(trigger_payload, schema)
            except JSONSchemaError as exc:
                error_msg = f"Schema validation failed: {exc}"
                execution.status = "failed"
                execution.error_data = {"message": error_msg}
                status_log.append({"status": "failed", "at": now().isoformat()})
                execution.execution_context["status_log"] = status_log
                execution.execution_context["preview_active"] = False
                execution.execution_context["preview_finished_at"] = now().isoformat()
                execution.completed_at = now()
                execution.save(update_fields=["status", "error_data", "execution_context", "completed_at"])
                publish_event("error", {"message": error_msg})
                return
            except Exception as exc:
                error_msg = f"Invalid expected_schema: {exc}"
                execution.status = "failed"
                execution.error_data = {"message": error_msg}
                status_log.append({"status": "failed", "at": now().isoformat()})
                execution.execution_context["status_log"] = status_log
                execution.execution_context["preview_active"] = False
                execution.execution_context["preview_finished_at"] = now().isoformat()
                execution.completed_at = now()
                execution.save(update_fields=["status", "error_data", "execution_context", "completed_at"])
                publish_event("error", {"message": error_msg})
                return

    timeline: list[dict] = []

    def emit_step(step: dict, index: int):
        timeline.append(step)
        node_id = step.get("node_id", "")
        node_name = step.get("node_label", step.get("name", step.get("kind", "")))
        step_status = step.get("status", "success")
        is_sandbox = step.get("meta", {}).get("sandbox", False)
        
        event_data = {
            "node_id": node_id,
            "node_name": node_name,
            "step_index": index,
            "step": step,
            "sandbox": is_sandbox,
        }
        
        if step_status == "error":
            event_data["error"] = step.get("error", "Unknown error")
            publish_event("node_error", event_data)
        else:
            event_data["output"] = step.get("output")
            publish_event("node_finished", event_data)

    t0 = time.time()
    try:
        run = FlowRun(
            graph,
            trigger_payload or {},
            config=config_values,
            tenant_id=tenant_id,
            trigger={"source": "event_preview", "run_id": run_id, "data": (trigger_metadata or {}).get("event")},
            on_step=emit_step,
            sandbox=True,
        )
        result = run.execute()
        execution.status = "success"
        execution.output_data = result
        execution.error_data = {}
        status_log.append({"status": "success", "at": now().isoformat()})
    except Exception as exc:
        execution.status = "failed"
        execution.error_data = {"message": str(exc)}
        execution.output_data = {}
        status_log.append({"status": "failed", "at": now().isoformat()})
        logger.error("Sandbox preview execution failed: %s", exc, exc_info=True)
    finally:
        execution.execution_context["timeline"] = timeline
        execution.execution_context["status_log"] = status_log
        execution.execution_context["preview_active"] = False
        execution.execution_context["preview_finished_at"] = now().isoformat()
        execution.completed_at = now()
        execution.duration_ms = int((time.time() - t0) * 1000)
        execution.save()

    publish_event("sandbox_completed", {
        "status": execution.status,
        "duration_ms": execution.duration_ms,
        "sandbox": True,
        "summary": {
            "steps_count": len(timeline),
            "status": execution.status,
        },
    })
    
    logger.info(
        f"Sandbox preview completed: flow={flow.name}, run_id={run_id}, "
        f"status={execution.status}, steps={len(timeline)}, duration={execution.duration_ms}ms"
    )


@shared_task(name="flows.tasks.execute_scheduled_flow", queue=FLOWS_Q)
def execute_scheduled_flow(
    schedule_id: str,
    flow_id: str,
    tenant_id: str,
):
    """
    Celery task to execute a flow triggered by a schedule.
    Called by Celery Beat when a FlowSchedule fires.
    
    Args:
        schedule_id: UUID of the FlowSchedule
        flow_id: UUID of the Flow to execute
        tenant_id: UUID of the Tenant
    
    Returns:
        dict: Execution result
    """
    from .models import FlowSchedule
    from django.utils.timezone import now as tz_now
    
    logger.info(f"Executing scheduled flow: flow_id={flow_id}, schedule_id={schedule_id}")
    
    try:
        schedule = FlowSchedule.objects.get(id=schedule_id)
    except FlowSchedule.DoesNotExist:
        logger.error(f"FlowSchedule not found: {schedule_id}")
        return {"error": f"FlowSchedule not found: {schedule_id}"}
    
    if not schedule.is_active:
        logger.warning(f"FlowSchedule is inactive: {schedule_id}")
        return {"error": f"FlowSchedule is inactive: {schedule_id}"}
    
    schedule.last_run_at = tz_now()
    schedule.save(update_fields=['last_run_at'])
    
    trigger_metadata = {
        "schedule_id": str(schedule_id),
        "schedule_type": schedule.schedule_type,
        "cron_expression": schedule.cron_expression or None,
        "interval_seconds": schedule.interval_seconds,
        "timezone": schedule.timezone,
    }
    
    result = execute_flow_sync(
        flow_id,
        payload={},
        trigger_source="schedule",
        trigger_metadata=trigger_metadata,
    )
    
    if schedule.schedule_type == FlowSchedule.SCHEDULE_TYPE_ONE_OFF:
        schedule.is_active = False
        schedule.save(update_fields=['is_active'])
        from .core.schedule_service import ScheduleService
        ScheduleService.delete_schedule(schedule)
        logger.info(f"One-off schedule {schedule_id} completed and deactivated")
    
    return result


@shared_task(name="flows.tasks.execute_scheduled_task", queue=FLOWS_Q)
def execute_scheduled_task(scheduled_task_id: str, tenant_id: str):
    """
    Called by Celery Beat to execute a scheduled task.
    Dispatches the target task asynchronously and tracks execution.
    
    Args:
        scheduled_task_id: UUID of the ScheduledTask
        tenant_id: UUID of the Tenant
    
    Returns:
        dict: Execution dispatch result with execution_id and celery_task_id
    """
    from celery import current_app
    from .models import ScheduledTask, TaskExecution
    
    logger.info(f"Dispatching scheduled task: {scheduled_task_id} for tenant: {tenant_id}")
    
    try:
        scheduled_task = ScheduledTask.objects.get(id=scheduled_task_id, tenant_id=tenant_id)
    except ScheduledTask.DoesNotExist:
        logger.error(f"ScheduledTask not found: {scheduled_task_id}")
        return {"error": f"ScheduledTask not found: {scheduled_task_id}"}
    
    execution = TaskExecution.objects.create(
        scheduled_task=scheduled_task,
        tenant=scheduled_task.tenant,
        status=TaskExecution.STATUS_PENDING,
        trigger_type='scheduled',
        input_data={'args': scheduled_task.task_args, 'kwargs': scheduled_task.task_kwargs},
    )
    
    try:
        task = current_app.tasks.get(scheduled_task.task_name)
        if not task:
            raise ValueError(f"Task '{scheduled_task.task_name}' not found in Celery registry")
        
        result = task.apply_async(
            args=scheduled_task.task_args or [],
            kwargs=scheduled_task.task_kwargs or {},
            link=run_scheduled_task_callback.s(str(execution.id)),
            link_error=run_scheduled_task_error_callback.s(str(execution.id)),
        )
        
        execution.celery_task_id = result.id
        execution.save(update_fields=['celery_task_id'])
        execution.mark_running()
        
        logger.info(f"Scheduled task {scheduled_task.name} dispatched: celery_task_id={result.id}")
        return {
            "status": "dispatched",
            "execution_id": str(execution.id),
            "celery_task_id": result.id,
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        tb = traceback.format_exc()
        execution.mark_failed(error_msg, tb)
        
        logger.error(f"Scheduled task {scheduled_task.name} dispatch failed: {error_msg}")
        return {"status": "failed", "error": error_msg}


@shared_task(name="flows.tasks.run_scheduled_task_callback", queue=FLOWS_Q)
def run_scheduled_task_callback(task_result, execution_id: str):
    """Callback when a scheduled task completes successfully."""
    from .models import TaskExecution
    
    try:
        execution = TaskExecution.objects.get(id=execution_id)
        execution.mark_success(task_result)
        logger.info(f"Scheduled task execution {execution_id} completed successfully")
    except TaskExecution.DoesNotExist:
        logger.error(f"TaskExecution not found for callback: {execution_id}")


@shared_task(name="flows.tasks.run_scheduled_task_error_callback", queue=FLOWS_Q)
def run_scheduled_task_error_callback(request, exc, traceback_str, execution_id: str):
    """Callback when a scheduled task fails."""
    from .models import TaskExecution
    
    try:
        execution = TaskExecution.objects.get(id=execution_id)
        execution.mark_failed(str(exc), traceback_str or '')
        logger.error(f"Scheduled task execution {execution_id} failed: {exc}")
    except TaskExecution.DoesNotExist:
        logger.error(f"TaskExecution not found for error callback: {execution_id}")


@shared_task(name="flows.tasks.execute_scheduled_task_immediate", queue=FLOWS_Q)
def execute_scheduled_task_immediate(
    execution_id: str,
    task_name: str,
    task_args: list = None,
    task_kwargs: dict = None,
):
    """
    Execute a task immediately (manual trigger).
    Used for run-now functionality from the API.
    Dispatches the task asynchronously with callbacks.
    
    Args:
        execution_id: UUID of the TaskExecution record
        task_name: Full Celery task name to execute
        task_args: Positional arguments for the task
        task_kwargs: Keyword arguments for the task
    
    Returns:
        dict: Execution dispatch result with celery_task_id
    """
    from celery import current_app
    from .models import TaskExecution
    
    logger.info(f"Dispatching immediate task: {task_name} (execution: {execution_id})")
    
    try:
        execution = TaskExecution.objects.get(id=execution_id)
    except TaskExecution.DoesNotExist:
        logger.error(f"TaskExecution not found: {execution_id}")
        return {"error": f"TaskExecution not found: {execution_id}"}
    
    try:
        task = current_app.tasks.get(task_name)
        if not task:
            raise ValueError(f"Task '{task_name}' not found in Celery registry")
        
        result = task.apply_async(
            args=task_args or [],
            kwargs=task_kwargs or {},
            link=run_scheduled_task_callback.s(execution_id),
            link_error=run_scheduled_task_error_callback.s(execution_id),
        )
        
        execution.celery_task_id = result.id
        execution.save(update_fields=['celery_task_id'])
        execution.mark_running()
        
        logger.info(f"Immediate task dispatched: execution={execution_id}, celery_task_id={result.id}")
        return {
            "status": "dispatched",
            "execution_id": execution_id,
            "celery_task_id": result.id,
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        tb = traceback.format_exc()
        execution.mark_failed(error_msg, tb)
        
        logger.error(f"Immediate task dispatch failed: {execution_id}: {error_msg}")
        return {"status": "failed", "error": error_msg}
