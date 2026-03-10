"""
Tests for event → ActivityRecord ingestion (event_activity_ingestion).
"""
from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from crm.models import ActivityRecord, Contact, Deal, Pipeline, PipelineStage, Ticket
from crm.services.event_activity_ingestion import create_activities_from_event
from flows.models import EventLog
from central_hub.models import Tenant


def _get_tenant():
    tenant, _ = Tenant.objects.get_or_create(
        id=1,
        defaults={"nombre": "Test Tenant", "domain": "test.example.com"},
    )
    return tenant


@pytest.mark.django_db
def test_deal_created_creates_one_activity_for_contact():
    """Deal event creates one ActivityRecord for the deal's contact."""
    tenant = _get_tenant()
    contact = Contact.objects.create(
        tenant=tenant,
        fullname="Alice",
        email="alice@test.example.com",
        phone="+123",
    )
    pipeline = Pipeline.objects.create(tenant=tenant, name="Sales", description="", is_active=True)
    stage = PipelineStage.objects.create(
        tenant=tenant, pipeline=pipeline, name="Qualification", description="", order=1, probability=10
    )
    deal = Deal.objects.create(
        tenant=tenant,
        title="ACME Deal",
        description="",
        contact=contact,
        pipeline=pipeline,
        stage=stage,
        value=100,
        currency="USD",
    )
    event = EventLog.objects.create(
        name="deal.created",
        tenant_id=tenant.tenant_code,
        payload={
            "deal_id": str(deal.id),
            "title": deal.title,
        },
        occurred_at=timezone.now(),
        source="test",
    )
    n = create_activities_from_event(event.id)
    assert n == 1
    activities = list(ActivityRecord.objects.filter(tenant=tenant, source="system"))
    assert len(activities) == 1
    act = activities[0]
    assert act.contact_id == contact.user_id
    assert act.deal_id == deal.id
    assert act.title == "Deal created: ACME Deal"
    assert act.content.get("event", {}).get("event_id") == str(event.id)
    assert act.occurred_at is not None


@pytest.mark.django_db
def test_ticket_created_creates_multiple_activities_for_creator_assigned_waiting_for():
    """Ticket event creates one ActivityRecord per involved contact (creator, assigned, waiting_for)."""
    tenant = _get_tenant()
    c1 = Contact.objects.create(tenant=tenant, fullname="Creator", email="c1@test.com", phone="+1")
    c2 = Contact.objects.create(tenant=tenant, fullname="Assigned", email="c2@test.com", phone="+2")
    c3 = Contact.objects.create(tenant=tenant, fullname="Waiting", email="c3@test.com", phone="+3")
    ticket = Ticket.objects.create(
        tenant=tenant,
        service="support",
        type="I",
        description="Help",
        creator=c1,
        assigned=c2,
        waiting_for=c3,
    )
    event = EventLog.objects.create(
        name="ticket.created",
        tenant_id=tenant.tenant_code,
        payload={"ticket_id": str(ticket.id)},
        occurred_at=timezone.now(),
        source="test",
    )
    n = create_activities_from_event(event.id)
    assert n == 3
    activities = list(ActivityRecord.objects.filter(tenant=tenant, source="system").order_by("contact_id"))
    assert len(activities) == 3
    contact_ids = {act.contact_id for act in activities}
    assert contact_ids == {c1.user_id, c2.user_id, c3.user_id}
    for act in activities:
        assert act.ticket_id == ticket.id
        assert act.content.get("event", {}).get("event_id") == str(event.id)


@pytest.mark.django_db
def test_idempotency_running_ingestion_twice_does_not_duplicate():
    """Running create_activities_from_event twice for the same event does not create duplicate activities."""
    tenant = _get_tenant()
    contact = Contact.objects.create(
        tenant=tenant,
        fullname="Bob",
        email="bob@test.example.com",
        phone="+456",
    )
    event = EventLog.objects.create(
        name="contact.created",
        tenant_id=tenant.tenant_code,
        payload={"contact_id": contact.user_id},
        occurred_at=timezone.now(),
        source="test",
    )
    n1 = create_activities_from_event(event.id)
    assert n1 == 1
    n2 = create_activities_from_event(event.id)
    assert n2 == 0
    assert ActivityRecord.objects.filter(tenant=tenant, source="system").count() == 1


@pytest.mark.django_db
def test_loop_prevention_crm_activity_events_produce_zero_activities():
    """Event name crm.activity.created (and any crm.activity.*) produces zero new activities."""
    tenant = _get_tenant()
    contact = Contact.objects.create(
        tenant=tenant,
        fullname="Loop",
        email="loop@test.example.com",
        phone="+789",
    )
    event = EventLog.objects.create(
        name="crm.activity.created",
        tenant_id=tenant.tenant_code,
        payload={"contact_id": contact.user_id, "activity_id": str(uuid.uuid4())},
        occurred_at=timezone.now(),
        source="test",
    )
    n = create_activities_from_event(event.id)
    assert n == 0
    assert ActivityRecord.objects.filter(tenant=tenant, source="system").count() == 0
