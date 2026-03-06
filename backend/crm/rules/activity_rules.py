"""
Activity rules: helpers to create ActivitySuggestions from CRM events.

Use from signal handlers, scheduled tasks, or flows. For flow-based automation,
use the CRM CRUD node (resource_slug=activity_suggestion, operation=create)
instead of calling this directly.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def create_activity_suggestion_from_rule(
    tenant,
    type_key: str,
    reason: str,
    *,
    target_contact_id: Optional[str] = None,
    target_customer_id: Optional[str] = None,
    target_deal_id: Optional[str] = None,
    proposed_fields: Optional[Dict[str, Any]] = None,
    expires_at=None,
    confidence: Optional[float] = None,
    created_by_source: str = "rule",
) -> "ActivitySuggestion":
    """
    Create an activity suggestion (e.g. from a signal or cron rule).

    Call this from CRM signal handlers or scheduled jobs when you want to
    suggest an activity (e.g. "no activity for 7 days" -> suggest a follow-up call).
    """
    from crm.models import ActivitySuggestion, ActivitySuggestionStatus

    return ActivitySuggestion.objects.create(
        tenant=tenant,
        type_key=type_key[:60],
        reason=reason[:200],
        confidence=confidence,
        expires_at=expires_at,
        proposed_fields=proposed_fields or {},
        target_contact_id=target_contact_id,
        target_customer_id=target_customer_id,
        target_deal_id=target_deal_id,
        status=ActivitySuggestionStatus.PENDING,
        created_by_source=created_by_source[:60],
    )
