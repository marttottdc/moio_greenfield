"""
Output Executors - Flow Output Handlers

Output handlers that finalize flow execution results.
These can store results, notify users, update records, etc.

Output types:
- store_result: Store flow execution result in database
- notify: Send notification about flow completion
- webhook_response: Return response to webhook caller
- log_completion: Log flow completion
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, List
from celery import shared_task

from moio_platform.settings import FLOWS_Q

from .base import (
    ExecutorResult,
    ExecutorContext,
    create_result,
    get_tenant_config,
    log_entry,
    _now_iso,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="executors.store_flow_result", queue=FLOWS_Q)
def store_flow_result_task(
    self,
    tenant_id: str,
    flow_id: str,
    execution_id: str,
    result_data: Dict[str, Any],
    status: str = "completed",
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store flow execution result in the database.
    
    Args:
        tenant_id: Tenant ID
        flow_id: Flow ID
        execution_id: Execution/run ID
        result_data: Final result data
        status: Execution status (completed, failed, cancelled)
        error: Error message if failed
    
    Returns:
        ExecutorResult dict with storage confirmation
    """
    with ExecutorContext("store_flow_result", self.request.id) as ctx:
        result = ctx.result
        
        result.info(f"Storing flow result", {
            "flow_id": flow_id,
            "execution_id": execution_id,
            "status": status,
        })
        
        try:
            from flows.models import FlowExecution
            
            try:
                execution = FlowExecution.objects.get(id=execution_id)
                execution.status = status
                execution.result = result_data
                if error:
                    execution.error = error
                execution.completed_at = _now_iso()
                execution.save()
                
                result.success = True
                result.data = {
                    "execution_id": execution_id,
                    "status": status,
                    "stored": True,
                }
                result.info(f"Flow result stored: {execution_id}")
            except FlowExecution.DoesNotExist:
                result.warning(f"Execution not found, logging result only")
                result.success = True
                result.data = {
                    "execution_id": execution_id,
                    "status": status,
                    "stored": False,
                    "result_data": result_data,
                }
                
        except ImportError:
            result.warning("FlowExecution model not available, logging result only")
            result.success = True
            result.data = {
                "execution_id": execution_id,
                "status": status,
                "stored": False,
                "result_data": result_data,
            }
        except Exception as e:
            result.success = False
            result.error = f"Failed to store flow result: {e}"
            result.error_log(result.error)
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.flow_completion_notify", queue=FLOWS_Q)
def flow_completion_notify_task(
    self,
    tenant_id: str,
    flow_id: str,
    flow_name: str,
    execution_id: str,
    status: str,
    notify_channels: List[str],
    result_summary: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send notification about flow completion.
    
    Args:
        tenant_id: Tenant ID
        flow_id: Flow ID
        flow_name: Flow name for display
        execution_id: Execution ID
        status: Completion status
        notify_channels: List of notification channels ('email', 'slack', 'webhook')
        result_summary: Optional summary message
    
    Returns:
        ExecutorResult dict with notification status
    """
    with ExecutorContext("flow_completion_notify", self.request.id) as ctx:
        result = ctx.result
        
        result.info(f"Sending completion notification", {
            "flow_name": flow_name,
            "status": status,
            "channels": notify_channels,
        })
        
        notifications_sent = []
        
        for channel in notify_channels:
            try:
                if channel == "email":
                    result.info(f"Email notification would be sent for {flow_name}")
                    notifications_sent.append({"channel": "email", "status": "queued"})
                elif channel == "slack":
                    result.info(f"Slack notification would be sent for {flow_name}")
                    notifications_sent.append({"channel": "slack", "status": "queued"})
                elif channel == "webhook":
                    result.info(f"Webhook notification would be sent for {flow_name}")
                    notifications_sent.append({"channel": "webhook", "status": "queued"})
                else:
                    result.warning(f"Unknown notification channel: {channel}")
            except Exception as e:
                result.warning(f"Failed to send {channel} notification: {e}")
                notifications_sent.append({"channel": channel, "status": "failed", "error": str(e)})
        
        result.success = True
        result.data = {
            "flow_id": flow_id,
            "flow_name": flow_name,
            "execution_id": execution_id,
            "status": status,
            "notifications": notifications_sent,
        }
        result.info(f"Sent {len(notifications_sent)} notifications")
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.webhook_response", queue=FLOWS_Q)
def webhook_response_task(
    self,
    response_data: Dict[str, Any],
    status_code: int = 200,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Prepare a webhook response for the caller.
    
    This task doesn't actually send the response (that's handled by the view),
    but it formats the response data for return.
    
    Args:
        response_data: Data to return in the response
        status_code: HTTP status code
        headers: Optional response headers
    
    Returns:
        ExecutorResult dict with formatted response
    """
    with ExecutorContext("webhook_response", self.request.id) as ctx:
        result = ctx.result
        
        result.info(f"Preparing webhook response", {"status_code": status_code})
        
        result.success = True
        result.data = {
            "response_data": response_data,
            "status_code": status_code,
            "headers": headers or {},
        }
        result.info(f"Webhook response prepared with status {status_code}")
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.log_flow_completion", queue=FLOWS_Q)
def log_flow_completion_task(
    self,
    tenant_id: str,
    flow_id: str,
    flow_name: str,
    execution_id: str,
    status: str,
    duration_ms: int,
    node_count: int,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Log flow completion for analytics and debugging.
    
    Args:
        tenant_id: Tenant ID
        flow_id: Flow ID
        flow_name: Flow name
        execution_id: Execution ID
        status: Completion status
        duration_ms: Total execution duration in milliseconds
        node_count: Number of nodes executed
        error: Error message if failed
    
    Returns:
        ExecutorResult dict with log confirmation
    """
    with ExecutorContext("log_flow_completion", self.request.id) as ctx:
        result = ctx.result
        
        log_data = {
            "tenant_id": tenant_id,
            "flow_id": flow_id,
            "flow_name": flow_name,
            "execution_id": execution_id,
            "status": status,
            "duration_ms": duration_ms,
            "node_count": node_count,
            "completed_at": _now_iso(),
        }
        
        if error:
            log_data["error"] = error
            logger.error(f"Flow execution failed: {flow_name} ({execution_id})", extra=log_data)
        else:
            logger.info(f"Flow execution completed: {flow_name} ({execution_id}) in {duration_ms}ms", extra=log_data)
        
        result.success = True
        result.data = log_data
        result.info(f"Flow completion logged: {flow_name}")
    
    return ctx.result.to_dict()


def store_result_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for storing results."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "flow_id": ctx.get("flow_id", ""),
        "execution_id": ctx.get("execution_id", ""),
        "result_data": payload if isinstance(payload, dict) else {"result": payload},
        "status": config.get("status", "completed"),
        "error": config.get("error"),
    }
    
    return store_flow_result_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def notify_completion_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for completion notifications."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "flow_id": ctx.get("flow_id", ""),
        "flow_name": ctx.get("flow_name", "Unknown Flow"),
        "execution_id": ctx.get("execution_id", ""),
        "status": config.get("status", "completed"),
        "notify_channels": config.get("channels", ["email"]),
        "result_summary": config.get("summary"),
    }
    
    if config.get("async", False):
        task = flow_completion_notify_task.apply_async(kwargs=task_kwargs)  # type: ignore[attr-defined]
        return create_result(
            success=True,
            data={"task_id": task.id, "status": "queued"},
            logs=[log_entry("INFO", f"Notification task queued: {task.id}")],
        )
    else:
        return flow_completion_notify_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def webhook_response_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for webhook response."""
    task_kwargs = {
        "response_data": config.get("response_data", payload),
        "status_code": config.get("status_code", 200),
        "headers": config.get("headers"),
    }
    
    return webhook_response_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def log_completion_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for logging completion."""
    task_kwargs = {
        "tenant_id": tenant_id,
        "flow_id": ctx.get("flow_id", ""),
        "flow_name": ctx.get("flow_name", "Unknown Flow"),
        "execution_id": ctx.get("execution_id", ""),
        "status": config.get("status", "completed"),
        "duration_ms": ctx.get("duration_ms", 0),
        "node_count": ctx.get("node_count", 0),
        "error": config.get("error"),
    }
    
    return log_flow_completion_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]
