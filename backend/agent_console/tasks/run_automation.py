"""
Run an Agent Console automation (invoke runtime with the automation's message).

Designed to be called by:
- Celery Beat (recurring): schedule this task with (tenant_schema, automation_id)
- Event handlers: when an event matches, call this task with the automation_id
- Webhook views: when webhook is hit, resolve automation and call this task
- Flows: flow step or handler can call this task to run the agent
"""
from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import async_to_sync
from celery import shared_task
from tenancy.tenant_support import public_schema_name, schema_context

logger = logging.getLogger(__name__)


@shared_task(name="agent_console.tasks.run_agent_console_automation", bind=True)
def run_agent_console_automation(
    self,
    tenant_schema: str,
    automation_id: int,
    *,
    initiator_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Load the automation, get a runtime backend for the tenant, and run the agent once.

    Args:
        tenant_schema: Tenant schema name (for loading automation and backend).
        automation_id: PK of AgentConsoleAutomation in that tenant's schema.
        initiator_override: Optional initiator dict for the run (default: first tenant user).

    Returns:
        Result dict from runtime run_once (runId, sessionKey, agentRuntime, etc.)
        or error dict with "error" key.
    """
    from tenancy.tenant_support import tenant_schema_context
    from agent_console.models import AgentConsoleAutomation
    from agent_console.services.runtime_service import (
        get_runtime_backend_for_user,
        runtime_initiator_from_user,
    )

    with schema_context(public_schema_name()):
        from django.db.models import Q
        from tenancy.models import Tenant
        from django.contrib.auth import get_user_model
        User = get_user_model()
        tenant = Tenant.objects.filter(
            Q(schema_name=tenant_schema) | Q(subdomain=tenant_schema)
        ).first()
        if not tenant:
            logger.warning("run_agent_console_automation: tenant not found schema=%s", tenant_schema)
            return {"error": "tenant not found", "tenant_schema": tenant_schema}
        user = User.objects.filter(tenant=tenant).select_related("tenant").first()
        if not user:
            logger.warning("run_agent_console_automation: no user for tenant schema=%s", tenant_schema)
            return {"error": "no user for tenant", "tenant_schema": tenant_schema}

    with tenant_schema_context(tenant_schema):
        try:
            automation = AgentConsoleAutomation.objects.get(pk=automation_id)
        except AgentConsoleAutomation.DoesNotExist:
            logger.warning("run_agent_console_automation: automation not found id=%s", automation_id)
            return {"error": "automation not found", "automation_id": automation_id}
        if not automation.active:
            logger.info("run_agent_console_automation: automation inactive id=%s", automation_id)
            return {"error": "automation inactive", "automation_id": automation_id}

    try:
        backend = get_runtime_backend_for_user(user, workspace_slug=automation.workspace_slug)
    except Exception as e:
        logger.exception("run_agent_console_automation: failed to get backend for user")
        return {"error": str(e), "automation_id": automation_id}

    initiator = initiator_override if isinstance(initiator_override, dict) else runtime_initiator_from_user(user)
    session_key = (automation.session_key or "automation").strip() or "automation"
    message = (automation.message or "").strip() or "Run automation."

    try:
        result = async_to_sync(backend.run_once)(
            session_key=session_key,
            message=message,
            initiator=initiator,
            selected_profile=None,
        )
        return result
    except Exception as e:
        logger.exception("run_agent_console_automation: run_once failed automation_id=%s", automation_id)
        return {"error": str(e), "automation_id": automation_id}
