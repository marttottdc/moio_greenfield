"""Webhook and FlowConnector handlers for executing flows."""
import logging
import uuid
from typing import Dict, Any
from django.db.models import Q
from django.utils.timezone import now
from moio_platform.settings import FLOWS_Q
from central_hub.webhooks.registry import webhook_handler

logger = logging.getLogger(__name__)


def _log_flow_event(trace_id: str, event: str, **kwargs):
    """Log a structured flow event for traceability."""
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None)
    logger.info(f"[FLOW_TRACE:{trace_id}] {event} {extra}")


@webhook_handler()
def execute_flow_webhook(payload: Dict[str, Any], headers: dict, content_type: str, webhook_config):
    """
    Webhook handler that executes all flows linked to this webhook.
    
    Dispatches both published and testing versions ASYNCHRONOUSLY via Celery:
    1. Published version: production mode (sandbox=False)
    2. Testing version: sandbox mode (sandbox=True)
    
    Both versions run in parallel in background workers, so the webhook
    returns immediately without blocking.
    
    Draft versions are never executed.
    
    Args:
        payload: Webhook payload data
        headers: Request headers
        content_type: Content-Type header value
        webhook_config: WebhookConfig instance
    
    Returns:
        dict: Dispatch confirmation (not execution results, since async)
    """
    from .models import Flow, FlowVersionStatus
    from .tasks import execute_flow

    # Generate trace ID for this webhook invocation
    trace_id = str(uuid.uuid4())[:8]
    webhook_id = str(getattr(webhook_config, "id", ""))
    webhook_name = getattr(webhook_config, "name", "")
    
    _log_flow_event(trace_id, "WEBHOOK_RECEIVED", 
                    webhook_id=webhook_id, 
                    webhook_name=webhook_name,
                    content_type=content_type,
                    payload_keys=list(payload.keys()) if isinstance(payload, dict) else None)

    metadata = {
        "headers": dict(headers or {}),
        "content_type": content_type,
        "webhook": {
            "id": webhook_id,
            "name": webhook_name,
        },
        "trace_id": trace_id,
    }
    
    try:
        from crm.models import WebhookPayload
        WebhookPayload.objects.create(
            config=webhook_config,
            tenant=webhook_config.tenant,
            payload=payload,
            status='received'
        )
    except Exception as e:
        logger.warning(f"Failed to store webhook payload: {e}")
    
    flow_ids = []
    
    if hasattr(webhook_config, 'linked_flows'):
        # Get flows that have either published or testing versions
        linked = webhook_config.linked_flows.filter(
            Q(published_version__isnull=False) |
            Q(versions__status=FlowVersionStatus.TESTING)
        ).distinct().values_list('id', flat=True)
        flow_ids.extend([str(fid) for fid in linked])
    
    if not flow_ids:
        description = webhook_config.description or ""
        if description.startswith("flow:"):
            legacy_flow_id = description.replace("flow:", "").strip()
            if legacy_flow_id:
                flow_ids.append(legacy_flow_id)
    
    if not flow_ids:
        _log_flow_event(trace_id, "WEBHOOK_NO_FLOWS", webhook_id=webhook_id)
        logger.warning(f"Webhook {webhook_config.id} has no linked flows")
        return {"error": "No flows linked to this webhook", "flows_triggered": 0, "trace_id": trace_id}
    
    _log_flow_event(trace_id, "WEBHOOK_DISPATCHING", flow_count=len(flow_ids), flow_ids=",".join(flow_ids))
    
    dispatched = []
    errors = []
    
    for flow_id in flow_ids:
        try:
            flow = Flow.objects.prefetch_related('versions').get(id=flow_id)
        except Flow.DoesNotExist:
            errors.append({"flow_id": flow_id, "status": "error", "error": f"Flow not found: {flow_id}"})
            continue
        
        # Get published version
        published_version = flow.published_version
        if not published_version:
            published_version = flow.versions.filter(status=FlowVersionStatus.PUBLISHED).first()
        
        # Get testing version
        testing_version = flow.versions.filter(status=FlowVersionStatus.TESTING).first()
        
        # Dispatch published version asynchronously (production mode)
        if published_version:
            try:
                _log_flow_event(trace_id, "DISPATCH_PUBLISHED", 
                               flow_id=flow_id, 
                               flow_name=flow.name,
                               version_id=str(published_version.id),
                               version_label=published_version.label)
                execute_flow.apply_async(
                    kwargs={
                        "flow_id": flow_id,
                        "payload": payload,
                        "trigger_source": "webhook",
                        "trigger_metadata": metadata,
                        "version_id": str(published_version.id),
                        "sandbox": False,
                    },
                    queue=FLOWS_Q,
                )
                dispatched.append({
                    "flow_id": flow_id,
                    "flow_name": flow.name,
                    "version_id": str(published_version.id),
                    "version_label": published_version.label,
                    "version_status": "published",
                    "status": "dispatched",
                    "trace_id": trace_id,
                })
            except Exception as e:
                _log_flow_event(trace_id, "DISPATCH_ERROR", flow_id=flow_id, version_status="published", error=str(e))
                logger.error(f"Error dispatching published version for flow {flow_id}: {e}")
                errors.append({
                    "flow_id": flow_id,
                    "version_id": str(published_version.id),
                    "version_status": "published",
                    "status": "error",
                    "error": str(e),
                })
        
        # Handle testing version - execute in sandbox mode
        if testing_version:
            try:
                _log_flow_event(trace_id, "DISPATCH_TESTING", 
                               flow_id=flow_id,
                               flow_name=flow.name,
                               version_id=str(testing_version.id),
                               version_label=testing_version.label,
                               sandbox=True)
                execute_flow.apply_async(
                    kwargs={
                        "flow_id": flow_id,
                        "payload": payload,
                        "trigger_source": "webhook",
                        "trigger_metadata": metadata,
                        "version_id": str(testing_version.id),
                        "sandbox": True,
                    },
                    queue=FLOWS_Q,
                )
                dispatched.append({
                    "flow_id": flow_id,
                    "flow_name": flow.name,
                    "version_id": str(testing_version.id),
                    "version_label": testing_version.label,
                    "version_status": "testing",
                    "status": "dispatched",
                    "trace_id": trace_id,
                })
            except Exception as e:
                _log_flow_event(trace_id, "DISPATCH_ERROR", flow_id=flow_id, version_status="testing", error=str(e))
                logger.error(f"Error dispatching testing version for flow {flow_id}: {e}")
                errors.append({
                    "flow_id": flow_id,
                    "version_id": str(testing_version.id),
                    "version_status": "testing",
                    "status": "error",
                    "error": str(e),
                })
    
    _log_flow_event(trace_id, "WEBHOOK_COMPLETE", 
                    flows_triggered=len(flow_ids),
                    versions_dispatched=len(dispatched),
                    errors=len(errors))
    
    return {
        "trace_id": trace_id,
        "flows_triggered": len(flow_ids),
        "versions_dispatched": len(dispatched),
        "dispatch_errors": len(errors),
        "dispatched": dispatched,
        "errors": errors,
        "async": True,
    }


def flow_connector_handler(
    *args,
    flow_id: str,
    trigger_type: str = "manual",
    payload: Dict[str, Any] | None = None,
    webhook_payload: Dict[str, Any] | None = None,
    **kwargs,
):
    """
    Handler for FlowConnector nodes that trigger other flows.
    
    This is the glue between FlowConnector nodes (inside flow graphs) and the 
    flow execution engine. When a FlowConnector node executes during a flow run,
    this function is called to trigger the target flow.
    
    The function normalizes various input formats into a standard format for
    execute_flow_sync, which handles the actual execution.
    
    Args:
        *args: Positional args (ignored, for compatibility)
        flow_id: UUID of the target flow to execute
        trigger_type: Source identifier (e.g., "manual", "connector", "api")
        payload: Direct payload data
        webhook_payload: Webhook-style payload (alternative to payload)
        **kwargs: Additional context data
    
    Returns:
        dict: Execution result from execute_flow_sync
    """
    from .tasks import execute_flow_sync

    def _first_mapping(*candidates: Any) -> Dict[str, Any]:
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate:
                return candidate
        return {}

    data = _first_mapping(payload, webhook_payload, kwargs.get("payload"), kwargs.get("data"))
    if not data and kwargs:
        contextual = {
            key: value
            for key, value in kwargs.items()
            if key not in {"flow_id", "trigger_type"}
        }
        if contextual:
            data = {key: str(value) for key, value in contextual.items()}

    source = trigger_type or "manual"
    metadata = {}
    if payload is not None:
        metadata["payload_source"] = "payload"
    elif webhook_payload is not None:
        metadata["payload_source"] = "webhook_payload"

    extra = {
        key: value
        for key, value in kwargs.items()
        if key not in {"flow_id", "trigger_type", "payload", "webhook_payload"}
    }
    if extra:
        metadata["extra"] = {key: str(value) for key, value in extra.items()}

    return execute_flow_sync(
        flow_id,
        data or {},
        trigger_source=source,
        trigger_metadata=metadata,
    )


# Backward compatibility alias
execute_published_flow = flow_connector_handler
