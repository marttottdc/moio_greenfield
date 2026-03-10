"""
Base utilities for flow executors.

Provides:
- ExecutorResult: Structured output for all executors
- Expression resolution: Handles {{field}}, payload.field, context.field
- Tenant configuration lookup
- Logging helpers with timestamps
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional, Mapping, Union

from ..lib import DotAccessDict

logger = logging.getLogger(__name__)

ISO_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

_SAFE_BUILTINS: Mapping[str, Any] = {
    "len": len,
    "min": min,
    "max": max,
    "sum": sum,
    "any": any,
    "all": all,
    "sorted": sorted,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "enumerate": enumerate,
    "range": range,
    "list": list,
    "dict": dict,
    "set": set,
}


def _now_iso() -> str:
    return datetime.now(UTC).strftime(ISO_TIMESTAMP_FORMAT)


@dataclass
class ExecutorLog:
    """Single log entry from executor execution."""
    timestamp: str
    level: str
    message: str
    data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "timestamp": self.timestamp,
            "level": self.level,
            "message": self.message,
        }
        if self.data:
            result["data"] = self.data
        return result


@dataclass
class ExecutorResult:
    """
    Structured result from any executor.
    
    Provides consistent output format for:
    - Flow node chaining (data passed to downstream nodes)
    - Logging and debugging (logs with timestamps)
    - Error handling (success flag + error message)
    - Execution metadata (timing, task IDs)
    """
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    logs: List[ExecutorLog] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "logs": [log.to_dict() for log in self.logs],
            "error": self.error,
            "metadata": self.metadata,
        }
    
    def add_log(self, level: str, message: str, data: Optional[Dict[str, Any]] = None):
        self.logs.append(ExecutorLog(
            timestamp=_now_iso(),
            level=level,
            message=message,
            data=data,
        ))
    
    def info(self, message: str, data: Optional[Dict[str, Any]] = None):
        self.add_log("INFO", message, data)
        logger.info(message)
    
    def warning(self, message: str, data: Optional[Dict[str, Any]] = None):
        self.add_log("WARNING", message, data)
        logger.warning(message)
    
    def error_log(self, message: str, data: Optional[Dict[str, Any]] = None):
        self.add_log("ERROR", message, data)
        logger.error(message)
    
    def debug(self, message: str, data: Optional[Dict[str, Any]] = None):
        self.add_log("DEBUG", message, data)
        logger.debug(message)


class ExecutorContext:
    """
    Context manager for executor execution.
    Tracks timing and provides logging utilities.
    
    Sandbox Mode:
    When sandbox=True, executors should skip external actions (API calls, 
    message sending, etc.) and return simulated success responses. This is
    used for preview executions of armed draft flows.
    """
    def __init__(
        self, 
        executor_name: str, 
        task_id: Optional[str] = None,
        *,
        sandbox: bool = False,
        preview_run_id: Optional[str] = None,
        preview_flow_id: Optional[str] = None,
    ):
        self.executor_name = executor_name
        self.task_id = task_id
        self.sandbox = sandbox
        self.preview_run_id = preview_run_id
        self.preview_flow_id = preview_flow_id
        self.start_time: float = 0
        self.result = ExecutorResult(success=True)
        self.result.metadata["executor"] = executor_name
        self.result.metadata["sandbox"] = sandbox
        if task_id:
            self.result.metadata["task_id"] = task_id
        if preview_run_id:
            self.result.metadata["preview_run_id"] = preview_run_id
    
    def __enter__(self) -> "ExecutorContext":
        self.start_time = time.time()
        self.result.metadata["started_at"] = _now_iso()
        mode_label = "[SANDBOX] " if self.sandbox else ""
        self.result.info(f"{mode_label}Starting executor: {self.executor_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self.start_time) * 1000)
        self.result.metadata["finished_at"] = _now_iso()
        self.result.metadata["duration_ms"] = duration_ms
        
        if exc_val:
            self.result.success = False
            self.result.error = str(exc_val)
            self.result.error_log(f"Executor failed: {exc_val}")
        else:
            mode_label = "[SANDBOX] " if self.sandbox else ""
            self.result.info(f"{mode_label}Executor completed in {duration_ms}ms")
        
        return False
    
    def sandbox_skip(self, action_description: str, simulated_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Skip an external action in sandbox mode and return simulated result.
        
        Use this in executors to skip real API calls when in sandbox mode:
        
            if ctx.sandbox:
                return ctx.sandbox_skip(
                    "Send WhatsApp message to +1234567890",
                    {"message_id": "sandbox-123", "status": "simulated"}
                )
        """
        self.result.info(f"[SANDBOX SKIP] {action_description}")
        self.result.success = True
        self.result.data = {
            **simulated_data,
            "sandbox": True,
            "sandbox_action": action_description,
        }
        return self.result.to_dict()


def log_entry(level: str, message: str, data: Optional[Dict[str, Any]] = None) -> ExecutorLog:
    """Create a standalone log entry."""
    return ExecutorLog(
        timestamp=_now_iso(),
        level=level,
        message=message,
        data=data,
    )


def create_result(
    success: bool = True,
    data: Optional[Dict[str, Any]] = None,
    logs: Optional[List[ExecutorLog]] = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a standardized executor result dict."""
    result = ExecutorResult(
        success=success,
        data=data or {},
        logs=logs or [],
        error=error,
        metadata=metadata or {},
    )
    return result.to_dict()


def create_error_result(
    error: str,
    logs: Optional[List[ExecutorLog]] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create an error result with the given message."""
    result = ExecutorResult(
        success=False,
        data=data or {},
        logs=logs or [],
        error=error,
    )
    result.error_log(error)
    return result.to_dict()


def resolve_expression(expr: Any, payload: Any, ctx: Dict[str, Any]) -> Any:
    """
    Resolve a template expression from payload/context.
    
    Supports:
    - {{field}} - direct field access
    - {{payload.field}} - explicit payload access
    - {{context.field}} - context access
    - {{$input.field}} - initial input access
    - {{$trigger.data.field}} - trigger data access
    - {{node_id.field}} - previous node output access
    """
    if not isinstance(expr, str):
        return expr
    
    stripped = expr.strip()
    if not (stripped.startswith("{{") and stripped.endswith("}}")):
        return expr
    
    inner = stripped[2:-2].strip()

    input_value = ctx.get("$input")
    scope: Dict[str, Any] = {
        "payload": payload,
        "ctx": ctx,
        "context": ctx,
        "input": DotAccessDict(input_value) if isinstance(input_value, dict) else input_value,
        "trigger": ctx.get("$trigger"),
    }
    
    if isinstance(payload, dict):
        scope.update(payload)
    
    trigger_data = ctx.get("$trigger", {})
    if isinstance(trigger_data, dict):
        scope.update(trigger_data.get("data", {}))
    
    for node_id, node_output in ctx.items():
        if not node_id.startswith("$") and isinstance(node_output, dict):
            scope[node_id] = node_output
    
    try:
        return eval(inner, {"__builtins__": _SAFE_BUILTINS}, scope)
    except Exception as e:
        if isinstance(inner, str) and "input." in inner and "input.body." not in inner:
            logger.warning(
                "Expression resolution failed for '%s': %s. "
                "Hint: runtime `input` is now a container; use `input.body.<field>` instead of `input.<field>`.",
                expr,
                e,
            )
        else:
            logger.warning(f"Expression resolution failed for '{expr}': {e}")
        return _lookup_path(payload, ctx, inner)


def _lookup_path(payload: Any, ctx: Dict[str, Any], path: str) -> Any:
    """
    Lookup a dotted path in payload or context.
    
    Supports:
    - payload.field.subfield
    - context.field
    - $input.field
    - $trigger.data.field
    - node_id.output.field
    """
    if not path:
        return None
    
    parts = path.split(".")
    source: Any = None
    key_parts: List[str] = []
    
    first = parts[0].lower()
    
    if first in ("payload", "$payload"):
        source = payload
        key_parts = parts[1:]
    elif first in ("context", "$context", "ctx"):
        source = ctx
        key_parts = parts[1:]
    elif first == "$input":
        source = ctx.get("$input", {})
        key_parts = parts[1:]
    elif first == "$trigger":
        source = ctx.get("$trigger", {})
        key_parts = parts[1:]
    elif first in ctx:
        source = ctx.get(first, {})
        key_parts = parts[1:]
    else:
        source = payload if isinstance(payload, dict) else {}
        key_parts = parts
    
    result = source
    for part in key_parts:
        if isinstance(result, dict):
            result = result.get(part)
        elif hasattr(result, part):
            result = getattr(result, part)
        else:
            return None
        if result is None:
            return None
    
    return result


def resolve_mapping(
    mapping: Dict[str, Any],
    payload: Any,
    ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Resolve all expressions in a mapping dict.
    
    Args:
        mapping: Dict with values that may contain {{expressions}}
        payload: Current payload from previous node
        ctx: Execution context
    
    Returns:
        Dict with all expressions resolved to actual values
    """
    resolved = {}
    for key, value in mapping.items():
        if isinstance(value, str):
            resolved[key] = resolve_expression(value, payload, ctx)
        elif isinstance(value, dict):
            resolved[key] = resolve_mapping(value, payload, ctx)
        elif isinstance(value, list):
            resolved[key] = [
                resolve_expression(item, payload, ctx) if isinstance(item, str)
                else resolve_mapping(item, payload, ctx) if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            resolved[key] = value
    return resolved


def get_tenant_config(tenant_id: Optional[str]):
    """
    Get tenant and configuration from tenant_id.
    
    Returns:
        Tuple of (tenant, config) or (None, None) if not found
    """
    if not tenant_id:
        return None, None
    
    try:
        from central_hub.models import Tenant, TenantConfiguration
        tenant = Tenant.objects.get(id=tenant_id)
        config = TenantConfiguration.objects.filter(tenant=tenant).first()
        return tenant, config
    except Exception as e:
        logger.error(f"Failed to get tenant config for {tenant_id}: {e}")
        return None, None


def get_tenant_by_id(tenant_id: Optional[str]):
    """Get just the tenant object."""
    if not tenant_id:
        return None
    try:
        from central_hub.models import Tenant
        return Tenant.objects.get(id=tenant_id)
    except Exception as e:
        logger.error(f"Failed to get tenant {tenant_id}: {e}")
        return None
