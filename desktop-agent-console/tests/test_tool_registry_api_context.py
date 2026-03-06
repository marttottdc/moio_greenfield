from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from moio_runtime.tools import ToolError, ToolRegistry


class ToolRegistryApiContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _make_registry(self, resolver):
        registry = ToolRegistry(
            workspace_root=self.root,
            shell_enabled=False,
            shell_timeout_seconds=1.0,
            docker_enabled=False,
            docker_timeout_seconds=1.0,
            dynamic_tools_enabled=False,
            dynamic_tools_dir=self.root / "dynamic-tools",
            package_install_enabled=False,
            package_install_timeout_seconds=1.0,
            vault_enabled=False,
            vault_file=self.root / "vault" / "secrets.enc.json",
            vault_passphrase=None,
            api_connection_resolver=resolver,
        )
        return registry

    async def test_api_run_passes_initiator_to_connection_resolver(self) -> None:
        seen: list[dict[str, object] | None] = []

        def resolver(connection_name: str, *, initiator=None):
            seen.append(dict(initiator) if isinstance(initiator, dict) else None)
            return {
                "name": connection_name,
                "baseUrl": "https://example.test/api",
                "protocol": "rest",
                "authType": "none",
                "defaultHeaders": {},
                "timeoutSeconds": 5.0,
                "source": "integration_catalog",
            }

        registry = self._make_registry(resolver)

        def fake_http_request(**kwargs):
            return {
                "ok": True,
                "url": str(kwargs.get("url", "")),
                "status_code": 200,
                "content_type": "application/json",
                "headers": {},
                "body_bytes": b"{\"ok\": true}",
            }

        registry._http_request = fake_http_request  # type: ignore[method-assign]

        result = await registry.execute(
            "api.run",
            {"connection": "crm", "endpoint": "/contacts"},
            execution_context={"initiator": {"id": 41, "tenantRole": "member"}},
        )

        self.assertTrue(result.get("ok"))
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0], {"id": 41, "tenantRole": "member"})

    async def test_api_run_fails_when_user_scoped_credentials_are_missing(self) -> None:
        def resolver(connection_name: str, *, initiator=None):
            return {
                "name": connection_name,
                "baseUrl": "https://example.test/api",
                "protocol": "rest",
                "authType": "bearer",
                "missingCredential": True,
                "missingCredentialReason": "user_credentials_required",
                "source": "integration_catalog",
            }

        registry = self._make_registry(resolver)

        with self.assertRaises(ToolError) as exc:
            await registry.execute(
                "api.run",
                {"connection": "crm", "endpoint": "/contacts"},
                execution_context={"initiator": {"id": 99, "tenantRole": "member"}},
            )

        self.assertIn("not configured for the initiating user", str(exc.exception))

    async def test_api_run_uses_initiator_bearer_auth_for_internal_connection(self) -> None:
        seen_headers: list[dict[str, str]] = []

        def resolver(connection_name: str, *, initiator=None):
            return {
                "name": connection_name,
                "baseUrl": "https://example.test",
                "protocol": "rest",
                "authType": "initiator_bearer",
                "defaultHeaders": {"X-Workspace": "main"},
                "timeoutSeconds": 5.0,
                "source": "internal_api",
            }

        registry = self._make_registry(resolver)

        def fake_http_request(**kwargs):
            headers = kwargs.get("headers")
            if isinstance(headers, dict):
                seen_headers.append(dict(headers))
            return {
                "ok": True,
                "url": str(kwargs.get("url", "")),
                "status_code": 200,
                "content_type": "application/json",
                "headers": {},
                "body_bytes": b"{\"ok\": true}",
            }

        registry._http_request = fake_http_request  # type: ignore[method-assign]

        await registry.execute(
            "api.run",
            {"connection": "moio_internal", "endpoint": "/api/v1/meta/endpoints/"},
            execution_context={"initiator": {"id": 7, "accessToken": "jwt-abc"}},
        )

        self.assertEqual(len(seen_headers), 1)
        self.assertEqual(seen_headers[0].get("Authorization"), "Bearer jwt-abc")
        self.assertEqual(seen_headers[0].get("X-Workspace"), "main")

    async def test_api_run_errors_when_initiator_bearer_token_is_missing(self) -> None:
        def resolver(connection_name: str, *, initiator=None):
            return {
                "name": connection_name,
                "baseUrl": "https://example.test",
                "protocol": "rest",
                "authType": "initiator_bearer",
                "defaultHeaders": {},
                "timeoutSeconds": 5.0,
                "source": "internal_api",
            }

        registry = self._make_registry(resolver)

        with self.assertRaises(ToolError) as exc:
            await registry.execute(
                "api.run",
                {"connection": "moio_internal", "endpoint": "/api/v1/meta/endpoints/"},
                execution_context={"initiator": {"id": 3, "tenantRole": "member"}},
            )

        self.assertIn("access token is unavailable", str(exc.exception))

    async def test_moio_api_run_enriches_with_endpoint_contract(self) -> None:
        seen_connections: list[str] = []
        seen_auth_headers: list[str] = []

        def resolver(connection_name: str, *, initiator=None):
            seen_connections.append(connection_name)
            return {
                "name": connection_name,
                "baseUrl": "https://example.test",
                "protocol": "rest",
                "authType": "initiator_bearer",
                "defaultHeaders": {"X-Workspace": "main"},
                "timeoutSeconds": 5.0,
                "source": "internal_api",
            }

        registry = self._make_registry(resolver)

        def fake_http_request(**kwargs):
            headers = kwargs.get("headers")
            if isinstance(headers, dict):
                seen_auth_headers.append(str(headers.get("Authorization", "")))
            url = str(kwargs.get("url", ""))
            if "/api/v1/meta/endpoints/" in url:
                return {
                    "ok": True,
                    "url": url,
                    "status_code": 200,
                    "content_type": "application/json",
                    "headers": {},
                    "body_bytes": (
                        b'{"endpoints":[{"id":"crm:GET:/api/v1/crm/contacts/","method":"GET",'
                        b'"path":"/api/v1/crm/contacts/","name":"List contacts"}]}'
                    ),
                }
            return {
                "ok": True,
                "url": url,
                "status_code": 200,
                "content_type": "application/json",
                "headers": {},
                "body_bytes": b'{"items":[]}',
            }

        registry._http_request = fake_http_request  # type: ignore[method-assign]

        result = await registry.execute(
            "moio_api.run",
            {"endpoint": "/api/v1/crm/contacts/", "method": "GET"},
            execution_context={"initiator": {"id": 11, "accessToken": "jwt-abc"}},
        )

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("tool"), "moio_api.run")
        request = result.get("request") or {}
        self.assertEqual((request or {}).get("requested_endpoint"), "/api/v1/crm/contacts/")
        self.assertEqual((request or {}).get("endpoint"), "/api/v1/crm/contacts/")
        contract = result.get("endpoint_contract")
        self.assertIsInstance(contract, dict)
        self.assertEqual((contract or {}).get("path"), "/api/v1/crm/contacts/")
        self.assertEqual(seen_connections, ["moio_internal", "moio_internal"])
        self.assertEqual(seen_auth_headers, ["Bearer jwt-abc", "Bearer jwt-abc"])

    async def test_moio_api_run_canonicalizes_missing_trailing_slash(self) -> None:
        seen_urls: list[str] = []

        def resolver(connection_name: str, *, initiator=None):
            return {
                "name": connection_name,
                "baseUrl": "https://example.test",
                "protocol": "rest",
                "authType": "initiator_bearer",
                "defaultHeaders": {},
                "timeoutSeconds": 5.0,
                "source": "internal_api",
            }

        registry = self._make_registry(resolver)

        def fake_http_request(**kwargs):
            url = str(kwargs.get("url", ""))
            seen_urls.append(url)
            if "/api/v1/meta/endpoints/" in url:
                return {
                    "ok": True,
                    "url": url,
                    "status_code": 200,
                    "content_type": "application/json",
                    "headers": {},
                    "body_bytes": (
                        b'{"endpoints":[{"id":"crm:GET:/api/v1/crm/contacts/","method":"GET",'
                        b'"path":"/api/v1/crm/contacts/","name":"List contacts"}]}'
                    ),
                }
            return {
                "ok": True,
                "url": url,
                "status_code": 200,
                "content_type": "application/json",
                "headers": {},
                "body_bytes": b'{"items":[]}',
            }

        registry._http_request = fake_http_request  # type: ignore[method-assign]

        result = await registry.execute(
            "moio_api.run",
            {"endpoint": "/api/v1/crm/contacts", "method": "GET"},
            execution_context={"initiator": {"id": 11, "accessToken": "jwt-abc"}},
        )

        self.assertTrue(result.get("ok"))
        request = result.get("request") or {}
        self.assertEqual((request or {}).get("requested_endpoint"), "/api/v1/crm/contacts")
        self.assertEqual((request or {}).get("endpoint"), "/api/v1/crm/contacts/")
        self.assertEqual(seen_urls[1], "https://example.test/api/v1/crm/contacts/")
