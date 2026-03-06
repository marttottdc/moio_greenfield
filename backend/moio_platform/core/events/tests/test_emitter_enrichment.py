import uuid

import pytest

from moio_platform.core.events import emit_event
from moio_platform.core.events import emitter as emitter_module


@pytest.mark.django_db
def test_emit_event_enriches_deal_payload_with_description_and_contact_snapshot(monkeypatch, tenant, user_factory):
    """
    If an event payload contains deal_id/contact_id, emitter should add:
    - description for the deal (when missing)
    - contact snapshot under payload.contact (when missing)
    """
    from crm.models import Contact, Deal, Pipeline, PipelineStage
    from flows.models import EventLog

    # Avoid routing side-effects in this unit test.
    monkeypatch.setattr(emitter_module, "_dispatch_to_router", lambda *_args, **_kwargs: None)

    user = user_factory(email=f"evt-{uuid.uuid4().hex[:8]}@example.com", username=f"evt-{uuid.uuid4().hex[:8]}", tenant=tenant)
    contact = Contact.objects.create(tenant=tenant, fullname="Alice", email="alice@example.com", phone="+123")

    pipeline = Pipeline.objects.create(tenant=tenant, name="Sales", description="", is_active=True)
    stage = PipelineStage.objects.create(tenant=tenant, pipeline=pipeline, name="Qualification", description="", order=1, probability=10)
    deal = Deal.objects.create(
        tenant=tenant,
        title="ACME Deal",
        description="Important context",
        contact=contact,
        pipeline=pipeline,
        stage=stage,
        value=100,
        currency="USD",
        created_by=user,
    )

    event_id = emit_event(
        name="deal.created",
        tenant_id=tenant.tenant_code,
        actor={"type": "user", "id": str(user.id)},
        entity={"type": "deal", "id": str(deal.id)},
        payload={
            "deal_id": str(deal.id),
            "title": deal.title,
            "contact_id": str(contact.user_id),
            # Intentionally omit description + contact snapshot to exercise enrichment.
        },
        source="test",
        defer_routing=False,
    )

    logged = EventLog.objects.get(id=event_id)
    assert logged.payload.get("description") == "Important context"
    assert isinstance(logged.payload.get("contact"), dict)
    assert logged.payload["contact"].get("email") == "alice@example.com"


