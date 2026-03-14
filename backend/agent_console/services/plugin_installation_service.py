from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agent_console.runtime.plugins import extract_plugin_zip_to_dir, validate_plugin_bundle_loadable


@dataclass(slots=True)
class ParsedPluginBundle:
    plugin_id: str
    name: str
    version: str
    manifest: dict
    checksum_sha256: str
    bundle_zip: bytes


def parse_plugin_bundle_zip(bundle_zip: bytes) -> ParsedPluginBundle:
    payload = bytes(bundle_zip or b"")
    checksum = hashlib.sha256(payload).hexdigest()
    with tempfile.TemporaryDirectory(prefix="agent-console-plugin-validate-") as tmp_dir:
        bundle = extract_plugin_zip_to_dir(payload, Path(tmp_dir))
        validate_plugin_bundle_loadable(bundle)
        manifest = bundle.manifest
        return ParsedPluginBundle(
            plugin_id=manifest.plugin_id,
            name=manifest.name,
            version=manifest.version,
            manifest=manifest.to_dict(),
            checksum_sha256=checksum,
            bundle_zip=payload,
        )


def upsert_installed_plugin_from_zip(bundle_zip: bytes):
    from agent_console.models import AgentConsoleInstalledPlugin

    parsed = parse_plugin_bundle_zip(bundle_zip)
    existing = AgentConsoleInstalledPlugin.objects.filter(plugin_id=parsed.plugin_id).first()
    plugin, _ = AgentConsoleInstalledPlugin.objects.update_or_create(
        plugin_id=parsed.plugin_id,
        defaults={
            "name": parsed.name,
            "version": parsed.version,
            "manifest": parsed.manifest,
            "checksum_sha256": parsed.checksum_sha256,
            "bundle_zip": parsed.bundle_zip,
            "enabled": True,
            "is_platform_approved": existing.is_platform_approved if existing is not None else False,
        },
    )
    return plugin
