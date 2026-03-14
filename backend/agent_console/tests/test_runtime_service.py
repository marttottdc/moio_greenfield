from django.test import SimpleTestCase

from agent_console.services.runtime_service import (
    _api_connection_resolver,
    runtime_base_url_from_request,
    runtime_base_url_from_scope,
    runtime_initiator_from_user,
)


class _DummyRequest:
    def build_absolute_uri(self, location="/"):
        if location != "/":
            raise AssertionError("Unexpected location")
        return "https://console.example.test/agent-console/"


class _DummyUser:
    id = 7
    email = "Agent@Test.Example"
    tenant_id = "tenant-123"
    is_superuser = False
    is_staff = False
    username = "agent-user"

    def get_full_name(self):
        return ""


class RuntimeServiceTests(SimpleTestCase):
    def test_runtime_base_url_from_scope_prefers_forwarded_headers(self):
        scope = {
            "scheme": "ws",
            "headers": [
                (b"x-forwarded-proto", b"https"),
                (b"x-forwarded-host", b"console.example.test"),
                (b"host", b"internal:8000"),
            ],
        }

        self.assertEqual(runtime_base_url_from_scope(scope), "https://console.example.test")

    def test_runtime_base_url_from_request_uses_origin_only(self):
        self.assertEqual(
            runtime_base_url_from_request(_DummyRequest()),
            "https://console.example.test",
        )

    def test_runtime_initiator_includes_runtime_base_url(self):
        initiator = runtime_initiator_from_user(_DummyUser(), base_url="https://console.example.test/app/")

        self.assertEqual(initiator["runtimeBaseUrl"], "https://console.example.test")
        self.assertEqual(initiator["email"], "agent@test.example")

    def test_api_connection_resolver_prefers_runtime_base_url(self):
        resolved = _api_connection_resolver(
            "moio_internal",
            initiator={"runtimeBaseUrl": "https://console.example.test/runtime/"},
        )

        self.assertEqual(resolved["baseUrl"], "https://console.example.test")
        self.assertEqual(resolved["authType"], "initiator_bearer")
        self.assertEqual(resolved["source"], "internal_api")
