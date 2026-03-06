from __future__ import annotations

from typing import Any, Dict


class CrmCrudHandlerError(ValueError):
    pass


def dispatch_crm_operation(*, resource_slug: str, operation: str, data: dict, ctx: dict) -> dict:
    """Dispatch CRM CRUD operation to per-resource handlers.

    Expected output format must match the contract output schema for the given op.
    """
    resource_slug = str(resource_slug or "").strip().lower()
    operation = str(operation or "").strip().lower()

    if resource_slug == "activity":
        from flows.core.executors.crm_handlers_activity import handle_activity_operation
        return handle_activity_operation(operation=operation, data=data, ctx=ctx)
    if resource_slug == "activity_suggestion":
        from flows.core.executors.crm_handlers_activity import handle_activity_suggestion_operation
        return handle_activity_suggestion_operation(operation=operation, data=data, ctx=ctx)
    if resource_slug == "contact":
        from flows.core.executors.crm_handlers_contact import handle_contact_operation
        return handle_contact_operation(operation=operation, data=data, ctx=ctx)
    if resource_slug == "ticket":
        from flows.core.executors.crm_handlers_ticket import handle_ticket_operation
        return handle_ticket_operation(operation=operation, data=data, ctx=ctx)
    if resource_slug == "deal":
        from flows.core.executors.crm_handlers_deal import handle_deal_operation
        return handle_deal_operation(operation=operation, data=data, ctx=ctx)
    if resource_slug == "audience":
        from flows.core.executors.crm_handlers_audience import handle_audience_operation
        return handle_audience_operation(operation=operation, data=data, ctx=ctx)

    raise CrmCrudHandlerError(f"Unknown CRM resource '{resource_slug}'")


__all__ = ["CrmCrudHandlerError", "dispatch_crm_operation"]

