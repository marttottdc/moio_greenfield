# services/activity_service.py
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from crm.core.activity_schemas import validate_content
from crm.models import (
    ActivityKind,
    ActivityRecord,
    ActivitySourceChoices,
    ActivityType,
    UserModel,
)
from crm.services.activity_payloads import PAYLOAD_MODEL_BY_KIND
import logging

logger = logging.getLogger(__name__)


# ===============================
# CENTRAL ACTIVITY MANAGER
# ===============================

class ActivityManager:
    """
    Central orchestrator for activity lifecycle management.

    Handles:
    - Activity creation with type-specific logic
    - Event emission and side effect triggering
    - Orchestration rules and relationships
    - Lifecycle management (status transitions, etc.)
    """

    def __init__(self):
        self._strategies = {}
        self._side_effects = {}
        self._event_handlers = {}

    def register_strategy(self, activity_key: str, strategy_class):
        """Register activity type strategy"""
        self._strategies[activity_key] = strategy_class()

    def register_side_effect(self, trigger_key: str, effect_class):
        """Register side effect for activity type"""
        if trigger_key not in self._side_effects:
            self._side_effects[trigger_key] = []
        self._side_effects[trigger_key].append(effect_class())

    def register_event_handler(self, event_type: str, handler_class):
        """Register event handler"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler_class())

    def create_activity(self, activity_data: dict, **kwargs) -> ActivityRecord:
        """
        Central activity creation with orchestration.

        1. Validate and create base activity
        2. Apply type-specific strategy
        3. Trigger side effects
        4. Emit events
        """
        # Get activity type info
        activity_key = activity_data.get('type_key') or f"{activity_data.get('kind', 'other')}.default"

        # create_activity only accepts a subset of ActivityRecord fields.
        # Keep additional ActivityRecord attributes to apply after creation.
        create_data = dict(activity_data)
        if "client_id" in create_data:
            if "customer_id" not in create_data:
                create_data["customer_id"] = create_data["client_id"]
            create_data.pop("client_id", None)
        deferred_updates = {}
        for field in (
            "contact_id",
            "customer_id",
            "deal_id",
            "ticket_id",
            "owner_id",
            "created_by_id",
            "occurred_at",
            "completed_at",
            "duration_minutes",
        ):
            if field in create_data:
                deferred_updates[field] = create_data.pop(field)
        create_data.pop("type_key", None)

        # Create the base row and deferred FK/id updates atomically so
        # invalid deferred values cannot leave orphaned activity records.
        with transaction.atomic():
            activity = create_activity(**create_data, **kwargs)
            if deferred_updates:
                for field, value in deferred_updates.items():
                    setattr(activity, field, value)
                activity.save(update_fields=list(deferred_updates.keys()))

        # Apply strategy if exists
        if activity_key in self._strategies:
            strategy = self._strategies[activity_key]
            activity = strategy.process_creation(activity, activity_data)

        # Trigger side effects
        self._trigger_side_effects(activity, activity_data)

        # Emit creation event
        self._emit_event('activity.created', activity, activity_data)

        return activity

    def update_activity(self, activity_id: str, updates: dict, **kwargs) -> ActivityRecord:
        """Central activity update with orchestration"""
        activity = update_activity(activity_id, updates)

        # Apply strategy if exists
        activity_key = getattr(activity.type, 'key', f"{activity.kind}.default")
        if activity_key in self._strategies:
            strategy = self._strategies[activity_key]
            activity = strategy.process_update(activity, updates)

        # Emit update event
        self._emit_event('activity.updated', activity, updates)

        return activity

    def transition_status(self, activity_id: str, new_status: str, **kwargs) -> ActivityRecord:
        """Handle status transitions with orchestration"""
        activity = get_object_or_404(ActivityRecord, id=activity_id)

        # Validate transition
        old_status = activity.status
        activity.status = new_status
        activity.save()

        # Emit status change event
        self._emit_event('activity.status_changed', activity, {
            'old_status': old_status,
            'new_status': new_status,
            **kwargs
        })

        # Trigger status-specific side effects
        self._trigger_status_effects(activity, old_status, new_status)

        return activity

    def _trigger_side_effects(self, activity: ActivityRecord, context: dict):
        """Trigger side effects for activity"""
        activity_key = getattr(activity.type, 'key', f"{activity.kind}.default")

        if activity_key in self._side_effects:
            for effect in self._side_effects[activity_key]:
                try:
                    effect.execute(activity, context)
                except Exception as e:
                    logger.error(f"Side effect failed for {activity_key}: {e}")

    def _trigger_status_effects(self, activity: ActivityRecord, old_status: str, new_status: str):
        """Trigger status transition side effects"""
        status_key = f"status.{old_status}_to_{new_status}"

        if status_key in self._side_effects:
            for effect in self._side_effects[status_key]:
                try:
                    effect.execute(activity, {'old_status': old_status, 'new_status': new_status})
                except Exception as e:
                    logger.error(f"Status effect failed for {status_key}: {e}")

    def _emit_event(self, event_type: str, activity: ActivityRecord, context: dict):
        """Emit activity events to handlers"""
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    handler.handle(activity, context)
                except Exception as e:
                    logger.error(f"Event handler failed for {event_type}: {e}")

        # Also emit via Moio events system
        try:
            from moio_platform.core.events import emit_event
            emit_event(
                name=f"crm.{event_type}",
                tenant_id=str(activity.tenant_id),
                entity={"type": "activity", "id": str(activity.id)},
                payload={
                    "activity_id": str(activity.id),
                    "activity_type": getattr(activity.type, 'key', activity.kind),
                    "status": activity.status,
                    **context
                }
            )
        except Exception as e:
            logger.error(f"Failed to emit event {event_type}: {e}")


# ===============================
# ACTIVITY STRATEGIES
# ===============================

class ActivityStrategy:
    """Base class for activity type strategies"""

    def process_creation(self, activity: ActivityRecord, context: dict) -> ActivityRecord:
        """Process activity creation with type-specific logic"""
        return activity

    def process_update(self, activity: ActivityRecord, updates: dict) -> ActivityRecord:
        """Process activity updates with type-specific logic"""
        return activity


class MeetingStrategy(ActivityStrategy):
    """Strategy for meeting activities"""

    def process_creation(self, activity: ActivityRecord, context: dict) -> ActivityRecord:
        """Auto-create calendar event for meetings"""
        if activity.scheduled_at and context.get('attendees'):
            logger.info(f"Would create calendar event for meeting: {activity.title}")
            # TODO: Integrate with calendar service
        return activity


class TaskStrategy(ActivityStrategy):
    """Strategy for task activities"""

    def process_creation(self, activity: ActivityRecord, context: dict) -> ActivityRecord:
        """Set default due dates and priorities for tasks"""
        if not activity.scheduled_at and context.get('priority') == 'high':
            from django.utils import timezone
            from datetime import timedelta
            activity.scheduled_at = timezone.now() + timedelta(hours=24)
            activity.save()
        return activity


# ===============================
# SIDE EFFECTS
# ===============================

class SideEffect:
    """Base class for activity side effects"""

    def execute(self, activity: ActivityRecord, context: dict):
        """Execute the side effect"""
        raise NotImplementedError


class NotificationSideEffect(SideEffect):
    """Send notifications for activities"""

    def execute(self, activity: ActivityRecord, context: dict):
        """Send notifications to relevant users"""
        logger.info(f"Would send notification for activity: {activity.title}")
        # TODO: Implement notification logic


class CalendarSyncSideEffect(SideEffect):
    """Sync activities with calendar"""

    def execute(self, activity: ActivityRecord, context: dict):
        """Create/update calendar events"""
        logger.info(f"Would sync calendar for activity: {activity.title}")
        # TODO: Integrate with calendar service


# ===============================
# EVENT HANDLERS
# ===============================

class EventHandler:
    """Base class for activity event handlers"""

    def handle(self, activity: ActivityRecord, context: dict):
        """Handle the event"""
        raise NotImplementedError


class AuditHandler(EventHandler):
    """Log activity events for audit"""

    def handle(self, activity: ActivityRecord, context: dict):
        """Log activity events"""
        logger.info(f"Activity event: {context.get('event_type', 'unknown')} for {activity.title}")


# ===============================
# GLOBAL ACTIVITY MANAGER INSTANCE
# ===============================

activity_manager = ActivityManager()

# Register default strategies
activity_manager.register_strategy("meeting.in_person", MeetingStrategy)
activity_manager.register_strategy("meeting.remote", MeetingStrategy)
activity_manager.register_strategy("task.follow_up", TaskStrategy)

# Register default side effects
activity_manager.register_side_effect("meeting.in_person", CalendarSyncSideEffect)
activity_manager.register_side_effect("meeting.remote", CalendarSyncSideEffect)
activity_manager.register_side_effect("task.follow_up", NotificationSideEffect)

# Register event handlers
activity_manager.register_event_handler("activity.created", AuditHandler)
activity_manager.register_event_handler("activity.updated", AuditHandler)
activity_manager.register_event_handler("activity.status_changed", AuditHandler)


def _normalize_content(
    content: Any,
    *,
    kind: str,
    activity_type: Optional[ActivityType] = None,
) -> Dict[str, Any]:
    """Validate and return content dict. Uses type.schema if set, else PAYLOAD_MODEL_BY_KIND."""
    if content is None:
        content = {}
    has_type_schema = bool(
        activity_type and isinstance(getattr(activity_type, "schema", None), dict)
    )
    try:
        return validate_content(
            activity_type or type("_", (), {"kind": kind, "type": activity_type})(),
            content,
            kind=kind,
        )
    except Exception:
        if has_type_schema or kind in PAYLOAD_MODEL_BY_KIND:
            raise
        return content if isinstance(content, dict) else {}


def create_activity(
    kind: str,
    title: str,
    content: Any,
    tenant,
    user=None,
    source=None,
    visibility=None,
    *,
    activity_type: Optional[ActivityType] = None,
    status: Optional[str] = None,
    scheduled_at=None,
    contact=None,
    customer=None,
    client=None,
    deal=None,
    ticket=None,
    owner=None,
    created_by=None,
    tags: Optional[List[str]] = None,
    reason: str = "",
    needs_confirmation: bool = False,
) -> ActivityRecord:
    if kind not in ActivityKind.values:
        raise ValueError(f"Invalid kind: {kind}")

    content = _normalize_content(content, kind=kind, activity_type=activity_type)
    source_value = (
        source if source in ActivitySourceChoices.values else ActivitySourceChoices.MANUAL
    )
    if customer is None and client is not None:
        customer = client

    return ActivityRecord.objects.create(
        kind=kind,
        title=title or "No Title",
        content=content,
        tenant=tenant,
        user=user,
        source=source_value,
        visibility=visibility or ActivityRecord._meta.get_field("visibility").default,
        created_at=timezone.now(),
        type=activity_type,
        status=status or "completed",
        scheduled_at=scheduled_at,
        contact=contact,
        customer=customer,
        deal=deal,
        ticket=ticket,
        owner=owner or user,
        created_by=created_by or user,
        tags=tags or [],
        reason=reason,
        needs_confirmation=needs_confirmation,
    )


def update_activity(record_id, updates: dict) -> ActivityRecord:
    record = get_object_or_404(ActivityRecord, id=record_id)

    if "content" in updates:
        updates["content"] = _normalize_content(
            updates["content"],
            kind=updates.get("kind", record.kind),
            activity_type=updates.get("type", record.type),
        )

    for key, value in updates.items():
        if hasattr(record, key):
            setattr(record, key, value)
    record.save()
    return record


def delete_activity(record_id):
    record = get_object_or_404(ActivityRecord, id=record_id)
    record.delete()
    return True


def query_activities(
    kind: str,
    user: Optional[UserModel] = None,
    search: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    order: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> List[ActivityRecord]:
    """
    Generic retrieval engine.
    - `kind`            mandatory: "task" | "note" | ...
    - `user`            optional: limit to that user
    - `search`          full-text search in title + json content (simple ILIKE)
    - `filters`         dict of field look-ups; accepts dotted paths into JSON
                        e.g. {"content.due_date__lte": "2025-07-20",
                              "content.priority": 1}
    - `order`           list of ORM order strings, default = ["-created_at"]
    - `limit`           cap the result count
    """
    qs = ActivityRecord.objects.filter(kind=kind)

    if user:
        qs = qs.filter(user=user)

    # Dynamic JSON / scalar filters
    if filters:
        for lookup, value in filters.items():
            if lookup.startswith("content."):
                # Convert "content.due_date__lte" → "content__due_date__lte"
                lookup = lookup.replace("content.", "content__")
            qs = qs.filter(**{lookup: value})

    # Simple free-text search (title + any JSON string values)
    if search:
        qs = qs.filter(
            Q(title__icontains=search) |
            Q(content__icontains=search)      # works in Postgres; uses ->> cast
        )

    qs = qs.order_by(*(order or ["-created_at"]))
    return list(qs[:limit] if limit else qs)
