"""
Trigger Executors - Flow Trigger Handlers

Trigger handlers that can be registered as flow entry points.
These are NOT Celery tasks - they're synchronous handlers that
process trigger events and return structured results.

Trigger types:
- webhook: Incoming HTTP webhook
- schedule: Scheduled/cron trigger
- event: Internal event trigger
- manual: Manual trigger from UI
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any, Dict, Optional
from celery import shared_task

from moio_platform.settings import FLOWS_Q

from .base import (
    ExecutorResult,
    ExecutorContext,
    create_result,
    log_entry,
    _now_iso,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="executors.process_webhook_trigger", queue=FLOWS_Q)
def process_webhook_trigger_task(
    self,
    tenant_id: str,
    flow_id: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    method: str = "POST",
    path: str = "",
) -> Dict[str, Any]:
    """
    Process an incoming webhook trigger for a flow.
    
    Args:
        tenant_id: Tenant ID
        flow_id: Flow ID to trigger
        payload: Webhook payload data
        headers: HTTP headers from the request
        method: HTTP method used
        path: Request path
    
    Returns:
        ExecutorResult dict with:
        - success: bool
        - data: {trigger_type, payload, flow_id, ...}
        - logs: execution logs
        - metadata: timing info
    """
    with ExecutorContext("webhook_trigger", self.request.id) as ctx:
        result = ctx.result
        
        result.info(f"Processing webhook trigger", {
            "flow_id": flow_id,
            "method": method,
            "path": path,
        })
        
        trigger_data = {
            "trigger_type": "webhook",
            "flow_id": flow_id,
            "tenant_id": tenant_id,
            "payload": payload,
            "headers": headers or {},
            "method": method,
            "path": path,
            "timestamp": _now_iso(),
        }
        
        result.success = True
        result.data = trigger_data
        result.info("Webhook trigger processed successfully")
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.process_schedule_trigger", queue=FLOWS_Q)
def process_schedule_trigger_task(
    self,
    tenant_id: str,
    flow_id: str,
    schedule_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process a scheduled trigger for a flow.
    
    Args:
        tenant_id: Tenant ID
        flow_id: Flow ID to trigger
        schedule_config: Schedule configuration (cron, interval, etc.)
    
    Returns:
        ExecutorResult dict with trigger data
    """
    with ExecutorContext("schedule_trigger", self.request.id) as ctx:
        result = ctx.result
        
        result.info(f"Processing scheduled trigger", {
            "flow_id": flow_id,
            "schedule": schedule_config,
        })
        
        trigger_data = {
            "trigger_type": "schedule",
            "flow_id": flow_id,
            "tenant_id": tenant_id,
            "payload": {},
            "schedule_config": schedule_config or {},
            "triggered_at": _now_iso(),
        }
        
        result.success = True
        result.data = trigger_data
        result.info("Schedule trigger processed successfully")
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.process_event_trigger", queue=FLOWS_Q)
def process_event_trigger_task(
    self,
    tenant_id: str,
    flow_id: str,
    event_type: str,
    event_data: Dict[str, Any],
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process an internal event trigger for a flow.
    
    Args:
        tenant_id: Tenant ID
        flow_id: Flow ID to trigger
        event_type: Type of event (e.g., 'contact.created', 'ticket.updated')
        event_data: Event payload data
        source: Source of the event
    
    Returns:
        ExecutorResult dict with trigger data
    """
    with ExecutorContext("event_trigger", self.request.id) as ctx:
        result = ctx.result
        
        result.info(f"Processing event trigger", {
            "flow_id": flow_id,
            "event_type": event_type,
            "source": source,
        })
        
        trigger_data = {
            "trigger_type": "event",
            "event_type": event_type,
            "flow_id": flow_id,
            "tenant_id": tenant_id,
            "payload": event_data,
            "source": source,
            "triggered_at": _now_iso(),
        }
        
        result.success = True
        result.data = trigger_data
        result.info(f"Event trigger '{event_type}' processed successfully")
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.process_manual_trigger", queue=FLOWS_Q)
def process_manual_trigger_task(
    self,
    tenant_id: str,
    flow_id: str,
    user_id: Optional[str] = None,
    input_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Process a manual trigger from the UI.
    
    Args:
        tenant_id: Tenant ID
        flow_id: Flow ID to trigger
        user_id: ID of user who triggered the flow
        input_data: Optional input data from UI form
    
    Returns:
        ExecutorResult dict with trigger data
    """
    with ExecutorContext("manual_trigger", self.request.id) as ctx:
        result = ctx.result
        
        result.info(f"Processing manual trigger", {
            "flow_id": flow_id,
            "user_id": user_id,
        })
        
        trigger_data = {
            "trigger_type": "manual",
            "flow_id": flow_id,
            "tenant_id": tenant_id,
            "payload": input_data or {},
            "triggered_by": user_id,
            "triggered_at": _now_iso(),
        }
        
        result.success = True
        result.data = trigger_data
        result.info("Manual trigger processed successfully")
    
    return ctx.result.to_dict()


def webhook_trigger_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for webhook trigger processing."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "flow_id": ctx.get("flow_id", ""),
        "payload": payload if isinstance(payload, dict) else {"raw": payload},
        "headers": config.get("headers"),
        "method": config.get("method", "POST"),
        "path": config.get("path", ""),
    }
    
    return process_webhook_trigger_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def schedule_trigger_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for schedule trigger."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "flow_id": ctx.get("flow_id", ""),
        "schedule_config": config.get("schedule"),
    }
    
    return process_schedule_trigger_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def event_trigger_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for event trigger."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "flow_id": ctx.get("flow_id", ""),
        "event_type": config.get("event_type", ""),
        "event_data": payload if isinstance(payload, dict) else {"raw": payload},
        "source": config.get("source"),
    }
    
    return process_event_trigger_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def manual_trigger_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for manual trigger."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "flow_id": ctx.get("flow_id", ""),
        "user_id": ctx.get("user_id"),
        "input_data": payload if isinstance(payload, dict) else {"raw": payload},
    }
    
    return process_manual_trigger_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]
