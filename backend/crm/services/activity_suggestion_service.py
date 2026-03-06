"""
ActivitySuggestion accept/dismiss and creation helpers.
"""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from typing import Any, Dict, Optional

from crm.models import (
    ActivityRecord,
    ActivityKind,
    ActivitySuggestion,
    ActivitySuggestionStatus,
    ActivityType,
    ActivityTypeCategory,
    Contact,
    Customer,
    Deal,
)
from crm.services.activity_service import create_activity


def _resolve_suggestion_kind(
    proposed_fields: Dict[str, Any],
    activity_type: Optional[ActivityType],
) -> str:
    """Pick a safe kind for suggestion acceptance."""
    raw_kind = proposed_fields.get("kind")
    if raw_kind is not None:
        if not isinstance(raw_kind, str):
            raise ValueError("kind override must be a string")
        normalized_kind = raw_kind.strip().lower()
        if normalized_kind not in ActivityKind.values:
            raise ValueError(f"Invalid kind override: {raw_kind}")
        return normalized_kind

    if activity_type and activity_type.category == ActivityTypeCategory.TASK:
        return ActivityKind.TASK
    return ActivityKind.OTHER


def accept_suggestion(
    suggestion_id: str,
    user,
    overrides: Optional[Dict[str, Any]] = None,
    tenant=None,
) -> ActivityRecord:
    """
    Accept a suggestion: create an ActivityRecord from it and link the suggestion.

    Args:
        suggestion_id: ActivitySuggestion pk.
        user: User accepting (used as owner/created_by).
        overrides: Optional dict to override proposed_fields (e.g. scheduled_at, title).
        tenant: Optional tenant to scope lookup (recommended for API).

    Returns:
        The created ActivityRecord.
    """
    if overrides is None:
        overrides = {}
    elif not isinstance(overrides, dict):
        raise ValueError("overrides must be an object")
    with transaction.atomic():
        qs = ActivitySuggestion.objects.select_for_update().filter(id=suggestion_id)
        if tenant is not None:
            qs = qs.filter(tenant=tenant)
        suggestion = get_object_or_404(qs)
        if suggestion.status != ActivitySuggestionStatus.PENDING:
            raise ValueError(f"Suggestion is not pending: {suggestion.status}")

        proposed = {**suggestion.proposed_fields, **overrides}

        try:
            activity_type = ActivityType.objects.get(
                tenant=suggestion.tenant,
                key=suggestion.type_key,
            )
        except ActivityType.DoesNotExist:
            activity_type = None

        contact = None
        if suggestion.target_contact_id:
            contact = Contact.objects.filter(
                user_id=suggestion.target_contact_id,
                tenant=suggestion.tenant,
            ).first()
        customer = None
        if suggestion.target_customer_id:
            customer = Customer.objects.filter(
                id=suggestion.target_customer_id,
                tenant=suggestion.tenant,
            ).first()
        deal = None
        if suggestion.target_deal_id:
            deal = Deal.objects.filter(
                id=suggestion.target_deal_id,
                tenant=suggestion.tenant,
            ).first()

        resolved_kind = _resolve_suggestion_kind(proposed, activity_type)
        record = create_activity(
            kind=resolved_kind,
            title=proposed.get("title", f"Follow-up: {suggestion.reason}"),
            content=proposed.get("content", {}),
            tenant=suggestion.tenant,
            user=user,
            source="suggestion",
            activity_type=activity_type,
            status="planned",
            scheduled_at=proposed.get("scheduled_at"),
            contact=contact,
            customer=customer,
            deal=deal,
            owner=user,
            created_by=user,
            reason=suggestion.reason,
        )

        suggestion.activity_record = record
        suggestion.status = ActivitySuggestionStatus.ACCEPTED
        suggestion.save(update_fields=["activity_record", "status"])
        return record


def dismiss_suggestion(suggestion_id: str, tenant=None) -> None:
    """Mark suggestion as dismissed."""
    with transaction.atomic():
        qs = ActivitySuggestion.objects.select_for_update().filter(id=suggestion_id)
        if tenant is not None:
            qs = qs.filter(tenant=tenant)
        suggestion = get_object_or_404(qs)
        if suggestion.status != ActivitySuggestionStatus.PENDING:
            raise ValueError(f"Suggestion is not pending: {suggestion.status}")
        suggestion.status = ActivitySuggestionStatus.DISMISSED
        suggestion.save(update_fields=["status"])
