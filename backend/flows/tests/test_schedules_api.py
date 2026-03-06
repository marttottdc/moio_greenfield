import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from flows.models import FlowSchedule, FlowVersion, FlowVersionStatus


@pytest.mark.django_db
def test_schedule_create_when_missing(client, tenant, flow_factory):
    User = get_user_model()
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create_user(
        email=f"schedule-owner-{suffix}@example.com",
        username=f"schedule-owner-{suffix}",
        password="secret",
        tenant=tenant,
    )
    client.force_login(user)

    flow = flow_factory(tenant=tenant, created_by=user)
    url = reverse("flows_api:flow_schedule_list", args=[flow.id])

    resp = client.post(url, data={"schedule_type": "cron", "cron_expression": "0 9 * * *", "timezone": "UTC"})
    assert resp.status_code == 201, resp.content
    payload = resp.json()
    assert payload["success"] is True


@pytest.mark.django_db
def test_draft_save_does_not_delete_schedule_driven_by_published_version(client, tenant, flow_factory):
    """Regression: draft clone/save without trigger_scheduled must not delete FlowSchedule."""
    User = get_user_model()
    suffix = uuid.uuid4().hex[:8]
    user = User.objects.create_user(
        email=f"schedule-owner2-{suffix}@example.com",
        username=f"schedule-owner2-{suffix}",
        password="secret",
        tenant=tenant,
    )
    client.force_login(user)

    flow = flow_factory(tenant=tenant, created_by=user)

    # Published version with scheduled trigger drives schedule.
    published = FlowVersion.objects.create(
        flow=flow,
        tenant=tenant,
        status=FlowVersionStatus.PUBLISHED,
        graph={
            "nodes": [
                {"id": "trig", "kind": "trigger_scheduled", "config": {"schedule_type": "cron", "cron_expression": "0 9 * * *", "timezone": "UTC"}}
            ],
            "edges": [],
        },
        created_by=user,
    )
    # Ensure the signal has a chance to create the schedule by explicitly saving.
    published.save()

    assert FlowSchedule.objects.filter(flow=flow).exists()
    schedule_id = str(FlowSchedule.objects.get(flow=flow).id)

    # Draft version without trigger_scheduled should not delete schedule.
    draft = FlowVersion.objects.create(flow=flow, tenant=tenant, graph={"nodes": [], "edges": []}, created_by=user)
    draft.save()

    assert FlowSchedule.objects.filter(flow=flow).exists()
    assert str(FlowSchedule.objects.get(flow=flow).id) == schedule_id


