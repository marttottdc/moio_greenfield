from __future__ import annotations

import asyncio
import json
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from moio_runtime.plugins import (
    PluginEnablement,
    extract_plugin_zip_to_dir,
    PluginManifest,
    PluginRuntimeContext,
    evaluate_plugin_readiness,
    load_plugin_bundle,
    load_plugin_manifest,
    resolve_active_plugins,
)
from moio_runtime.tools import ToolRegistry


EXAMPLE_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "examples" / "plugins" / "crm-contacts"


class PluginManifestTests(unittest.TestCase):
    def test_manifest_parses_requirements(self) -> None:
        manifest = PluginManifest.from_dict(
            {
                "schema_version": 1,
                "id": "crm.contacts",
                "name": "CRM Contacts",
                "version": "1.0.0",
                "description": "Search and update CRM contacts",
                "entrypoint": "plugin.py",
                "icon": "icon.svg",
                "readme": "README.md",
                "capabilities": ["resources", "tools"],
                "permissions": ["network_outbound"],
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "base_url": {"type": "string"},
                    },
                },
                "requirements": {
                    "tenant_config": ["base_url"],
                    "user_config": ["locale"],
                    "tenant_credentials": ["crm_api_key"],
                    "user_credentials": ["crm_login"],
                    "assets": ["openapi.json"],
                },
            }
        )

        self.assertEqual(manifest.plugin_id, "crm.contacts")
        self.assertEqual(manifest.schema_version, 1)
        self.assertEqual(manifest.tool_names, [])
        self.assertEqual(manifest.icon_path, "icon.svg")
        self.assertEqual(manifest.readme_path, "README.md")
        self.assertEqual(manifest.permissions, ["network_outbound"])
        self.assertEqual(manifest.tenant_config_keys, ["base_url"])
        self.assertEqual(manifest.user_credentials, ["crm_login"])
        self.assertEqual(manifest.required_assets, ["openapi.json"])

    def test_manifest_rejects_tenant_config_without_schema_properties(self) -> None:
        with self.assertRaises(ValueError):
            PluginManifest.from_dict(
                {
                    "schema_version": 1,
                    "id": "crm.contacts",
                    "name": "CRM Contacts",
                    "version": "1.0.0",
                    "entrypoint": "plugin.py",
                    "requirements": {
                        "tenant_config": ["base_url"],
                    },
                }
            )

    def test_repo_example_manifest_loads_from_bundle_directory(self) -> None:
        manifest = load_plugin_manifest(EXAMPLE_PLUGIN_DIR)

        self.assertEqual(manifest.plugin_id, "crm.contacts")
        self.assertEqual(manifest.schema_version, 1)
        self.assertEqual(manifest.entrypoint, "plugin.py")
        self.assertEqual(manifest.capabilities, ["resources", "tools"])
        self.assertEqual(manifest.permissions, ["filesystem_read", "network_outbound"])
        self.assertEqual(manifest.required_assets, ["openapi.json"])

    def test_repo_example_bundle_loads_entrypoint_metadata(self) -> None:
        bundle = load_plugin_bundle(EXAMPLE_PLUGIN_DIR)

        self.assertEqual(bundle.manifest.plugin_id, "crm.contacts")
        self.assertEqual(bundle.entrypoint_path.name, "plugin.py")
        self.assertEqual(bundle.bundle_dir, EXAMPLE_PLUGIN_DIR.resolve())


class PluginReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = PluginManifest.from_dict(
            {
                "schema_version": 1,
                "id": "crm.contacts",
                "name": "CRM Contacts",
                "version": "1.0.0",
                "entrypoint": "plugin.py",
                "permissions": ["network_outbound"],
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "base_url": {"type": "string"},
                    },
                },
                "requirements": {
                    "tenant_config": ["base_url"],
                    "user_config": ["locale"],
                    "tenant_credentials": ["crm_api_key"],
                    "user_credentials": ["crm_login"],
                    "assets": ["openapi.json"],
                },
            }
        )

    def test_readiness_blocks_missing_requirements(self) -> None:
        report = evaluate_plugin_readiness(
            self.manifest,
            PluginEnablement(
                installed=True,
                platform_approved=True,
                tenant_enabled=True,
                user_allowed=True,
            ),
            PluginRuntimeContext(
                tenant_config_keys={"base_url"},
                approved_permissions={"network_outbound"},
            ),
        )

        self.assertFalse(report.active)
        self.assertEqual(report.stage, "requirements")
        self.assertEqual(report.missing["user_config"], ["locale"])
        self.assertEqual(report.missing["tenant_credentials"], ["crm_api_key"])

    def test_readiness_requires_permission_approval(self) -> None:
        report = evaluate_plugin_readiness(
            self.manifest,
            PluginEnablement(
                installed=True,
                platform_approved=True,
                tenant_enabled=True,
                user_allowed=True,
            ),
            PluginRuntimeContext(
                tenant_config_keys={"base_url"},
                user_config_keys={"locale"},
                tenant_credentials={"crm_api_key"},
                user_credentials={"crm_login"},
                available_assets={"openapi.json"},
                approved_permissions=set(),
            ),
        )

        self.assertFalse(report.active)
        self.assertEqual(report.stage, "permissions")
        self.assertEqual(report.missing["permissions"], ["network_outbound"])

    def test_readiness_is_active_when_everything_is_satisfied(self) -> None:
        report = evaluate_plugin_readiness(
            self.manifest,
            PluginEnablement(
                installed=True,
                platform_approved=True,
                tenant_enabled=True,
                user_allowed=True,
            ),
            PluginRuntimeContext(
                tenant_config_keys={"base_url"},
                user_config_keys={"locale"},
                tenant_credentials={"crm_api_key"},
                user_credentials={"crm_login"},
                available_assets={"openapi.json"},
                approved_permissions={"network_outbound"},
            ),
        )

        self.assertTrue(report.active)
        self.assertEqual(report.stage, "active")

    def test_readiness_accepts_plugin_scoped_runtime_keys(self) -> None:
        report = evaluate_plugin_readiness(
            self.manifest,
            PluginEnablement(
                installed=True,
                platform_approved=True,
                tenant_enabled=True,
                user_allowed=True,
            ),
            PluginRuntimeContext(
                tenant_config_keys={"crm.contacts:base_url"},
                user_config_keys={"crm.contacts:locale"},
                tenant_credentials={"crm.contacts:crm_api_key"},
                user_credentials={"crm.contacts:crm_login"},
                available_assets={"openapi.json"},
                approved_permissions={"network_outbound"},
            ),
        )

        self.assertTrue(report.active)
        self.assertEqual(report.stage, "active")


class PluginRuntimeIntegrationTests(unittest.TestCase):
    def test_extract_plugin_zip_to_dir_loads_bundle(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "crm-bundle/replica.plugin.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "crm.contacts",
                        "name": "CRM Contacts",
                        "version": "1.0.0",
                        "entrypoint": "plugin.py",
                    }
                ),
            )
            archive.writestr("crm-bundle/plugin.py", "def register(api):\n    return None\n")

        with tempfile.TemporaryDirectory() as tmp:
            bundle = extract_plugin_zip_to_dir(buffer.getvalue(), Path(tmp) / "bundle")

        self.assertEqual(bundle.manifest.plugin_id, "crm.contacts")
        self.assertEqual(bundle.entrypoint_path.name, "plugin.py")

    def test_resolve_active_plugins_loads_ready_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "crm-contacts"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            (plugin_dir / "plugin.py").write_text("def register(api):\n    return None\n", encoding="utf-8")
            (plugin_dir / "openapi.json").write_text("{}", encoding="utf-8")
            (plugin_dir / "replica.plugin.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "crm.contacts",
                        "name": "CRM Contacts",
                        "version": "1.0.0",
                        "entrypoint": "plugin.py",
                        "tools": ["files.read"],
                        "permissions": ["filesystem_read"],
                        "config_schema": {
                            "type": "object",
                            "properties": {
                                "base_url": {"type": "string"},
                            },
                        },
                        "requirements": {
                            "tenant_config": ["base_url"],
                            "assets": ["openapi.json"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            active_plugins, reports = resolve_active_plugins(
                SimpleNamespace(
                    manifests_dir=plugin_dir,
                    platform_approved=["crm.contacts"],
                    tenant_enabled=["crm.contacts"],
                    user_allowed=["crm.contacts"],
                    approved_permissions=["filesystem_read"],
                    tenant_config_keys=["base_url"],
                    user_config_keys=[],
                    tenant_credentials=[],
                    user_credentials=[],
                )
            )

            self.assertEqual(len(active_plugins), 1)
            self.assertEqual(active_plugins[0].manifest.tool_names, ["files.read"])
            self.assertTrue(any(report.active for report in reports))

    def test_resolve_active_plugins_scans_additional_manifest_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            primary = root / "primary"
            extra = root / "extra" / "crm-contacts"
            primary.mkdir(parents=True, exist_ok=True)
            extra.mkdir(parents=True, exist_ok=True)
            (extra / "plugin.py").write_text("def register(api):\n    return None\n", encoding="utf-8")
            (extra / "replica.plugin.json").write_text(
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

            active_plugins, reports = resolve_active_plugins(
                SimpleNamespace(
                    manifests_dir=primary,
                    additional_manifests_dirs=[root / "extra"],
                    platform_approved=["crm.contacts"],
                    tenant_enabled=["crm.contacts"],
                    user_allowed=["crm.contacts"],
                    approved_permissions=[],
                    tenant_config_keys=[],
                    user_config_keys=[],
                    tenant_credentials=[],
                    user_credentials=[],
                )
            )

            self.assertEqual(len(active_plugins), 1)
            self.assertTrue(any(report.active for report in reports))

    def test_resolve_active_plugins_blocks_missing_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "crm-contacts"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            (plugin_dir / "openapi.json").write_text("{}", encoding="utf-8")
            (plugin_dir / "replica.plugin.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "crm.contacts",
                        "name": "CRM Contacts",
                        "version": "1.0.0",
                        "entrypoint": "plugin.py",
                        "tools": ["files.read"],
                        "permissions": ["filesystem_read"],
                        "config_schema": {
                            "type": "object",
                            "properties": {
                                "base_url": {"type": "string"},
                            },
                        },
                        "requirements": {
                            "tenant_config": ["base_url"],
                            "assets": ["openapi.json"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            active_plugins, reports = resolve_active_plugins(
                SimpleNamespace(
                    manifests_dir=plugin_dir,
                    platform_approved=["crm.contacts"],
                    tenant_enabled=["crm.contacts"],
                    user_allowed=["crm.contacts"],
                    approved_permissions=["filesystem_read"],
                    tenant_config_keys=["base_url"],
                    user_config_keys=[],
                    tenant_credentials=[],
                    user_credentials=[],
                )
            )

            self.assertEqual(active_plugins, [])
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].stage, "bundle")
            self.assertEqual(reports[0].missing["entrypoint"], ["plugin.py"])

    def test_resolve_active_plugins_supports_scoped_requirement_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "crm-contacts"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            (plugin_dir / "plugin.py").write_text("def register(api):\n    return None\n", encoding="utf-8")
            (plugin_dir / "openapi.json").write_text("{}", encoding="utf-8")
            (plugin_dir / "replica.plugin.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "crm.contacts",
                        "name": "CRM Contacts",
                        "version": "1.0.0",
                        "entrypoint": "plugin.py",
                        "tools": ["files.read"],
                        "permissions": ["filesystem_read"],
                        "config_schema": {
                            "type": "object",
                            "properties": {
                                "base_url": {"type": "string"},
                            },
                        },
                        "requirements": {
                            "tenant_config": ["base_url"],
                            "assets": ["openapi.json"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            active_plugins, reports = resolve_active_plugins(
                SimpleNamespace(
                    manifests_dir=plugin_dir,
                    platform_approved=["crm.contacts"],
                    tenant_enabled=["crm.contacts"],
                    user_allowed=["crm.contacts"],
                    approved_permissions=["filesystem_read"],
                    tenant_config_keys=["crm.contacts:base_url"],
                    user_config_keys=[],
                    tenant_credentials=[],
                    user_credentials=[],
                )
            )

            self.assertEqual(len(active_plugins), 1)
            self.assertTrue(any(report.active for report in reports))

    def test_tool_registry_exposes_only_active_plugin_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "crm-contacts"
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

            active_plugins, _reports = resolve_active_plugins(
                SimpleNamespace(
                    manifests_dir=plugin_dir,
                    platform_approved=["crm.contacts"],
                    tenant_enabled=["crm.contacts"],
                    user_allowed=["crm.contacts"],
                    approved_permissions=[],
                    tenant_config_keys=[],
                    user_config_keys=[],
                    tenant_credentials=[],
                    user_credentials=[],
                )
            )

            registry = ToolRegistry(
                workspace_root=root,
                shell_enabled=False,
                shell_timeout_seconds=30.0,
                docker_enabled=False,
                docker_timeout_seconds=60.0,
                dynamic_tools_enabled=False,
                dynamic_tools_dir=root / "dynamic-tools",
                package_install_enabled=False,
                package_install_timeout_seconds=60.0,
                vault_enabled=False,
                vault_file=root / "vault.json",
                vault_passphrase=None,
                active_plugins=active_plugins,
            )

            listed = [spec.name for spec in registry.list_specs([])]
            self.assertIn("plugin.crm.contacts.files.read", listed)
            self.assertEqual(
                registry.plugin_id_for_tool("plugin.crm.contacts.files.read"),
                "crm.contacts",
            )

    def test_resolve_active_plugins_registers_entrypoint_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "telegram-plugin"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            (plugin_dir / "plugin.py").write_text(
                "\n".join(
                    [
                        "def register(api):",
                        "    @api.tool(",
                        "        name='telegram.notify',",
                        "        description='Send a telegram notification.',",
                        "        parameters={",
                        "            'type': 'object',",
                        "            'properties': {'text': {'type': 'string'}},",
                        "            'required': ['text']",
                        "        },",
                        "    )",
                        "    def notify(params):",
                        "        prefix = str(api.config.get('prefix', ''))",
                        "        return {'sent': prefix + str(params.get('text', ''))}",
                        "    return None",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (plugin_dir / "replica.plugin.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "telegram.notifications",
                        "name": "Telegram Notifications",
                        "version": "1.0.0",
                        "entrypoint": "plugin.py",
                        "tools": ["telegram.notify"],
                        "capabilities": ["tools"],
                    }
                ),
                encoding="utf-8",
            )

            active_plugins, reports = resolve_active_plugins(
                SimpleNamespace(
                    manifests_dir=plugin_dir,
                    platform_approved=["telegram.notifications"],
                    tenant_enabled=["telegram.notifications"],
                    user_allowed=["telegram.notifications"],
                    approved_permissions=[],
                    tenant_config_keys=[],
                    user_config_keys=[],
                    tenant_credentials=[],
                    user_credentials=[],
                    plugin_configs={"telegram.notifications": {"prefix": "tg:"}},
                )
            )

            self.assertEqual(len(active_plugins), 1)
            self.assertTrue(any(report.active for report in reports))
            self.assertEqual(
                [tool.name for tool in active_plugins[0].registered_tools],
                ["telegram.notify"],
            )

            registry = ToolRegistry(
                workspace_root=root,
                shell_enabled=False,
                shell_timeout_seconds=30.0,
                docker_enabled=False,
                docker_timeout_seconds=60.0,
                dynamic_tools_enabled=False,
                dynamic_tools_dir=root / "dynamic-tools",
                package_install_enabled=False,
                package_install_timeout_seconds=60.0,
                vault_enabled=False,
                vault_file=root / "vault.json",
                vault_passphrase=None,
                active_plugins=active_plugins,
            )
            listed = [spec.name for spec in registry.list_specs([])]
            self.assertIn("telegram.notify", listed)
            self.assertEqual(registry.plugin_id_for_tool("telegram.notify"), "telegram.notifications")
            result = asyncio.run(registry.execute("telegram.notify", {"text": "hola"}))
            self.assertEqual(result.get("sent"), "tg:hola")

    def test_resolve_active_plugins_blocks_unimportable_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "crm-contacts"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            (plugin_dir / "plugin.py").write_text("def broken(:\n    return None\n", encoding="utf-8")
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

            active_plugins, reports = resolve_active_plugins(
                SimpleNamespace(
                    manifests_dir=plugin_dir,
                    platform_approved=["crm.contacts"],
                    tenant_enabled=["crm.contacts"],
                    user_allowed=["crm.contacts"],
                    approved_permissions=[],
                    tenant_config_keys=[],
                    user_config_keys=[],
                    tenant_credentials=[],
                    user_credentials=[],
                )
            )

            self.assertEqual(active_plugins, [])
            self.assertTrue(any(report.stage == "initialization" for report in reports))


if __name__ == "__main__":
    unittest.main()
