"""
Debug Executors - Debug Logger Celery Task

Standalone Celery task for debugging flow execution that can be:
1. Called directly from anywhere
2. Registered as flow node executors

Returns structured ExecutorResult for downstream chaining.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from celery import shared_task

from .base import (
    ExecutorResult,
    ExecutorContext,
    create_result,
    log_entry,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="executors.debug_log")
def debug_log_task(
    self,
    message: str,
    payload: Any = None,
    context: Optional[Dict[str, Any]] = None,
    level: str = "DEBUG",
    log_to_console: bool = True,
    log_to_file: bool = False,
    file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Debug logging task for flow execution.
    
    Logs the current payload and context for debugging purposes.
    
    Args:
        message: Debug message to log
        payload: Current payload data to log
        context: Current context data to log
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_to_console: Whether to log to console (default True)
        log_to_file: Whether to write to a file (default False)
        file_path: File path for file logging
    
    Returns:
        ExecutorResult dict with:
        - success: bool
        - data: {message, payload, context}
        - logs: execution logs
        - metadata: timing info
    """
    with ExecutorContext("debug_log", self.request.id) as ctx:
        result = ctx.result
        
        log_data = {
            "message": message,
            "payload_type": type(payload).__name__,
            "context_keys": list(context.keys()) if context else [],
        }
        
        if log_to_console:
            log_method = getattr(logger, level.lower(), logger.debug)
            log_method(f"[FLOW DEBUG] {message}")
            log_method(f"[FLOW DEBUG] Payload: {json.dumps(payload, default=str) if payload else 'None'}")
            if context:
                log_method(f"[FLOW DEBUG] Context keys: {list(context.keys())}")
        
        if log_to_file and file_path:
            try:
                with open(file_path, "a") as f:
                    f.write(f"\n--- Debug Log ---\n")
                    f.write(f"Message: {message}\n")
                    f.write(f"Payload: {json.dumps(payload, default=str, indent=2) if payload else 'None'}\n")
                    f.write(f"Context: {json.dumps(context, default=str, indent=2) if context else 'None'}\n")
                result.info(f"Logged to file: {file_path}")
            except Exception as e:
                result.warning(f"Failed to write to file {file_path}: {e}")
        
        result.data = {
            "message": message,
            "payload": payload,
            "context_snapshot": {k: type(v).__name__ for k, v in (context or {}).items()},
            "level": level,
        }
        
        result.add_log(level.upper(), message, log_data)
        result.success = True
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.passthrough")
def passthrough_task(
    self,
    payload: Any = None,
    transform: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Passthrough task that returns payload unchanged or with transformations.
    
    Useful for testing flow execution or simple data transformations.
    
    Args:
        payload: Data to pass through
        transform: Optional transformation mapping {output_key: input_path}
    
    Returns:
        ExecutorResult with payload as data
    """
    with ExecutorContext("passthrough", self.request.id) as ctx:
        result = ctx.result
        
        if transform and isinstance(payload, dict):
            output_data = {}
            for output_key, input_path in transform.items():
                parts = input_path.split(".")
                value = payload
                for part in parts:
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        value = None
                        break
                output_data[output_key] = value
            result.data = output_data
            result.info(f"Transformed {len(transform)} fields")
        else:
            result.data = {"payload": payload}
            result.info("Passthrough complete")
        
        result.success = True
    
    return ctx.result.to_dict()


@shared_task(bind=True, name="executors.noop")
def noop_task(self) -> Dict[str, Any]:
    """
    No-operation task that does nothing and returns success.
    
    Useful for testing and as a placeholder.
    
    Returns:
        ExecutorResult with success=True
    """
    with ExecutorContext("noop", self.request.id) as ctx:
        result = ctx.result
        result.data = {"message": "No operation performed"}
        result.info("Noop task executed")
        result.success = True
    
    return ctx.result.to_dict()


def noop_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for noop."""
    return noop_task.apply().result  # type: ignore[attr-defined]


def debug_log_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for debug logging."""
    task_kwargs = {
        "message": config.get("message", "Debug checkpoint"),
        "payload": payload,
        "context": ctx,
        "level": config.get("level", "DEBUG"),
        "log_to_console": config.get("log_to_console", True),
        "log_to_file": config.get("log_to_file", False),
        "file_path": config.get("file_path"),
    }
    
    return debug_log_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]


def passthrough_executor(
    payload: Any,
    config: Dict[str, Any],
    ctx: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """Flow node executor wrapper for passthrough."""
    task_kwargs = {
        "payload": payload,
        "transform": config.get("transform"),
    }
    
    return passthrough_task.apply(kwargs=task_kwargs).result  # type: ignore[attr-defined]
