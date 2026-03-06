import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

from flows.models import FlowExecution


pytestmark = pytest.mark.django_db


def _utc_now():
    return datetime.now(timezone.utc)


def test_execution_messages_groups_by_msg_id(client, tenant, flow_factory):
    flow = flow_factory()
    user_model = get_user_model()
    user = user_model.objects.create_user(
        email="tester@example.com",
        username="tester",
        password="secret",
        tenant=tenant,
    )
    client.force_login(user)

    execution = FlowExecution.objects.create(
        flow=flow,
        status="success",
        started_at=_utc_now(),
    )

    msg_id = "wamid.ABCD1234"

    # Seed outbound log (has flow_execution_id)
    from chatbot.models.wa_message_log import WaMessageLog

    WaMessageLog.objects.create(
        tenant=tenant,
        flow_execution_id=execution.id,
        msg_id=msg_id,
        status="sent",
        type="text",
        body="Hello!",
        timestamp=_utc_now(),
    )

    # Later delivery update (no flow_execution_id)
    WaMessageLog.objects.create(
        tenant=tenant,
        flow_execution_id=None,
        msg_id=msg_id,
        status="delivered",
        type=None,
        body=None,
        timestamp=_utc_now() + timedelta(seconds=5),
    )

    url = reverse("flows_api:api_execution_messages", args=[execution.id])
    response = client.get(url)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["seed_msg_ids_count"] == 1
    threads = payload.get("threads") or []
    assert len(threads) == 1
    thread = threads[0]
    assert thread["msg_id"] == msg_id
    assert thread["latest_status"] == "delivered"
    events = thread.get("events") or []
    statuses = [e.get("status") for e in events]
    assert statuses == ["sent", "delivered"]

