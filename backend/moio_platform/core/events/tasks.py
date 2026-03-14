"""
Celery tasks for event routing.
"""

import logging
from uuid import UUID

from celery import shared_task
from django.db import ProgrammingError

from central_hub.models import Tenant

from moio_platform.settings import FLOWS_Q
from tenancy.tenant_support import tenant_rls_context

logger = logging.getLogger(__name__)


def _resolve_schema_name(event_uuid: UUID, tenant_id: str | None) -> str | None:
    """Resolve tenant schema for an event task."""
    if tenant_id:
        try:
            tenant_uuid = UUID(str(tenant_id))
        except (TypeError, ValueError):
            logger.error("Invalid tenant_id=%s for event=%s", tenant_id, event_uuid)
            return None
        tenant = Tenant.objects.filter(tenant_code=tenant_uuid).only("schema_name").first()
        return getattr(tenant, "schema_name", None) if tenant else None

    # Backward-compatibility: older queued jobs may not include tenant_id.
    # Scan tenant schemas to find where this EventLog lives.
    logger.warning("Missing tenant_id for event=%s, scanning tenant schemas", event_uuid)
    for tenant in Tenant.objects.only("schema_name").iterator():
        schema_name = getattr(tenant, "schema_name", None)
        if not schema_name:
            continue
        try:
            with tenant_rls_context(schema_name):
                from flows.models import EventLog

                if EventLog.objects.filter(id=event_uuid).exists():
                    return schema_name
        except Exception:
            continue
    return None


@shared_task(
    name="events.route_event",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    queue=FLOWS_Q,
)
def route_event_task(self, event_id: str, tenant_id: str | None = None):
    """
    Celery task to route an event to matching flows.
    
    Args:
        event_id: String UUID of the EventLog entry
    """
    from .router import route_event

    logger.info(f"Routing event: {event_id}")

    try:
        event_uuid = UUID(event_id)
        schema_name = _resolve_schema_name(event_uuid, tenant_id)
        if not schema_name:
            logger.error(
                "Cannot route event %s: unable to resolve tenant schema",
                event_id,
            )
            return {
                "event_id": event_id,
                "flow_executions": [],
                "status": "skipped_tenant_not_found",
            }

        with tenant_rls_context(schema_name):
            results = route_event(event_uuid)
        logger.info(f"Event {event_id} routed to {len(results)} flow(s)")
        # Best-effort: create ActivityRecords for contact-related events (never fail routing)
        try:
            from crm.services.event_activity_ingestion import create_activities_from_event
            n = create_activities_from_event(event_uuid)
            if n:
                logger.info(f"Event {event_id} created {n} activity record(s)")
        except Exception as ingesting_err:
            logger.warning("Event activity ingestion failed for %s: %s", event_id, ingesting_err)
        return {
            "event_id": event_id,
            "flow_executions": results,
            "status": "routed",
        }
    except ValueError as e:
        logger.error(
            "Invalid event_id %s for event routing task: %s",
            event_id,
            e,
        )
        return {
            "event_id": event_id,
            "flow_executions": [],
            "status": "skipped_invalid_event_id",
        }
    except ProgrammingError as e:
        if 'relation "flows_event_log" does not exist' in str(e):
            logger.error(
                "Event routing skipped for %s because tenant schema tables are unavailable: %s",
                event_id,
                e,
            )
            return {
                "event_id": event_id,
                "flow_executions": [],
                "status": "skipped_missing_eventlog_table",
            }
        logger.error(f"Error routing event {event_id}: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Error routing event {event_id}: {e}", exc_info=True)
        raise
