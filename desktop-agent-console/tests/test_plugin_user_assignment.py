from __future__ import annotations

import json
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


def _catalog_tool_ids(payload: dict[str, object]) -> set[str]:
    groups = payload.get("groups") if isinstance(payload, dict) else None
    if not isinstance(groups, list):
        return set()
    output: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            continue
        tools = group.get("tools")
        if not isinstance(tools, list):
            continue
        for item in tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("id", "")).strip()
            if name:
                output.add(name)
    return output


class PluginUserAssignmentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        plugin_dir = self.root / "plugins" / "crm-contacts"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "plugin.py").write_text("def register(api):\n    return None\n", encoding="utf-8")
        (plugin_dir / "replica.plugin.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "crm.contacts",
                    "name": "CRM Contacts",
                    "version": "1.0.0",
                    "entrypoint": "plugin.py",
                    "tools": ["files.read"],
                }
            ),
            encoding="utf-8",
        )
        self.plugins_dir = self.root / "plugins"

    def _make_backend(self) -> AgentConsoleBackend:
        cfg = ReplicaConfig(
            model=ModelConfig(api_key="test-key"),
            skills=SkillsConfig(),
            tools=ToolsConfig(
                allowlist=["files.read"],
                workspace_root=self.root,
                vendors_file=self.root / "vendors" / "vendors.json",
                shell_enabled=False,
                docker_enabled=False,
                dynamic_tools_enabled=False,
                package_install_enabled=False,
                vault_enabled=False,
            ),
            plugins=PluginsConfig(
                manifests_dir=self.plugins_dir,
                platform_approved=["crm.contacts"],
                tenant_enabled=["crm.contacts"],
                user_allowed=["crm.contacts"],
            ),
            agent=AgentConfig(context_compaction_enabled=False),
            app=AppConfig(),
            sessions_dir=self.root / "sessions",
        )
        return AgentConsoleBackend(
            cfg,
            plugin_user_allowlist_resolver=lambda initiator: (
                ["crm.contacts"] if str((initiator or {}).get("tenantRole", "")).strip().lower() == "admin" else []
            ),
        )

    async def test_plugin_alias_is_filtered_from_member_allowlist(self) -> None:
        backend = self._make_backend()

        member_allowlist = backend.effective_tool_allowlist(initiator={"id": 1, "tenantRole": "member"})
        admin_allowlist = backend.effective_tool_allowlist(initiator={"id": 2, "tenantRole": "admin"})

        self.assertNotIn("plugin.crm.contacts.files.read", member_allowlist)
        self.assertIn("plugin.crm.contacts.files.read", admin_allowlist)

    async def test_resources_exposes_user_assignment_stage_when_blocked(self) -> None:
        backend = self._make_backend()

        member_resources = await backend.resources(initiator={"id": 1, "tenantRole": "member"})
        admin_resources = await backend.resources(initiator={"id": 2, "tenantRole": "admin"})

        member_plugins = (((member_resources.get("pluginsStatus") or {}).get("payload")) or {})
        admin_plugins = (((admin_resources.get("pluginsStatus") or {}).get("payload")) or {})
        member_reports = list(member_plugins.get("reports", []))
        member_tools_catalog = (((member_resources.get("toolsCatalog") or {}).get("payload")) or {})
        admin_tools_catalog = (((admin_resources.get("toolsCatalog") or {}).get("payload")) or {})

        self.assertEqual(int(member_plugins.get("activeCount", 0) or 0), 0)
        self.assertEqual(int(admin_plugins.get("activeCount", 0) or 0), 1)
        self.assertTrue(
            any(
                str(row.get("pluginId", "")).strip().lower() == "crm.contacts"
                and str(row.get("stage", "")).strip().lower() == "user_assignment"
                for row in member_reports
                if isinstance(row, dict)
            )
        )
        self.assertNotIn("plugin.crm.contacts.files.read", _catalog_tool_ids(member_tools_catalog))
        self.assertIn("plugin.crm.contacts.files.read", _catalog_tool_ids(admin_tools_catalog))

    async def test_profile_tool_allowlist_does_not_hide_plugin_tools(self) -> None:
        backend = self._make_backend()

        allowlist = backend.effective_tool_allowlist(
            initiator={"id": 2, "tenantRole": "admin"},
            profile_allowlist=["files.read"],
        )

        self.assertIn("plugin.crm.contacts.files.read", allowlist)


if __name__ == "__main__":
    unittest.main()
