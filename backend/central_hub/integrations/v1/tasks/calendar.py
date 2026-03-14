from __future__ import annotations

import logging
from celery import shared_task
from django.conf import settings

from moio_platform.core.events import emit_event
from central_hub.integrations.v1.models import CalendarAccount
from central_hub.integrations.v1.normalizers.calendar import normalize_event
from central_hub.integrations.v1.fetchers import google_calendar, outlook_calendar

logger = logging.getLogger(__name__)


def _select_fetcher(provider: str):
    if provider == "google":
        return google_calendar
    if provider == "microsoft":
        return outlook_calendar
    raise ValueError(f"Unsupported provider for calendar: {provider}")


@shared_task(bind=True, name="integrations.calendar_ingest", queue=settings.LOW_PRIORITY_Q)
def calendar_ingest(self, calendar_account_id: str):
    account = CalendarAccount.objects.select_related("external_account", "tenant").get(id=calendar_account_id)
    external = account.external_account
    fetcher = _select_fetcher(external.provider)

    raw_items, new_state = fetcher.fetch(external.state or {})
    if new_state is not None:
        external.state = new_state
        external.save(update_fields=["state"])

    for raw in raw_items:
        normalized = normalize_event(external.provider, account.id, raw)
        emit_event(
            name="calendar.event_received",
            tenant_id=account.tenant_id,
            payload=normalized,
            source="integrations",
        )
    return {"fetched": len(raw_items)}

