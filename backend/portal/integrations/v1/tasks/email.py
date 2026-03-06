from __future__ import annotations

import logging
from celery import shared_task

from moio_platform.core.events import emit_event
from portal.integrations.v1.models import EmailAccount
from portal.integrations.v1.normalizers.email import normalize_email
from portal.integrations.v1.fetchers import gmail, outlook, imap

logger = logging.getLogger(__name__)


def _select_fetcher(provider: str):
    if provider == "google":
        return gmail
    if provider == "microsoft":
        return outlook
    if provider == "imap":
        return imap
    raise ValueError(f"Unsupported provider: {provider}")


@shared_task(bind=True, name="integrations.email_ingest")
def email_ingest(self, email_account_id: str):
    account = EmailAccount.objects.select_related("external_account", "tenant").get(id=email_account_id)
    external = account.external_account
    fetcher = _select_fetcher(external.provider)

    raw_items, new_state = fetcher.fetch(external.state or {})
    if new_state is not None:
        external.state = new_state
        external.save(update_fields=["state"])

    for raw in raw_items:
        normalized = normalize_email(external.provider, account.id, raw)
        emit_event(
            name="email.received",
            tenant_id=account.tenant_id,
            payload=normalized,
            source="integrations",
        )
    return {"fetched": len(raw_items)}

