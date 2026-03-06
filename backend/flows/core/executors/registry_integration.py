"""
Registry Integration - Bridge between Executors and Flow Registry

This module provides integration functions that wrap executor functions
for use with the existing flow registry pattern.

The registry expects executors with signature: (node, payload, ctx) -> dict
Our executors have signature: (payload, config, ctx, tenant_id) -> ExecutorResult

This module bridges the gap by:
1. Extracting config from node
2. Extracting tenant_id from ctx
3. Calling the appropriate executor
4. Converting ExecutorResult to the expected format

Note: WhatsApp and Email executors are now handled directly in registry.py
via @register_executor decorators, not through this integration layer.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Callable

from .crm import (
    contact_create_executor,
    contact_upsert_executor,
    ticket_create_executor,
    candidate_status_executor,
    contact_search_executor,
)
from .http import http_request_executor
from .debug import debug_log_executor, passthrough_executor, noop_executor
from .triggers import (
    webhook_trigger_executor,
    schedule_trigger_executor,
    event_trigger_executor,
    manual_trigger_executor,
)
from .outputs import (
    store_result_executor,
    notify_completion_executor,
    webhook_response_executor,
    log_completion_executor,
)

logger = logging.getLogger(__name__)


def _wrap_executor(executor_fn: Callable) -> Callable[[dict, Any, dict], dict]:
    """
    Wrap a new-style executor function for use with the registry.
    
    Converts: (payload, config, ctx, tenant_id) -> ExecutorResult
    To: (node, payload, ctx) -> dict
    """
    def wrapped(node: dict, payload: Any, ctx: dict) -> dict:
        config = node.get("config", {})
        tenant_id = ctx.get("tenant_id", "")
        
        try:
            result = executor_fn(payload, config, ctx, tenant_id)
            
            if isinstance(result, dict) and "success" in result:
                return result
            else:
                return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"Executor failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    return wrapped


EXECUTOR_WRAPPERS = {
    # WhatsApp and Email are now handled directly in registry.py via @register_executor
    "tool_create_contact": _wrap_executor(contact_create_executor),
    "tool_upsert_contact": _wrap_executor(contact_upsert_executor),
    "tool_create_ticket": _wrap_executor(ticket_create_executor),
    "tool_update_candidate": _wrap_executor(candidate_status_executor),
    "tool_search_contacts": _wrap_executor(contact_search_executor),
    "tool_http_request": _wrap_executor(http_request_executor),
    "debug_logger": _wrap_executor(debug_log_executor),
    "debug_passthrough": _wrap_executor(passthrough_executor),
    "debug_noop": _wrap_executor(noop_executor),
    "trigger_webhook": _wrap_executor(webhook_trigger_executor),
    "trigger_scheduled": _wrap_executor(schedule_trigger_executor),
    "trigger_event": _wrap_executor(event_trigger_executor),
    "trigger_manual": _wrap_executor(manual_trigger_executor),
    "output_task": _wrap_executor(store_result_executor),
    "output_notify": _wrap_executor(notify_completion_executor),
    "output_webhook_reply": _wrap_executor(webhook_response_executor),
    "output_log": _wrap_executor(log_completion_executor),
}


def register_all_executors(registry):
    """
    Register all executor wrappers with the flow registry.
    
    Call this from flows/apps.py or wherever registry initialization happens.
    
    Usage:
        from flows.core.registry import registry
        from flows.core.executors.registry_integration import register_all_executors
        
        register_all_executors(registry)
    """
    for kind, wrapper in EXECUTOR_WRAPPERS.items():
        try:
            definition = registry.get(kind)
            if definition:
                definition.executor = wrapper
                logger.info(f"Registered executor for '{kind}'")
            else:
                logger.debug(f"No node definition for '{kind}', skipping")
        except Exception as e:
            logger.warning(f"Failed to register executor '{kind}': {e}")


def get_executor_wrapper(kind: str) -> Callable:
    """Get an executor wrapper by kind."""
    return EXECUTOR_WRAPPERS.get(kind)


def list_executor_kinds() -> list:
    """List all available executor kinds."""
    return list(EXECUTOR_WRAPPERS.keys())
