from django.test import SimpleTestCase

from moio_platform.core.events.schemas import get_event_payload_schema


class EventSchemaTests(SimpleTestCase):
    def test_email_received_schema_exists(self):
        schema = get_event_payload_schema("email.received")
        self.assertIn("message", schema["properties"])

    def test_calendar_event_received_schema_exists(self):
        schema = get_event_payload_schema("calendar.event_received")
        self.assertIn("event", schema["properties"])

