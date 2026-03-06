from moio_platform.core.events.router import _extract_flow_input_payload


def test_extract_flow_input_payload_returns_domain_payload_when_already_domain_dict():
    envelope = {
        "id": "evt-1",
        "name": "deal.stage_changed",
        "payload": {"title": "ACME", "pipeline_id": "p1"},
    }
    assert _extract_flow_input_payload(envelope) == {"title": "ACME", "pipeline_id": "p1"}


def test_extract_flow_input_payload_unwraps_body_from_transport_envelope():
    envelope = {
        "id": "evt-1",
        "name": "deal.stage_changed",
        "payload": {
            "path": "/crm/events/deal.stage_changed",
            "method": "POST",
            "body": {"title": "ACME", "pipeline_id": "p1"},
        },
    }
    assert _extract_flow_input_payload(envelope) == {"title": "ACME", "pipeline_id": "p1"}


def test_extract_flow_input_payload_unwraps_nested_payload_envelope():
    envelope = {
        "id": "evt-1",
        "name": "deal.stage_changed",
        "payload": {
            "payload": {
                "path": "/crm/events/deal.stage_changed",
                "body": {"title": "ACME", "pipeline_id": "p1"},
            }
        },
    }
    assert _extract_flow_input_payload(envelope) == {"title": "ACME", "pipeline_id": "p1"}


def test_extract_flow_input_payload_returns_empty_dict_when_payload_is_not_a_dict():
    assert _extract_flow_input_payload({"payload": "nope"}) == {}
    assert _extract_flow_input_payload({"payload": None}) == {}
    assert _extract_flow_input_payload(None) == {}

