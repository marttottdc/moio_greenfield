import uuid

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


@pytest.mark.django_db
def test_events_api_marks_canonical_vs_db_only(client, tenant):
    """
    /api/v1/flows/events/ should:
      - include canonical-only events from code
      - mark DB-only (non-canonical) events as non-emittable under strict contract
    """
    from flows.models import EventDefinition

    User = get_user_model()
    user = User.objects.create_user(
        email=f"events-{uuid.uuid4().hex[:8]}@example.com",
        username=f"events-{uuid.uuid4().hex[:8]}",
        password="secret",
        tenant=tenant,
    )
    client.force_login(user)

    EventDefinition.objects.create(
        name="custom.db_only",
        label="DB Only Event",
        description="Not in canonical schemas",
        entity_type="custom",
        category="custom",
        payload_schema={"type": "object"},
        hints={},
        active=True,
    )

    url = reverse("flows_api:event_definition_list")
    resp = client.get(url)
    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body

    db_only = next(e for e in body["events"] if e["name"] == "custom.db_only")
    assert db_only["is_canonical"] is False
    assert db_only["is_emittable"] is False
    assert db_only["payload_schema"] == {}

    # Canonical event should exist even if not present in DB.
    deal_created = next(e for e in body["events"] if e["name"] == "deal.created")
    assert deal_created["is_canonical"] is True
    assert deal_created["is_emittable"] is True

