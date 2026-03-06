import uuid

import pytest

from moio_platform.core.events import emit_event
from moio_platform.core.events import emitter as emitter_module


@pytest.mark.django_db
def test_can_emit_communications_session_events(monkeypatch):
    from flows.models import EventLog

    monkeypatch.setattr(emitter_module, "_dispatch_to_router", lambda *_args, **_kwargs: None)

    tenant_id = uuid.uuid4()
    event_id = emit_event(
        name="communications.session_started",
        tenant_id=tenant_id,
        payload={"session_id": "sess-1"},
        source="test",
        defer_routing=False,
    )
    assert EventLog.objects.filter(id=event_id, name="communications.session_started").exists()

    event_id2 = emit_event(
        name="communications.session_ended",
        tenant_id=tenant_id,
        payload={"session_id": "sess-1"},
        source="test",
        defer_routing=False,
    )
    assert EventLog.objects.filter(id=event_id2, name="communications.session_ended").exists()


@pytest.mark.django_db
def test_can_emit_flow_execution_completed_event(monkeypatch):
    from flows.models import EventLog

    monkeypatch.setattr(emitter_module, "_dispatch_to_router", lambda *_args, **_kwargs: None)

    tenant_id = uuid.uuid4()
    event_id = emit_event(
        name="flow.execution_completed",
        tenant_id=tenant_id,
        payload={"flow_id": "flow-1", "execution_id": "exec-1"},
        source="test",
        defer_routing=False,
    )
    assert EventLog.objects.filter(id=event_id, name="flow.execution_completed").exists()


