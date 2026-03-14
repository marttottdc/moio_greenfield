from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
PLUGIN_MANIFEST_FILENAME = "replica.plugin.json"
PLUGIN_SCHEMA_VERSION = 1
PLUGIN_CAPABILITIES = {
    "hooks",
    "providers",
    "resources",
    "services",
    "skills",
    "tools",
}
PLUGIN_PERMISSIONS = {
    "background_tasks",
    "db_models",
    "docker_exec",
    "filesystem_read",
    "filesystem_write",
    "network_outbound",
    "shell_exec",
}
PLUGIN_ICON_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
MAX_PLUGIN_ZIP_BYTES = 20 * 1024 * 1024
MAX_PLUGIN_UNZIPPED_BYTES = 100 * 1024 * 1024


def _normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _normalize_relative_path(value: Any, *, field_name: str, required: bool = True) -> str:
    raw = str(value or "").strip()
    if not raw:
        if required:
            raise ValueError(f"{field_name} is required")
        return ""
    normalized = Path(raw)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError(f"{field_name} must stay within the plugin bundle")
    return normalized.as_posix()


def _normalize_relative_path_list(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        raw = str(item or "").strip()
        if not raw:
            continue
        normalized = _normalize_relative_path(raw, field_name=field_name)
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _normalize_enum_list(value: Any, *, field_name: str, allowed: set[str]) -> list[str]:
    output = _normalize_str_list(value)
    invalid = sorted(item for item in output if item not in allowed)
    if invalid:
        allowed_list = ", ".join(sorted(allowed))
        raise ValueError(f"{field_name} contains unsupported values: {', '.join(invalid)} (allowed: {allowed_list})")
    return output


def _normalize_schema_version(value: Any) -> int:
    if value is None or str(value).strip() == "":
        return PLUGIN_SCHEMA_VERSION
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("plugin schema_version must be an integer") from exc
    if normalized != PLUGIN_SCHEMA_VERSION:
        raise ValueError(f"unsupported plugin schema_version: {normalized}")
    return normalized


def _normalize_id(value: Any) -> str:
    plugin_id = str(value or "").strip().lower()
    if not plugin_id:
        raise ValueError("plugin id is required")
    if not PLUGIN_ID_RE.fullmatch(plugin_id):
        raise ValueError("plugin id must match ^[a-z0-9][a-z0-9._-]{0,79}$")
    return plugin_id


@dataclass(slots=True)
class PluginManifest:
    schema_version: int
    plugin_id: str
    name: str
    version: str
    description: str
    entrypoint: str
    icon_path: str = ""
    readme_path: str = ""
    tool_names: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    tenant_config_keys: list[str] = field(default_factory=list)
    user_config_keys: list[str] = field(default_factory=list)
    tenant_credentials: list[str] = field(default_factory=list)
    user_credentials: list[str] = field(default_factory=list)
    required_assets: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Any) -> "PluginManifest":
        if not isinstance(raw, dict):
            raise ValueError("plugin manifest must be an object")

        requirements = raw.get("requirements")
        requirements = requirements if isinstance(requirements, dict) else {}
        config_schema = raw.get("config_schema")
        config_schema = dict(config_schema) if isinstance(config_schema, dict) else {}
        config_properties = config_schema.get("properties")
        config_properties = config_properties if isinstance(config_properties, dict) else {}

        name = str(raw.get("name", "") or "").strip()
        version = str(raw.get("version", "") or "").strip()
        entrypoint = str(raw.get("entrypoint", "") or "").strip()

        if not name:
            raise ValueError("plugin name is required")
        if not version:
            raise ValueError("plugin version is required")
        if not entrypoint:
            raise ValueError("plugin entrypoint is required")
        entrypoint = _normalize_relative_path(entrypoint, field_name="plugin entrypoint")
        if not entrypoint.endswith(".py"):
            raise ValueError("plugin entrypoint must point to a Python module")
        icon_path = _normalize_relative_path(raw.get("icon"), field_name="plugin icon", required=False)
        if icon_path and Path(icon_path).suffix.lower() not in PLUGIN_ICON_EXTENSIONS:
            raise ValueError("plugin icon must be one of: .png, .jpg, .jpeg, .webp, .svg")
        readme_path = _normalize_relative_path(raw.get("readme"), field_name="plugin readme", required=False)
        if readme_path and Path(readme_path).suffix.lower() != ".md":
            raise ValueError("plugin readme must be a markdown file (.md)")

        tenant_config_keys = _normalize_str_list(requirements.get("tenant_config"))
        user_config_keys = _normalize_str_list(requirements.get("user_config"))
        tenant_credentials = _normalize_str_list(requirements.get("tenant_credentials"))
        user_credentials = _normalize_str_list(requirements.get("user_credentials"))
        required_assets = _normalize_relative_path_list(
            requirements.get("assets"),
            field_name="plugin required assets",
        )

        if tenant_config_keys:
            if not config_properties:
                raise ValueError(
                    "plugin requirements.tenant_config requires config_schema.properties declarations"
                )
            missing_schema_keys = sorted(set(tenant_config_keys) - set(str(key) for key in config_properties.keys()))
            if missing_schema_keys:
                raise ValueError(
                    "plugin requirements.tenant_config contains keys not declared in config_schema.properties: "
                    + ", ".join(missing_schema_keys)
                )

        return cls(
            schema_version=_normalize_schema_version(raw.get("schema_version")),
            plugin_id=_normalize_id(raw.get("id")),
            name=name,
            version=version,
            description=str(raw.get("description", "") or "").strip(),
            entrypoint=entrypoint,
            icon_path=icon_path,
            readme_path=readme_path,
            tool_names=_normalize_str_list(raw.get("tools")),
            capabilities=_normalize_enum_list(
                raw.get("capabilities"),
                field_name="plugin capabilities",
                allowed=PLUGIN_CAPABILITIES,
            ),
            permissions=_normalize_enum_list(
                raw.get("permissions"),
                field_name="plugin permissions",
                allowed=PLUGIN_PERMISSIONS,
            ),
            config_schema=config_schema,
            tenant_config_keys=tenant_config_keys,
            user_config_keys=user_config_keys,
            tenant_credentials=tenant_credentials,
            user_credentials=user_credentials,
            required_assets=required_assets,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "entrypoint": self.entrypoint,
            "icon": self.icon_path,
            "readme": self.readme_path,
            "tools": list(self.tool_names),
            "capabilities": list(self.capabilities),
            "permissions": list(self.permissions),
            "config_schema": dict(self.config_schema),
            "requirements": {
                "tenant_config": list(self.tenant_config_keys),
                "user_config": list(self.user_config_keys),
                "tenant_credentials": list(self.tenant_credentials),
                "user_credentials": list(self.user_credentials),
                "assets": list(self.required_assets),
            },
        }


@dataclass(slots=True)
class PluginBundle:
    manifest: PluginManifest
    manifest_path: Path
    bundle_dir: Path
    entrypoint_path: Path


def _normalize_tool_name(raw: Any) -> str:
    name = str(raw or "").strip()
    if not name:
        raise ValueError("plugin tool name is required")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
        raise ValueError("plugin tool name must match [a-zA-Z0-9_.-]+")
    if name.startswith(".") or name.endswith(".") or ".." in name:
        raise ValueError("plugin tool name cannot start/end with '.' or contain '..'")
    return name


def _normalize_tool_schema(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("plugin tool parameters must be a JSON schema object")
    schema = dict(raw)
    schema_type = schema.get("type")
    if schema_type not in (None, "object"):
        raise ValueError("plugin tool parameters.type must be 'object'")
    schema["type"] = "object"
    properties = schema.get("properties")
    schema["properties"] = properties if isinstance(properties, dict) else {}
    required = schema.get("required")
    if not isinstance(required, list):
        required = []
    schema["required"] = [str(item).strip() for item in required if str(item).strip()]
    if "additionalProperties" not in schema:
        schema["additionalProperties"] = False
    return schema


class PluginBundleError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        plugin_id: str,
        missing: dict[str, list[str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.plugin_id = plugin_id
        self.missing = missing or {}


def _safe_zip_members(zip_file: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    total_size = 0
    for info in zip_file.infolist():
        filename = str(info.filename or "")
        if not filename or filename.endswith("/"):
            continue
        normalized = Path(filename)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError(f"plugin zip contains unsafe path: {filename}")
        total_size += max(int(info.file_size or 0), 0)
        if total_size > MAX_PLUGIN_UNZIPPED_BYTES:
            raise ValueError("plugin zip is too large after extraction")
        members.append(info)
    return members


def extract_plugin_zip_to_dir(zip_bytes: bytes, target_dir: Path) -> PluginBundle:
    payload = bytes(zip_bytes or b"")
    if not payload:
        raise ValueError("plugin bundle payload is empty")
    if len(payload) > MAX_PLUGIN_ZIP_BYTES:
        raise ValueError("plugin bundle payload exceeds maximum allowed size")

    root = target_dir.expanduser().resolve()
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValueError("plugin bundle is not a valid zip file") from exc

    with zip_file:
        members = _safe_zip_members(zip_file)
        for info in members:
            destination = (root / info.filename).resolve()
            if root not in destination.parents and destination != root:
                raise ValueError(f"plugin zip path escapes extraction root: {info.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(info, "r") as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)

    manifest_paths = sorted(root.rglob(PLUGIN_MANIFEST_FILENAME))
    if not manifest_paths:
        raise ValueError("plugin bundle is missing replica.plugin.json")
    if len(manifest_paths) > 1:
        raise ValueError("plugin bundle must include exactly one replica.plugin.json")
    return load_plugin_bundle(manifest_paths[0])


def load_plugin_manifest(path: Path) -> PluginManifest:
    manifest_path = path.expanduser().resolve()
    if manifest_path.is_dir():
        manifest_path = manifest_path / PLUGIN_MANIFEST_FILENAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"plugin manifest is unreadable: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"plugin manifest is not valid JSON: {manifest_path}") from exc
    return PluginManifest.from_dict(payload)


def load_plugin_bundle(path: Path) -> PluginBundle:
    manifest_path = path.expanduser().resolve()
    if manifest_path.is_dir():
        manifest_path = manifest_path / PLUGIN_MANIFEST_FILENAME
    manifest = load_plugin_manifest(manifest_path)
    bundle_dir = manifest_path.parent
    entrypoint_path = bundle_dir / manifest.entrypoint
    if not entrypoint_path.exists() or not entrypoint_path.is_file():
        raise PluginBundleError(
            "plugin entrypoint is missing from the bundle",
            plugin_id=manifest.plugin_id,
            missing={"entrypoint": [manifest.entrypoint]},
        )
    return PluginBundle(
        manifest=manifest,
        manifest_path=manifest_path,
        bundle_dir=bundle_dir,
        entrypoint_path=entrypoint_path,
    )


def load_plugin_bundle_from_zip_bytes(
    zip_bytes: bytes,
    *,
    cache_root: Path,
    plugin_id_hint: str = "",
) -> PluginBundle:
    normalized_hint = re.sub(r"[^a-z0-9._-]+", "-", str(plugin_id_hint or "").strip().lower()).strip("-")
    digest = hashlib.sha1(bytes(zip_bytes or b"")).hexdigest()[:12]
    bundle_dir = cache_root / f"{normalized_hint or 'plugin'}-{digest}"
    return extract_plugin_zip_to_dir(bytes(zip_bytes or b""), bundle_dir)


@dataclass(slots=True)
class PluginEnablement:
    installed: bool = True
    platform_approved: bool = False
    tenant_enabled: bool = False
    user_allowed: bool = False
    initialization_error: str = ""


@dataclass(slots=True)
class PluginRuntimeContext:
    tenant_config_keys: set[str] = field(default_factory=set)
    user_config_keys: set[str] = field(default_factory=set)
    tenant_credentials: set[str] = field(default_factory=set)
    user_credentials: set[str] = field(default_factory=set)
    available_assets: set[str] = field(default_factory=set)
    approved_permissions: set[str] = field(default_factory=set)


@dataclass(slots=True)
class RegisteredPluginTool:
    name: str
    description: str
    parameters: dict[str, Any]
    executor: Callable[[dict[str, Any]], Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
        }


@dataclass(slots=True)
class PluginReadinessReport:
    plugin_id: str
    active: bool
    stage: str
    reasons: list[str] = field(default_factory=list)
    missing: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pluginId": self.plugin_id,
            "active": self.active,
            "stage": self.stage,
            "reasons": list(self.reasons),
            "missing": {key: list(value) for key, value in self.missing.items()},
        }


@dataclass(slots=True)
class ActivePlugin:
    manifest: PluginManifest
    manifest_path: Path
    readiness: PluginReadinessReport
    registered_tools: list[RegisteredPluginTool] = field(default_factory=list)
    runtime_config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.manifest.schema_version,
            "pluginId": self.manifest.plugin_id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "manifestPath": str(self.manifest_path),
            "tools": list(self.manifest.tool_names),
            "registeredTools": [tool.to_dict() for tool in self.registered_tools],
            "configKeys": sorted(str(key) for key in self.runtime_config.keys() if str(key).strip()),
            "readiness": self.readiness.to_dict(),
        }


class PluginRegistrationApi:
    def __init__(self, *, plugin_id: str, plugin_config: dict[str, Any]) -> None:
        self.plugin_id = str(plugin_id or "").strip().lower()
        config_payload = dict(plugin_config) if isinstance(plugin_config, dict) else {}
        self.config = config_payload
        self.plugin_config = config_payload
        self._tools: dict[str, RegisteredPluginTool] = {}

    @property
    def tools(self) -> list[RegisteredPluginTool]:
        return list(self._tools.values())

    def register_tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        handler: Callable[[dict[str, Any]], Any] | None = None,
        executor: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        tool_name = _normalize_tool_name(name)
        if tool_name in self._tools:
            raise ValueError(f"plugin tool already registered: {tool_name}")
        fn = executor or handler
        if not callable(fn):
            raise ValueError(f"plugin tool '{tool_name}' must provide a callable handler")
        text = str(description or "").strip()
        if not text:
            raise ValueError(f"plugin tool '{tool_name}' description is required")
        normalized_parameters = _normalize_tool_schema(parameters or {"type": "object", "properties": {}, "required": []})
        self._tools[tool_name] = RegisteredPluginTool(
            name=tool_name,
            description=text,
            parameters=normalized_parameters,
            executor=fn,
        )

    def tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
    ) -> Callable[[Callable[[dict[str, Any]], Any]], Callable[[dict[str, Any]], Any]]:
        def _decorator(fn: Callable[[dict[str, Any]], Any]) -> Callable[[dict[str, Any]], Any]:
            self.register_tool(
                name=name,
                description=description,
                parameters=parameters,
                handler=fn,
            )
            return fn

        return _decorator

    # Reserved API surfaces for later phases.
    def register_hook(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - explicit v1 guard
        raise NotImplementedError("plugin hooks are not enabled in this runtime")

    def register_skill_pack(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - explicit v1 guard
        raise NotImplementedError("plugin skill packs are not enabled in this runtime")

    def register_service(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - explicit v1 guard
        raise NotImplementedError("plugin services are not enabled in this runtime")

    def register_provider(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - explicit v1 guard
        raise NotImplementedError("plugin providers are not enabled in this runtime")


def _import_plugin_entrypoint(bundle: PluginBundle) -> Callable[[PluginRegistrationApi], Any]:
    module_hint = re.sub(r"[^a-zA-Z0-9_]+", "_", bundle.manifest.plugin_id).strip("_") or "plugin"
    digest = hashlib.sha1(str(bundle.entrypoint_path).encode("utf-8")).hexdigest()[:10]
    module_name = f"agent_console_runtime_plugin_{module_hint}_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, bundle.entrypoint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load plugin entrypoint module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    register_fn = getattr(module, "register", None)
    if not callable(register_fn):
        raise RuntimeError("plugin entrypoint must export callable register(api)")
    return register_fn


def validate_plugin_bundle_loadable(bundle: PluginBundle) -> None:
    _import_plugin_entrypoint(bundle)


def load_registered_plugin_tools(
    bundle: PluginBundle,
    *,
    plugin_config: dict[str, Any] | None = None,
) -> list[RegisteredPluginTool]:
    register_fn = _import_plugin_entrypoint(bundle)
    api = PluginRegistrationApi(
        plugin_id=bundle.manifest.plugin_id,
        plugin_config=(plugin_config if isinstance(plugin_config, dict) else {}),
    )
    register_fn(api)
    return api.tools


def discover_plugin_manifest_paths(root: Path) -> list[Path]:
    base = root.expanduser()
    if base.is_file():
        return [base.resolve()] if base.name == PLUGIN_MANIFEST_FILENAME else []
    if not base.exists() or not base.is_dir():
        return []

    seen: set[Path] = set()
    output: list[Path] = []
    for path in sorted(base.rglob(PLUGIN_MANIFEST_FILENAME)):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        output.append(resolved)
    return output


def evaluate_plugin_readiness(
    manifest: PluginManifest,
    enablement: PluginEnablement,
    context: PluginRuntimeContext,
) -> PluginReadinessReport:
    plugin_id = manifest.plugin_id
    plugin_scope = str(plugin_id or "").strip().lower()

    def _missing_required_keys(required: list[str], available: set[str]) -> list[str]:
        missing_keys: list[str] = []
        for key in required:
            normalized = str(key or "").strip()
            if not normalized:
                continue
            if normalized in available:
                continue
            scoped = f"{plugin_scope}:{normalized}" if plugin_scope else normalized
            if scoped in available:
                continue
            missing_keys.append(normalized)
        return sorted(set(missing_keys))

    if not enablement.installed:
        return PluginReadinessReport(
            plugin_id=plugin_id,
            active=False,
            stage="install",
            reasons=["plugin is not installed"],
        )

    if not enablement.platform_approved:
        return PluginReadinessReport(
            plugin_id=plugin_id,
            active=False,
            stage="platform_approval",
            reasons=["plugin is not approved by the platform admin"],
        )

    if not enablement.tenant_enabled:
        return PluginReadinessReport(
            plugin_id=plugin_id,
            active=False,
            stage="tenant_enablement",
            reasons=["plugin is not enabled for this tenant"],
        )

    if not enablement.user_allowed:
        return PluginReadinessReport(
            plugin_id=plugin_id,
            active=False,
            stage="user_assignment",
            reasons=["plugin is not assigned or allowed for this user"],
        )

    missing_permissions = sorted(set(manifest.permissions) - set(context.approved_permissions))
    if missing_permissions:
        return PluginReadinessReport(
            plugin_id=plugin_id,
            active=False,
            stage="permissions",
            reasons=["plugin requests permissions that were not approved"],
            missing={"permissions": missing_permissions},
        )

    missing: dict[str, list[str]] = {}
    requirement_groups = {
        "tenant_config": _missing_required_keys(manifest.tenant_config_keys, set(context.tenant_config_keys)),
        "user_config": _missing_required_keys(manifest.user_config_keys, set(context.user_config_keys)),
        "tenant_credentials": _missing_required_keys(manifest.tenant_credentials, set(context.tenant_credentials)),
        "user_credentials": _missing_required_keys(manifest.user_credentials, set(context.user_credentials)),
        "assets": sorted(set(manifest.required_assets) - set(context.available_assets)),
    }
    for key, values in requirement_groups.items():
        if values:
            missing[key] = values

    if missing:
        return PluginReadinessReport(
            plugin_id=plugin_id,
            active=False,
            stage="requirements",
            reasons=["plugin requirements are incomplete for this runtime context"],
            missing=missing,
        )

    init_error = str(enablement.initialization_error or "").strip()
    if init_error:
        return PluginReadinessReport(
            plugin_id=plugin_id,
            active=False,
            stage="initialization",
            reasons=[init_error],
        )

    return PluginReadinessReport(
        plugin_id=plugin_id,
        active=True,
        stage="active",
    )


def resolve_active_plugins(
    config: Any,
    *,
    installed_plugins: list[dict[str, Any]] | None = None,
    runtime_plugin_configs: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[ActivePlugin], list[PluginReadinessReport]]:
    manifest_root = Path(getattr(config, "manifests_dir", Path("./.data/plugins")))
    additional_roots = [
        Path(item).expanduser()
        for item in getattr(config, "additional_manifests_dirs", []) or []
        if str(item or "").strip()
    ]
    scan_roots = [manifest_root, *additional_roots]
    platform_approved = {str(item).strip().lower() for item in getattr(config, "platform_approved", []) if str(item).strip()}
    tenant_enabled = {str(item).strip().lower() for item in getattr(config, "tenant_enabled", []) if str(item).strip()}
    user_allowed = {str(item).strip().lower() for item in getattr(config, "user_allowed", []) if str(item).strip()}
    platform_gate_open = not platform_approved
    tenant_gate_open = not tenant_enabled
    user_gate_open = not user_allowed
    approved_permissions = {
        str(item).strip() for item in getattr(config, "approved_permissions", []) if str(item).strip()
    }
    tenant_config_keys = {str(item).strip() for item in getattr(config, "tenant_config_keys", []) if str(item).strip()}
    user_config_keys = {str(item).strip() for item in getattr(config, "user_config_keys", []) if str(item).strip()}
    tenant_credentials = {str(item).strip() for item in getattr(config, "tenant_credentials", []) if str(item).strip()}
    user_credentials = {str(item).strip() for item in getattr(config, "user_credentials", []) if str(item).strip()}
    plugin_configs_raw = getattr(config, "plugin_configs", {})
    plugin_configs: dict[str, dict[str, Any]] = {}
    if isinstance(plugin_configs_raw, dict):
        for raw_plugin_id, raw_config in plugin_configs_raw.items():
            plugin_id = str(raw_plugin_id or "").strip().lower()
            if not plugin_id or not isinstance(raw_config, dict):
                continue
            plugin_configs[plugin_id] = dict(raw_config)
    if isinstance(runtime_plugin_configs, dict):
        for raw_plugin_id, raw_config in runtime_plugin_configs.items():
            plugin_id = str(raw_plugin_id or "").strip().lower()
            if not plugin_id or not isinstance(raw_config, dict):
                continue
            plugin_configs[plugin_id] = dict(raw_config)
            for raw_key in raw_config.keys():
                key = str(raw_key or "").strip()
                if not key:
                    continue
                tenant_config_keys.add(key)
                tenant_config_keys.add(f"{plugin_id}:{key}")

    active_plugins: list[ActivePlugin] = []
    reports: list[PluginReadinessReport] = []
    seen_plugin_ids: set[str] = set()
    discovered_bundles: list[PluginBundle] = []
    seen_manifest_paths: set[Path] = set()

    runtime_cache_root = Path(tempfile.mkdtemp(prefix="agent-console-plugin-runtime-"))

    for root in scan_roots:
        for manifest_path in discover_plugin_manifest_paths(root):
            resolved = manifest_path.resolve()
            if resolved in seen_manifest_paths:
                continue
            seen_manifest_paths.add(resolved)
            try:
                discovered_bundles.append(load_plugin_bundle(resolved))
            except PluginBundleError as exc:
                reports.append(
                    PluginReadinessReport(
                        plugin_id=exc.plugin_id,
                        active=False,
                        stage="bundle",
                        reasons=[str(exc)],
                        missing={key: list(value) for key, value in exc.missing.items()},
                    )
                )
            except ValueError as exc:
                plugin_id = resolved.stem.replace(".plugin", "").strip().lower() or resolved.name.lower()
                reports.append(
                    PluginReadinessReport(
                        plugin_id=plugin_id,
                        active=False,
                        stage="manifest",
                        reasons=[str(exc)],
                    )
                )

    for installed in installed_plugins or []:
        if not isinstance(installed, dict):
            continue
        plugin_id_hint = str(installed.get("plugin_id", "") or "").strip().lower()
        payload = installed.get("bundle_zip")
        if isinstance(payload, memoryview):
            zip_bytes = payload.tobytes()
        else:
            zip_bytes = bytes(payload or b"")
        if not zip_bytes:
            reports.append(
                PluginReadinessReport(
                    plugin_id=plugin_id_hint or "unknown",
                    active=False,
                    stage="install",
                    reasons=["plugin bundle payload is empty"],
                )
            )
            continue
        try:
            discovered_bundles.append(
                load_plugin_bundle_from_zip_bytes(
                    zip_bytes,
                    cache_root=runtime_cache_root,
                    plugin_id_hint=plugin_id_hint,
                )
            )
        except PluginBundleError as exc:
            reports.append(
                PluginReadinessReport(
                    plugin_id=exc.plugin_id or plugin_id_hint or "unknown",
                    active=False,
                    stage="bundle",
                    reasons=[str(exc)],
                    missing={key: list(value) for key, value in exc.missing.items()},
                )
            )
        except ValueError as exc:
            reports.append(
                PluginReadinessReport(
                    plugin_id=plugin_id_hint or "unknown",
                    active=False,
                    stage="manifest",
                    reasons=[str(exc)],
                )
            )

    for bundle in discovered_bundles:

        manifest = bundle.manifest
        if manifest.plugin_id in seen_plugin_ids:
            reports.append(
                PluginReadinessReport(
                    plugin_id=manifest.plugin_id,
                    active=False,
                    stage="manifest",
                    reasons=["duplicate plugin id ignored after first manifest"],
                )
            )
            continue
        seen_plugin_ids.add(manifest.plugin_id)

        available_assets = {
            asset
            for asset in manifest.required_assets
            if (bundle.bundle_dir / asset).exists()
        }
        report = evaluate_plugin_readiness(
            manifest,
            PluginEnablement(
                installed=True,
                platform_approved=platform_gate_open or manifest.plugin_id in platform_approved,
                tenant_enabled=tenant_gate_open or manifest.plugin_id in tenant_enabled,
                user_allowed=user_gate_open or manifest.plugin_id in user_allowed,
            ),
            PluginRuntimeContext(
                tenant_config_keys=tenant_config_keys,
                user_config_keys=user_config_keys,
                tenant_credentials=tenant_credentials,
                user_credentials=user_credentials,
                available_assets=available_assets,
                approved_permissions=approved_permissions,
            ),
        )
        reports.append(report)
        if report.active:
            try:
                registered_tools = load_registered_plugin_tools(
                    bundle,
                    plugin_config=plugin_configs.get(manifest.plugin_id, {}),
                )
            except Exception as exc:
                reports[-1] = PluginReadinessReport(
                    plugin_id=manifest.plugin_id,
                    active=False,
                    stage="initialization",
                    reasons=[f"plugin failed to initialize: {exc}"],
                )
                continue
            active_plugins.append(
                ActivePlugin(
                    manifest=manifest,
                    manifest_path=bundle.manifest_path,
                    readiness=report,
                    registered_tools=registered_tools,
                    runtime_config=plugin_configs.get(manifest.plugin_id, {}),
                )
            )

    return active_plugins, reports
