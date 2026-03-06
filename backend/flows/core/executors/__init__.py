"""
Flow Executors Package

Executor functions that run synchronously within flow execution tasks.
These are called directly from the flow runtime (which is already a Celery task).

All executors return structured ExecutorResult for downstream chaining.
"""

from .base import (
    ExecutorResult,
    ExecutorLog,
    ExecutorContext,
    create_result,
    create_error_result,
    resolve_expression,
    resolve_mapping,
    get_tenant_config,
    get_tenant_by_id,
    log_entry,
)

from .messaging import (
    send_whatsapp_template,
    send_email_template,
)

from .crm import (
    create_contact_task,
    upsert_contact_task,
    create_ticket_task,
    update_candidate_status_task,
    search_contacts_task,
    contact_create_executor,
    contact_upsert_executor,
    ticket_create_executor,
    candidate_status_executor,
    contact_search_executor,
)

from .http import (
    http_request_task,
    http_request_executor,
)

from .triggers import (
    process_webhook_trigger_task,
    process_schedule_trigger_task,
    process_event_trigger_task,
    process_manual_trigger_task,
    webhook_trigger_executor,
    schedule_trigger_executor,
    event_trigger_executor,
    manual_trigger_executor,
)

from .outputs import (
    store_flow_result_task,
    flow_completion_notify_task,
    webhook_response_task,
    log_flow_completion_task,
    store_result_executor,
    notify_completion_executor,
    webhook_response_executor,
    log_completion_executor,
)

from .debug import (
    debug_log_task,
    passthrough_task,
    noop_task,
    debug_log_executor,
    passthrough_executor,
    noop_executor,
)

__all__ = [
    # Base utilities
    "ExecutorResult",
    "ExecutorLog",
    "ExecutorContext",
    "create_result",
    "create_error_result",
    "resolve_expression",
    "resolve_mapping",
    "get_tenant_config",
    "get_tenant_by_id",
    "log_entry",
    # Messaging functions
    "send_whatsapp_template",
    "send_email_template",
    # CRM tasks
    "create_contact_task",
    "upsert_contact_task",
    "create_ticket_task",
    "update_candidate_status_task",
    "search_contacts_task",
    "contact_create_executor",
    "contact_upsert_executor",
    "ticket_create_executor",
    "candidate_status_executor",
    "contact_search_executor",
    # HTTP tasks
    "http_request_task",
    "http_request_executor",
    # Trigger tasks
    "process_webhook_trigger_task",
    "process_schedule_trigger_task",
    "process_event_trigger_task",
    "process_manual_trigger_task",
    "webhook_trigger_executor",
    "schedule_trigger_executor",
    "event_trigger_executor",
    "manual_trigger_executor",
    # Output tasks
    "store_flow_result_task",
    "flow_completion_notify_task",
    "webhook_response_task",
    "log_flow_completion_task",
    "store_result_executor",
    "notify_completion_executor",
    "webhook_response_executor",
    "log_completion_executor",
    # Debug tasks
    "debug_log_task",
    "passthrough_task",
    "noop_task",
    "debug_log_executor",
    "passthrough_executor",
    "noop_executor",
]

EXECUTOR_REGISTRY = {
    # Messaging - now called directly via @register_executor in registry.py
    # CRM
    "create_contact": contact_create_executor,
    "upsert_contact": contact_upsert_executor,
    "create_ticket": ticket_create_executor,
    "update_candidate_status": candidate_status_executor,
    "search_contacts": contact_search_executor,
    # HTTP
    "http_request": http_request_executor,
    # Triggers
    "webhook_trigger": webhook_trigger_executor,
    "schedule_trigger": schedule_trigger_executor,
    "event_trigger": event_trigger_executor,
    "manual_trigger": manual_trigger_executor,
    # Outputs
    "store_result": store_result_executor,
    "notify_completion": notify_completion_executor,
    "webhook_response": webhook_response_executor,
    "log_completion": log_completion_executor,
    # Debug
    "debug_log": debug_log_executor,
    "passthrough": passthrough_executor,
    "noop": noop_executor,
}


def get_executor(executor_type: str):
    """
    Get an executor function by type.
    
    Args:
        executor_type: The type of executor to get
    
    Returns:
        The executor function or None if not found
    """
    return EXECUTOR_REGISTRY.get(executor_type)


def list_executors():
    """List all available executor types."""
    return list(EXECUTOR_REGISTRY.keys())
