from __future__ import annotations

import base64
import mimetypes
import tempfile
from pathlib import Path
from typing import Any

from agent_console.models import AgentConsoleInstalledPlugin
from agent_console.runtime.plugins import extract_plugin_zip_to_dir


def _icon_data_url(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    raw = path.read_bytes()
    if not raw:
        return ""
    mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return f"data:{mime_type};base64,{base64.b64encode(raw).decode('ascii')}"


def _readme_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def _plugin_row_from_record(row: AgentConsoleInstalledPlugin) -> tuple[dict[str, Any], str]:
    plugin_id = str(row.plugin_id or "").strip().lower()
    manifest = row.manifest if isinstance(row.manifest, dict) else {}
    manifest_payload = dict(manifest) if manifest else {}
    name = str(row.name or manifest_payload.get("name") or plugin_id).strip() or plugin_id
    version = str(row.version or manifest_payload.get("version") or "").strip()
    capabilities = manifest_payload.get("capabilities")
    permissions = manifest_payload.get("permissions")
    capabilities_list = [str(item).strip() for item in capabilities if str(item).strip()] if isinstance(capabilities, list) else []
    permissions_list = [str(item).strip() for item in permissions if str(item).strip()] if isinstance(permissions, list) else []
    icon_data_url = ""
    help_markdown = ""
    validation_error = ""

    bundle_payload = row.bundle_zip
    if isinstance(bundle_payload, memoryview):
        bundle_bytes = bundle_payload.tobytes()
    else:
        bundle_bytes = bytes(bundle_payload or b"")

    if not bundle_bytes:
        validation_error = "Missing plugin bundle bytes in database."
    else:
        try:
            with tempfile.TemporaryDirectory(prefix="platform-plugin-inspect-") as tmp_dir:
                bundle = extract_plugin_zip_to_dir(bundle_bytes, Path(tmp_dir))
                icon_path = str(bundle.manifest.icon_path or "").strip()
                readme_path = str(bundle.manifest.readme_path or "").strip()
                if icon_path:
                    icon_data_url = _icon_data_url(bundle.bundle_dir / icon_path)
                if readme_path:
                    help_markdown = _readme_text(bundle.bundle_dir / readme_path)
        except Exception as exc:
            validation_error = str(exc)

    if not validation_error and not plugin_id:
        validation_error = "Invalid plugin id."

    payload = {
        "pluginId": plugin_id,
        "name": name,
        "version": version,
        "sourceType": "database",
        "bundlePath": f"db://agent_console_installed_plugin/{plugin_id}",
        "manifestPath": f"db://agent_console_installed_plugin/{plugin_id}/replica.plugin.json",
        "bundleFilename": f"{plugin_id}.zip",
        "bundleSha256": str(row.checksum_sha256 or "").strip(),
        "hasBundleBlob": bool(bundle_bytes),
        "iconDataUrl": icon_data_url,
        "iconFallback": name[:2].upper() if name else plugin_id[:2].upper(),
        "helpMarkdown": help_markdown,
        "manifest": manifest_payload,
        "capabilities": capabilities_list,
        "permissions": permissions_list,
        "isValidated": not validation_error,
        "isPlatformApproved": bool(row.is_platform_approved),
        "validationError": validation_error,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else "",
    }
    return payload, validation_error


def platform_plugin_admin_state() -> dict[str, Any]:
    rows = list(AgentConsoleInstalledPlugin.objects.order_by("plugin_id"))
    plugins: list[dict[str, Any]] = []
    invalid: list[dict[str, str]] = []
    for row in rows:
        payload, validation_error = _plugin_row_from_record(row)
        plugins.append(payload)
        if validation_error:
            invalid.append(
                {
                    "manifestPath": str(payload.get("manifestPath") or ""),
                    "error": validation_error,
                }
            )
    return {
        "sync": {
            "syncedCount": len(plugins),
            "invalid": invalid,
        },
        "plugins": plugins,
        "tenantPlugins": [],
        "tenantPluginAssignments": [],
    }
