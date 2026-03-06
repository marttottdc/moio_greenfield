"""
Celery tasks for event routing.
"""

import logging
from uuid import UUID

from celery import shared_task

from moio_platform.settings import FLOWS_Q

logger = logging.getLogger(__name__)


@shared_task(
    name="events.route_event",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    queue=FLOWS_Q,
)
def route_event_task(self, event_id: str):
    """
    Celery task to route an event to matching flows.
    
    Args:
        event_id: String UUID of the EventLog entry
    """
    from .router import route_event
    
    logger.info(f"Routing event: {event_id}")
    
    try:
        results = route_event(UUID(event_id))
        logger.info(f"Event {event_id} routed to {len(results)} flow(s)")
        # Best-effort: create ActivityRecords for contact-related events (never fail routing)
        try:
            from crm.services.event_activity_ingestion import create_activities_from_event
            n = create_activities_from_event(UUID(event_id))
            if n:
                logger.info(f"Event {event_id} created {n} activity record(s)")
        except Exception as ingesting_err:
            logger.warning("Event activity ingestion failed for %s: %s", event_id, ingesting_err)
        return {
            "event_id": event_id,
            "flow_executions": results,
            "status": "routed",
        }
    except Exception as e:
        logger.error(f"Error routing event {event_id}: {e}", exc_info=True)
        raise
