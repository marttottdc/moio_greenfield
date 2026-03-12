from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path


if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _AsyncOpenAI:  # pragma: no cover - import stub for tests
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    openai_stub.AsyncOpenAI = _AsyncOpenAI
    sys.modules["openai"] = openai_stub


from agent_console.runtime.config import AgentConfig, AppConfig, ModelConfig, PluginsConfig, ReplicaConfig, SkillsConfig, ToolsConfig
from agent_console.runtime.backend import AgentConsoleBackend


class StandaloneBackendProfilesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.seen_profile_requests: list[dict[str, object]] = []
        self.saved_profiles: list[dict[str, object]] = []

    def _make_backend(self) -> AgentConsoleBackend:
        def profile_state_resolver(initiator=None, selected_profile=None):
            self.seen_profile_requests.append(
                {
                    "initiator": dict(initiator) if isinstance(initiator, dict) else None,
                    "selectedProfile": str(selected_profile or ""),
                }
            )
            active_key = str(selected_profile or "ops").strip() or "ops"
            active_profile = {
                "id": 7,
                "key": active_key,
                "name": "Operations" if active_key == "ops" else active_key.title(),
                "systemPrompt": "Escalate risk clearly.",
                "defaultVendor": "xai",
                "defaultModel": "grok-4",
                "defaultThinking": "high",
                "defaultVerbosity": "detailed",
                "toolAllowlist": ["files.read", "files.list"],
                "pluginEntitlements": ["crm_contacts"],
                "isDefault": True,
                "isAssigned": True,
                "assignmentDefault": True,
                "isActive": True,
            }
            return {
                "profiles": [dict(active_profile)],
                "activeProfile": dict(active_profile),
                "diagnostics": {
                    "requestedProfile": str(selected_profile or ""),
                    "resolvedProfile": active_key,
                    "selectionSource": "explicit" if selected_profile else "assignment",
                    "requestedProfileRejected": False,
                    "hasExplicitAssignments": True,
                    "initiatorIsAdmin": bool((initiator or {}).get("tenantRole") == "admin"),
                },
            }

        def catalog_resolver():
            return {
                "profiles": [
                    {
                        "id": 7,
                        "key": "ops",
                        "name": "Operations",
                        "isDefault": True,
                        "isAssigned": True,
                        "assignmentDefault": True,
                        "isActive": True,
                    }
                ],
                "assignments": [
                    {
                        "id": 11,
                        "profileKey": "ops",
                        "userId": 42,
                        "userEmail": "boss@example.test",
                        "isDefault": True,
                        "isActive": True,
                    }
                ],
            }

        def upsert_handler(payload, initiator=None):
            saved = {
                "id": int(payload.get("id", 15) or 15),
                "key": str(payload.get("key") or "finance"),
                "name": str(payload.get("name") or "Finance"),
                "isDefault": bool(payload.get("isDefault", False)),
                "isAssigned": False,
                "assignmentDefault": False,
                "isActive": bool(payload.get("isActive", True)),
                "createdByEmail": str((initiator or {}).get("email") or ""),
            }
            self.saved_profiles.append(dict(saved))
            return saved

        cfg = ReplicaConfig(
            model=ModelConfig(api_key="test-key"),
            skills=SkillsConfig(),
            tools=ToolsConfig(
                allowlist=["files.read", "files.list", "files.write"],
                admin_only=["files.write"],
                workspace_root=self.root,
                vendors_file=self.root / "vendors" / "vendors.json",
                shell_enabled=False,
                docker_enabled=False,
                dynamic_tools_enabled=False,
                package_install_enabled=False,
                vault_enabled=False,
            ),
            plugins=PluginsConfig(),
            agent=AgentConfig(context_compaction_enabled=False),
            app=AppConfig(),
            sessions_dir=self.root / "sessions",
        )
        return AgentConsoleBackend(
            cfg,
            tenant_schema="tenant_a",
            workspace_slug="shared",
            agent_profile_state_resolver=profile_state_resolver,
            agent_profiles_catalog_resolver=catalog_resolver,
            agent_profile_upsert_handler=upsert_handler,
            workspace_profile_resolver=lambda: {
                "name": "Shared Workspace",
                "specialtyPrompt": "Focus on team-visible work.",
                "defaultVendor": "openai",
                "defaultModel": "gpt-4.1-mini",
                "defaultThinking": "low",
                "defaultVerbosity": "minimal",
            },
        )

    async def test_agent_runtime_applies_profile_defaults_and_tool_policy(self) -> None:
        backend = self._make_backend()

        runtime = await backend.agent_runtime(
            initiator={"id": 5, "tenantRole": "member"},
            selected_profile="ops",
            requested_tool_allowlist=["files.read", "files.write"],
        )

        effective = runtime.get("effective", {})
        diagnostics = runtime.get("diagnostics", {})

        self.assertEqual(self.seen_profile_requests[-1]["selectedProfile"], "ops")
        self.assertEqual(effective.get("provider"), "xai")
        self.assertEqual(effective.get("model"), "grok-4")
        self.assertEqual(effective.get("thinking"), "high")
        self.assertEqual(effective.get("verbosity"), "detailed")
        self.assertEqual(effective.get("toolAllowlist"), ["files.read"])
        self.assertEqual(diagnostics.get("resolvedProfile"), "ops")
        self.assertEqual(diagnostics.get("effectiveToolAllowlist"), ["files.read"])

    async def test_resources_exposes_agent_runtime_and_profiles(self) -> None:
        backend = self._make_backend()

        resources = await backend.resources(
            initiator={"id": 5, "tenantRole": "member"},
            selected_profile="ops",
        )

        agent_profiles = ((resources.get("agentProfiles") or {}).get("payload") or {})
        agent_runtime = ((resources.get("agentRuntime") or {}).get("payload") or {})
        models = ((resources.get("models") or {}).get("payload") or {})

        self.assertEqual((agent_profiles.get("activeProfile") or {}).get("key"), "ops")
        self.assertEqual(((agent_runtime.get("effective") or {}).get("provider")), "xai")
        self.assertEqual(models.get("provider"), "xai")

    async def test_agent_profiles_catalog_returns_admin_catalog(self) -> None:
        backend = self._make_backend()

        result = await backend.agent_profiles_catalog(
            initiator={"id": 42, "email": "boss@example.test", "tenantRole": "admin"},
        )

        payload = result.get("payload", {})
        self.assertTrue(result.get("ok"))
        self.assertEqual(payload.get("managementMode"), "admin")
        self.assertEqual(len(payload.get("assignments", [])), 1)
        self.assertEqual((payload.get("activeProfile") or {}).get("key"), "ops")

    async def test_agent_profile_upsert_requires_admin(self) -> None:
        backend = self._make_backend()

        with self.assertRaises(PermissionError):
            await backend.agent_profile_upsert(
                {"key": "finance", "name": "Finance"},
                initiator={"id": 5, "tenantRole": "member"},
            )

    async def test_agent_profile_upsert_returns_saved_profile_and_catalog(self) -> None:
        backend = self._make_backend()

        result = await backend.agent_profile_upsert(
            {"key": "finance", "name": "Finance"},
            initiator={"id": 42, "email": "boss@example.test", "tenantRole": "admin"},
        )

        payload = result.get("payload", {})
        self.assertTrue(result.get("ok"))
        self.assertEqual((payload.get("profile") or {}).get("key"), "finance")
        self.assertEqual((payload.get("catalog") or {}).get("managementMode"), "admin")
        self.assertEqual(len(self.saved_profiles), 1)

    async def test_run_once_preserves_agent_runtime_metadata_in_final_message(self) -> None:
        backend = self._make_backend()

        class _FakeResponse:
            raw_message = {"role": "assistant", "content": [{"type": "output_text", "text": "All set."}]}
            tool_calls: list[dict[str, object]] = []
            text = "All set."
            usage = {"input": 12, "output": 4, "total": 16}
            stop_reason = "stop"

        class _FakeClient:
            async def complete_stream(self, **kwargs):  # pragma: no cover - exercised via backend flow
                _ = kwargs
                return _FakeResponse()

        backend._client_for_config = lambda cfg: _FakeClient()  # type: ignore[method-assign]

        result = await backend.run_once(
            session_key="main",
            message="hello",
            initiator={"id": 5, "tenantRole": "member"},
            selected_profile="ops",
        )

        self.assertEqual(result.get("state"), "final")
        final_message = result.get("message") or {}
        self.assertEqual(((final_message.get("agentRuntime") or {}).get("profileKey")), "ops")
        self.assertEqual(((final_message.get("agentRuntime") or {}).get("toolAllowlist")), ["files.list", "files.read"])
        self.assertEqual(((final_message.get("agentRuntime") or {}).get("diagnostics") or {}).get("resolvedProfile"), "ops")

    async def test_effective_tool_allowlist_supports_exclude_patterns(self) -> None:
        cfg = ReplicaConfig(
            model=ModelConfig(api_key="test-key"),
            skills=SkillsConfig(),
            tools=ToolsConfig(
                allowlist=["files.read", "moio_api.run", "api.run"],
                workspace_root=self.root,
                vendors_file=self.root / "vendors" / "vendors.json",
                shell_enabled=False,
                docker_enabled=False,
                dynamic_tools_enabled=False,
                package_install_enabled=False,
                vault_enabled=False,
            ),
            plugins=PluginsConfig(),
            agent=AgentConfig(context_compaction_enabled=False),
            app=AppConfig(),
            sessions_dir=self.root / "sessions-exclude",
        )
        backend = AgentConsoleBackend(cfg, tenant_schema="tenant_a", workspace_slug="shared")

        effective = await backend.effective_tool_allowlist(
            initiator={"id": 5, "tenantRole": "member"},
            profile_allowlist=["-moio_api.run"],
        )

        self.assertIn("files.read", effective)
        self.assertIn("api.run", effective)
        self.assertNotIn("moio_api.run", effective)
