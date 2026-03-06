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


from moio_runtime.config import AgentConfig, AppConfig, ModelConfig, PluginsConfig, ReplicaConfig, SkillsConfig, ToolsConfig
from moio_runtime.standalone_backend import StandaloneAgentBackend


def _tool_ids(catalog: dict[str, object]) -> set[str]:
    groups = catalog.get("groups") if isinstance(catalog, dict) else None
    if not isinstance(groups, list):
        return set()
    names: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        tools = group.get("tools")
        if not isinstance(tools, list):
            continue
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            tool_id = str(tool.get("id", "")).strip()
            if tool_id:
                names.add(tool_id)
    return names


class StandaloneBackendAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _make_backend(self) -> StandaloneAgentBackend:
        cfg = ReplicaConfig(
            model=ModelConfig(api_key="test-key"),
            skills=SkillsConfig(),
            tools=ToolsConfig(
                allowlist=["files.read", "files.write"],
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
        return StandaloneAgentBackend(cfg, tenant_schema="tenant_a", workspace_slug="shared")

    async def test_resources_filters_admin_only_tools_for_members(self) -> None:
        backend = self._make_backend()

        member_resources = await backend.resources(initiator={"id": 11, "tenantRole": "member"})
        admin_resources = await backend.resources(initiator={"id": 12, "tenantRole": "admin"})

        member_tools = _tool_ids(
            ((((member_resources.get("toolsCatalog") or {}) if isinstance(member_resources, dict) else {}).get("payload")) or {})
        )
        admin_tools = _tool_ids(
            ((((admin_resources.get("toolsCatalog") or {}) if isinstance(admin_resources, dict) else {}).get("payload")) or {})
        )

        self.assertIn("files.read", member_tools)
        self.assertNotIn("files.write", member_tools)
        self.assertIn("files.write", admin_tools)

    def test_effective_runtime_tool_allowlist_enforces_admin_only(self) -> None:
        backend = self._make_backend()

        member_allowlist = backend._effective_runtime_tool_allowlist(["files.write"], initiator={"tenantRole": "member"})
        admin_allowlist = backend._effective_runtime_tool_allowlist(["files.write"], initiator={"tenantRole": "admin"})

        self.assertEqual(member_allowlist, [])
        self.assertEqual(admin_allowlist, ["files.write"])

    async def test_handle_tool_call_blocks_admin_only_execution_for_members(self) -> None:
        backend = self._make_backend()
        model_messages: list[dict[str, object]] = []

        async def _noop(*args, **kwargs):
            return None

        async def _identity(*, tool_name, result, session_key, run_id):
            return result

        async def _unexpected_execute(name: str, arguments: dict[str, object]) -> dict[str, object]:
            raise AssertionError(f"tool execution should not run: {name}")

        backend._emit_agent_tool_event = _noop  # type: ignore[method-assign]
        backend._record_memory_artifact = _noop  # type: ignore[method-assign]
        backend._enrich_tool_result_with_media = _identity  # type: ignore[method-assign]
        backend.tools.execute = _unexpected_execute  # type: ignore[method-assign]

        await backend._handle_tool_call(
            run_id="run-1",
            session_key="main",
            model_messages=model_messages,
            tool_call={
                "id": "call-1",
                "function": {
                    "name": "files.write",
                    "arguments": "{\"path\":\"note.txt\",\"content\":\"hello\"}",
                },
            },
            runtime_allowlist=backend._effective_runtime_tool_allowlist(None, initiator={"tenantRole": "member"}),
        )

        self.assertEqual(len(model_messages), 1)
        self.assertEqual(model_messages[0].get("role"), "tool")
        self.assertIn("requires a tenant admin initiator", str(model_messages[0].get("content", "")))
