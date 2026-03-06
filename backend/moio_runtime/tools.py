from __future__ import annotations

import asyncio
import base64
import contextvars
import csv
import hashlib
import importlib
import inspect
import io
import json
import mimetypes
import os
import re
import ssl
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from .plugins import ActivePlugin, RegisteredPluginTool

ToolExecutor = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    group: str
    label: str
    executor: ToolExecutor
    source: str = "core"


class ToolError(Exception):
    pass


_EXECUTION_CONTEXT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "webchat_replica_tool_execution_context",
    default=None,
)


def _require_optional(module_name: str, install_hint: str):
    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - runtime guard
        raise ToolError(f"missing dependency '{module_name}'. Install with: pip install {install_hint}") from exc


class EncryptedVault:
    def __init__(self, path: Path, passphrase: str):
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        cryptography = _require_optional("cryptography.fernet", "cryptography")
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(passphrase.encode("utf-8")).digest())
        self._fernet = cryptography.Fernet(derived_key)

    @staticmethod
    def _validate_key(key: str) -> str:
        normalized = key.strip()
        if not normalized:
            raise ToolError("vault key is required")
        if len(normalized) > 180:
            raise ToolError("vault key is too long")
        if not re.fullmatch(r"[a-zA-Z0-9._:/-]+", normalized):
            raise ToolError("vault key must match [a-zA-Z0-9._:/-]+")
        return normalized

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "records": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ToolError(f"vault file is unreadable: {self.path}") from exc
        if not isinstance(payload, dict):
            raise ToolError("vault payload is invalid")
        records = payload.get("records")
        if not isinstance(records, dict):
            records = {}
        payload["records"] = records
        payload["version"] = 1
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def list_keys(self, prefix: str | None = None, limit: int = 200) -> list[str]:
        payload = self._load()
        keys = sorted(str(key) for key in payload["records"].keys())
        if prefix:
            keys = [key for key in keys if key.startswith(prefix)]
        return keys[: max(1, min(limit, 5000))]

    def set(self, key: str, value: Any, overwrite: bool = True) -> dict[str, Any]:
        normalized_key = self._validate_key(key)
        payload = self._load()
        records: dict[str, Any] = payload["records"]
        now_ms = int(time.time() * 1000)
        if normalized_key in records and not overwrite:
            raise ToolError(f"vault key already exists: {normalized_key}")
        serialized = json.dumps(value, ensure_ascii=False)
        encrypted = self._fernet.encrypt(serialized.encode("utf-8")).decode("utf-8")
        previous = records.get(normalized_key)
        created_at_ms = (
            int(previous.get("createdAtMs"))
            if isinstance(previous, dict) and isinstance(previous.get("createdAtMs"), int)
            else now_ms
        )
        records[normalized_key] = {
            "ciphertext": encrypted,
            "createdAtMs": created_at_ms,
            "updatedAtMs": now_ms,
        }
        payload["updatedAtMs"] = now_ms
        self._save(payload)
        return {
            "key": normalized_key,
            "createdAtMs": created_at_ms,
            "updatedAtMs": now_ms,
        }

    def get(self, key: str) -> dict[str, Any]:
        normalized_key = self._validate_key(key)
        payload = self._load()
        entry = payload["records"].get(normalized_key)
        if not isinstance(entry, dict):
            return {"found": False, "key": normalized_key}
        ciphertext = str(entry.get("ciphertext", ""))
        if not ciphertext:
            return {"found": False, "key": normalized_key}
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
            value = json.loads(plaintext)
        except Exception as exc:
            raise ToolError(f"vault decryption failed for key: {normalized_key}") from exc
        return {
            "found": True,
            "key": normalized_key,
            "value": value,
            "createdAtMs": entry.get("createdAtMs"),
            "updatedAtMs": entry.get("updatedAtMs"),
        }

    def delete(self, key: str) -> dict[str, Any]:
        normalized_key = self._validate_key(key)
        payload = self._load()
        records: dict[str, Any] = payload["records"]
        existed = normalized_key in records
        if existed:
            records.pop(normalized_key, None)
            payload["updatedAtMs"] = int(time.time() * 1000)
            self._save(payload)
        return {"key": normalized_key, "deleted": bool(existed)}


class ToolRegistry:
    _MOIO_ENDPOINT_ALIASES: dict[str, str] = {
        "chatui/endpoints": "/api/v1/meta/endpoints/",
        "chatui/endpoints/": "/api/v1/meta/endpoints/",
        "api/endpoints": "/api/v1/meta/endpoints/",
        "api/endpoints/": "/api/v1/meta/endpoints/",
    }

    def __init__(
        self,
        workspace_root: Path,
        shell_enabled: bool,
        shell_timeout_seconds: float,
        docker_enabled: bool,
        docker_timeout_seconds: float,
        dynamic_tools_enabled: bool,
        dynamic_tools_dir: Path,
        package_install_enabled: bool,
        package_install_timeout_seconds: float,
        vault_enabled: bool,
        vault_file: Path,
        vault_passphrase: str | None,
        api_connection_resolver: Callable[[str], dict[str, Any] | None] | None = None,
        memory_recorder: Callable[..., dict[str, Any]] | None = None,
        memory_searcher: Callable[..., list[dict[str, Any]]] | None = None,
        memory_recent: Callable[..., list[dict[str, Any]]] | None = None,
        active_plugins: list[ActivePlugin] | None = None,
    ):
        self.workspace_root = workspace_root.expanduser().resolve()
        self.shell_enabled = shell_enabled
        self.shell_timeout_seconds = shell_timeout_seconds
        self.docker_enabled = docker_enabled
        self.docker_timeout_seconds = docker_timeout_seconds
        self.dynamic_tools_enabled = dynamic_tools_enabled
        self.dynamic_tools_dir = (
            dynamic_tools_dir.expanduser().resolve()
            if dynamic_tools_dir.is_absolute()
            else (self.workspace_root / dynamic_tools_dir).resolve()
        )
        self.package_install_enabled = package_install_enabled
        self.package_install_timeout_seconds = package_install_timeout_seconds
        self.vault_enabled = vault_enabled
        self.vault_file = (
            vault_file.expanduser().resolve()
            if vault_file.is_absolute()
            else (self.workspace_root / vault_file).resolve()
        )
        self.vault_passphrase = (vault_passphrase or "").strip() or None
        self._vault: EncryptedVault | None = None
        self.api_connection_resolver = api_connection_resolver
        self._api_connection_resolver_accepts_initiator = False
        if callable(self.api_connection_resolver):
            try:
                signature = inspect.signature(self.api_connection_resolver)
            except (TypeError, ValueError):
                signature = None
            if signature is not None:
                for name, param in signature.parameters.items():
                    if name == "initiator" or param.kind == inspect.Parameter.VAR_KEYWORD:
                        self._api_connection_resolver_accepts_initiator = True
                        break
        self.memory_recorder = memory_recorder
        self.memory_searcher = memory_searcher
        self.memory_recent = memory_recent
        self._oauth_tokens: dict[str, dict[str, Any]] = {}

        self._tools: dict[str, ToolSpec] = {}
        self._dynamic_tool_names: set[str] = set()
        self._plugin_tool_names: set[str] = set()
        self._plugin_tool_targets: dict[str, str] = {}
        self._plugin_tool_plugins: dict[str, str] = {}
        self._openai_name_to_tool_name: dict[str, str] = {}
        self._register_builtin_tools()
        self._load_dynamic_tools()
        self._register_plugin_custom_tools(active_plugins or [])
        self._register_plugin_tool_aliases(active_plugins or [])

    def get(self, name: str) -> ToolSpec:
        tool = self._tools.get(name)
        if not tool:
            raise ToolError(f"unknown tool: {name}")
        return tool

    def list_specs(self, allowlist: list[str]) -> list[ToolSpec]:
        names = {name.strip() for name in allowlist if name.strip()}
        if not names:
            specs = [
                tool
                for tool in self._tools.values()
                if (tool.name in self._dynamic_tool_names or tool.name in self._plugin_tool_names)
                and self._tool_is_enabled(tool.name)
            ]
            return sorted(specs, key=lambda entry: entry.name)

        specs: list[ToolSpec] = []
        for tool in self._tools.values():
            if not self._tool_is_enabled(tool.name):
                continue
            if tool.name in self._dynamic_tool_names or tool.name in self._plugin_tool_names:
                specs.append(tool)
                continue
            if self._is_allowed_by_allowlist(tool.name, names):
                specs.append(tool)
        return sorted(specs, key=lambda entry: entry.name)

    def list_specs_exact(self, allowed_names: list[str]) -> list[ToolSpec]:
        names = {str(name).strip() for name in allowed_names if str(name).strip()}
        if not names:
            return []
        specs = [
            tool
            for tool in self._tools.values()
            if tool.name in names and self._tool_is_enabled(tool.name)
        ]
        return sorted(specs, key=lambda entry: entry.name)

    def _build_tools_catalog_from_specs(self, specs: list[ToolSpec]) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for tool in specs:
            group = groups.setdefault(
                f"{tool.source}:{tool.group}",
                {
                    "id": f"{tool.source}:{tool.group}",
                    "label": tool.group,
                    "source": tool.source,
                    "tools": [],
                },
            )
            group["tools"].append(
                {
                    "id": tool.name,
                    "label": tool.label,
                    "description": tool.description,
                    "source": tool.source,
                    "defaultProfiles": ["full"],
                }
            )
        return {
            "profiles": [
                {"id": "minimal", "label": "minimal"},
                {"id": "full", "label": "full"},
            ],
            "groups": sorted(groups.values(), key=lambda entry: str(entry["id"])),
        }

    def tools_catalog(self, allowlist: list[str]) -> dict[str, Any]:
        return self._build_tools_catalog_from_specs(self.list_specs(allowlist))

    def tools_catalog_exact(self, allowed_names: list[str]) -> dict[str, Any]:
        return self._build_tools_catalog_from_specs(self.list_specs_exact(allowed_names))

    def _build_openai_tool_schemas_from_specs(self, specs: list[ToolSpec]) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        self._openai_name_to_tool_name = {}
        used_names: dict[str, str] = {}
        for tool in specs:
            base_name = self.to_openai_function_name(tool.name)
            openai_name = base_name
            if openai_name in used_names and used_names[openai_name] != tool.name:
                suffix = hashlib.sha1(tool.name.encode("utf-8")).hexdigest()[:8]
                openai_name = f"{base_name}_{suffix}"
            counter = 2
            while openai_name in used_names and used_names[openai_name] != tool.name:
                openai_name = f"{base_name}_{counter}"
                counter += 1
            used_names[openai_name] = tool.name
            self._openai_name_to_tool_name[openai_name] = tool.name
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": openai_name,
                        "description": f"{tool.description} Canonical id: {tool.name}",
                        "parameters": tool.parameters,
                    },
                }
            )
        return schemas

    def openai_tool_schemas(self, allowlist: list[str]) -> list[dict[str, Any]]:
        return self._build_openai_tool_schemas_from_specs(self.list_specs(allowlist))

    def openai_tool_schemas_exact(self, allowed_names: list[str]) -> list[dict[str, Any]]:
        return self._build_openai_tool_schemas_from_specs(self.list_specs_exact(allowed_names))

    def resolve_tool_name(self, incoming_name: str) -> str:
        if incoming_name in self._tools:
            return incoming_name
        mapped = self._openai_name_to_tool_name.get(incoming_name)
        if mapped:
            return mapped
        return incoming_name

    @staticmethod
    def to_openai_function_name(tool_name: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", tool_name).strip("_")
        return normalized or "tool"

    def _current_execution_context(self) -> dict[str, Any]:
        current = _EXECUTION_CONTEXT.get()
        return dict(current) if isinstance(current, dict) else {}

    def _current_initiator(self) -> dict[str, Any] | None:
        context = self._current_execution_context()
        initiator = context.get("initiator")
        return dict(initiator) if isinstance(initiator, dict) else None

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        execution_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        spec = self.get(name)
        token = _EXECUTION_CONTEXT.set(dict(execution_context) if isinstance(execution_context, dict) else None)
        try:
            return await spec.executor(arguments)
        finally:
            _EXECUTION_CONTEXT.reset(token)

    @staticmethod
    def _is_allowed_by_allowlist(tool_name: str, allowlist: set[str]) -> bool:
        if tool_name in allowlist:
            return True
        if "*" in allowlist or "all" in allowlist:
            return True
        for pattern in allowlist:
            if pattern.endswith(".*") and tool_name.startswith(f"{pattern[:-2]}."):
                return True
            if pattern.endswith(":*") and tool_name.startswith(f"{pattern[:-2]}."):
                return True
        return False

    def _tool_is_enabled(self, tool_name: str) -> bool:
        plugin_target = self._plugin_tool_targets.get(tool_name)
        if plugin_target:
            return self._tool_is_enabled(plugin_target)
        if tool_name == "shell.run":
            return self.shell_enabled
        if tool_name == "docker.run":
            return self.docker_enabled
        if tool_name == "tools.create":
            return self.dynamic_tools_enabled
        if tool_name == "packages.install":
            return self.package_install_enabled
        if tool_name.startswith("vault."):
            return self.vault_enabled
        return True

    def plugin_id_for_tool(self, tool_name: str) -> str:
        return str(self._plugin_tool_plugins.get(str(tool_name or "").strip(), "") or "").strip()

    @staticmethod
    def _validate_tool_name(raw: Any) -> str:
        name = str(raw or "").strip()
        if not name:
            raise ToolError("name is required")
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name):
            raise ToolError("name must match [a-zA-Z0-9_.-]+")
        if name.startswith(".") or name.endswith(".") or ".." in name:
            raise ToolError("name cannot start/end with '.' or contain '..'")
        return name

    @staticmethod
    def _validate_tool_schema(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ToolError("parameters must be a JSON schema object")
        schema = dict(raw)
        schema_type = schema.get("type")
        if schema_type not in (None, "object"):
            raise ToolError("parameters.type must be 'object'")
        schema["type"] = "object"
        if not isinstance(schema.get("properties"), dict):
            schema["properties"] = {}
        required = schema.get("required")
        if not isinstance(required, list):
            required = []
        schema["required"] = [str(entry).strip() for entry in required if str(entry).strip()]
        if "additionalProperties" not in schema:
            schema["additionalProperties"] = False
        return schema

    def _dynamic_tool_path(self, tool_name: str) -> Path:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", tool_name).strip("_") or "tool"
        digest = hashlib.sha1(tool_name.encode("utf-8")).hexdigest()[:10]
        return self.dynamic_tools_dir / f"{slug}-{digest}.json"

    def _build_dynamic_executor(self, tool_name: str, code: str) -> ToolExecutor:
        try:
            compiled = compile(code, f"<dynamic-tool:{tool_name}>", "exec")
        except SyntaxError as exc:
            raise ToolError(f"invalid Python code: {exc}") from exc

        namespace: dict[str, Any] = {"__builtins__": __builtins__}
        try:
            exec(compiled, namespace, namespace)
        except Exception as exc:
            raise ToolError(f"dynamic tool initialization failed: {exc}") from exc

        candidate = namespace.get("run") or namespace.get("tool_main") or namespace.get("execute")
        if not callable(candidate):
            raise ToolError("code must define callable run(arguments, context) or run(arguments)")

        signature = inspect.signature(candidate)
        params = [
            param
            for param in signature.parameters.values()
            if param.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        ]
        accepts_context = (
            any(param.kind == inspect.Parameter.VAR_POSITIONAL for param in signature.parameters.values())
            or len(params) >= 2
        )

        async def _executor(arguments: dict[str, Any]) -> dict[str, Any]:
            context = {
                "workspace_root": str(self.workspace_root),
                "dynamic_tools_dir": str(self.dynamic_tools_dir),
                "resolve_workspace_path": lambda raw: str(self._resolve_workspace_path(str(raw))),
            }
            try:
                value = candidate(arguments, context) if accepts_context else candidate(arguments)
                if inspect.isawaitable(value):
                    value = await value
            except ToolError:
                raise
            except Exception as exc:
                raise ToolError(f"dynamic tool {tool_name} failed: {exc}") from exc

            if value is None:
                return {"ok": True}
            if isinstance(value, dict):
                return value
            try:
                json.dumps(value)
            except TypeError:
                value = str(value)
            return {"result": value}

        return _executor

    def _register_dynamic_tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        code: str,
        group: str | None,
        label: str | None,
    ) -> ToolSpec:
        normalized_name = self._validate_tool_name(name)
        if normalized_name in self._tools and normalized_name not in self._dynamic_tool_names:
            raise ToolError(f"cannot overwrite builtin tool: {normalized_name}")
        if not isinstance(description, str) or not description.strip():
            raise ToolError("description is required")
        if not isinstance(code, str) or not code.strip():
            raise ToolError("code is required")

        normalized_schema = self._validate_tool_schema(parameters)
        normalized_group = str(group or "custom").strip() or "custom"
        normalized_label = str(label or normalized_name).strip() or normalized_name
        executor = self._build_dynamic_executor(normalized_name, code)

        spec = ToolSpec(
            name=normalized_name,
            description=description.strip(),
            parameters=normalized_schema,
            group=normalized_group,
            label=normalized_label,
            executor=executor,
            source="dynamic",
        )
        self._tools[normalized_name] = spec
        self._dynamic_tool_names.add(normalized_name)
        return spec

    def _load_dynamic_tools(self) -> None:
        if not self.dynamic_tools_enabled:
            return
        self.dynamic_tools_dir.mkdir(parents=True, exist_ok=True)
        for tool_file in sorted(self.dynamic_tools_dir.glob("*.json")):
            try:
                payload = json.loads(tool_file.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                self._register_dynamic_tool(
                    name=str(payload.get("name", "")).strip(),
                    description=str(payload.get("description", "")).strip(),
                    parameters=payload.get("parameters", {}),
                    code=str(payload.get("code", "")),
                    group=str(payload.get("group", "")).strip() or "custom",
                    label=str(payload.get("label", "")).strip() or None,
                )
            except Exception:
                # Keep startup resilient when one persisted tool is invalid.
                continue

    def _register_plugin_tool_aliases(self, active_plugins: list[ActivePlugin]) -> None:
        for active_plugin in active_plugins:
            manifest = active_plugin.manifest
            group_label = str(manifest.name or manifest.plugin_id).strip() or manifest.plugin_id
            source_label = f"plugin:{manifest.plugin_id}"
            for base_tool_name in manifest.tool_names:
                target_name = str(base_tool_name or "").strip()
                if not target_name:
                    continue
                base_spec = self._tools.get(target_name)
                if base_spec is None:
                    continue
                if str(base_spec.source or "").startswith("plugin:"):
                    continue
                alias_name = f"plugin.{manifest.plugin_id}.{target_name}"
                if alias_name in self._tools:
                    continue
                description = str(manifest.description or "").strip()
                if description:
                    description = f"{description} Executes via {target_name}."
                else:
                    description = f"Plugin-scoped alias for {target_name}. {base_spec.description}"
                self._tools[alias_name] = ToolSpec(
                    name=alias_name,
                    description=description,
                    parameters=dict(base_spec.parameters),
                    group=group_label,
                    label=f"{group_label}: {base_spec.label}",
                    executor=base_spec.executor,
                    source=source_label,
                )
                self._plugin_tool_names.add(alias_name)
                self._plugin_tool_targets[alias_name] = target_name
                self._plugin_tool_plugins[alias_name] = manifest.plugin_id

    def _register_plugin_custom_tools(self, active_plugins: list[ActivePlugin]) -> None:
        for active_plugin in active_plugins:
            manifest = active_plugin.manifest
            source_label = f"plugin:{manifest.plugin_id}"
            group_label = str(manifest.name or manifest.plugin_id).strip() or manifest.plugin_id
            for registered in active_plugin.registered_tools:
                if not isinstance(registered, RegisteredPluginTool):
                    continue
                tool_name = str(registered.name or "").strip()
                if not tool_name or tool_name in self._tools:
                    continue
                description = str(registered.description or "").strip() or f"Tool from plugin {manifest.plugin_id}."
                label = f"{group_label}: {tool_name}"
                executor = registered.executor
                try:
                    signature = inspect.signature(executor)
                except (TypeError, ValueError):
                    signature = None
                positional_params: list[inspect.Parameter] = []
                accepts_varargs = False
                if signature is not None:
                    for param in signature.parameters.values():
                        if param.kind == inspect.Parameter.VAR_POSITIONAL:
                            accepts_varargs = True
                            break
                        if param.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}:
                            positional_params.append(param)
                accepts_args = accepts_varargs or len(positional_params) >= 1
                accepts_context = accepts_varargs or len(positional_params) >= 2

                async def _executor(
                    arguments: dict[str, Any],
                    fn: Callable[[dict[str, Any]], Any] = executor,
                    tool_id: str = tool_name,
                    with_args: bool = accepts_args,
                    with_context: bool = accepts_context,
                ) -> dict[str, Any]:
                    try:
                        normalized_args = arguments if isinstance(arguments, dict) else {}
                        if with_context:
                            value = fn(normalized_args, self._current_execution_context())
                        elif with_args:
                            value = fn(normalized_args)
                        else:
                            value = fn()
                        if inspect.isawaitable(value):
                            value = await value
                    except ToolError:
                        raise
                    except Exception as exc:
                        raise ToolError(f"plugin tool {tool_id} failed: {exc}") from exc
                    if value is None:
                        return {"ok": True}
                    if isinstance(value, dict):
                        return value
                    try:
                        json.dumps(value)
                    except TypeError:
                        value = str(value)
                    return {"result": value}

                self._tools[tool_name] = ToolSpec(
                    name=tool_name,
                    description=description,
                    parameters=dict(registered.parameters),
                    group=group_label,
                    label=label,
                    executor=_executor,
                    source=source_label,
                )
                self._plugin_tool_names.add(tool_name)
                self._plugin_tool_plugins[tool_name] = manifest.plugin_id

    def _persist_dynamic_tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        code: str,
        group: str,
        label: str,
    ) -> Path:
        self.dynamic_tools_dir.mkdir(parents=True, exist_ok=True)
        path = self._dynamic_tool_path(name)
        payload = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "code": code,
            "group": group,
            "label": label,
        }
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        return path

    def _register_builtin_tools(self) -> None:
        self._tools["files.read"] = ToolSpec(
            name="files.read",
            label="Read file",
            description="Read a UTF-8 text file from the workspace.",
            group="files",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            executor=self._tool_files_read,
        )

        self._tools["files.write"] = ToolSpec(
            name="files.write",
            label="Write file",
            description="Write UTF-8 text content to a file under the workspace.",
            group="files",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {"type": "boolean"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            executor=self._tool_files_write,
        )

        self._tools["files.list"] = ToolSpec(
            name="files.list",
            label="List files",
            description="List directory entries under the workspace.",
            group="files",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_entries": {"type": "integer", "minimum": 1, "maximum": 2000},
                },
                "required": [],
                "additionalProperties": False,
            },
            executor=self._tool_files_list,
        )

        self._tools["files.search"] = ToolSpec(
            name="files.search",
            label="Search files",
            description="Search text in files under workspace using ripgrep (or fallback scanner).",
            group="files",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 2000},
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
            executor=self._tool_files_search,
        )

        self._tools["shell.run"] = ToolSpec(
            name="shell.run",
            label="Run shell",
            description="Run a shell command in the workspace and return stdout/stderr.",
            group="shell",
            parameters={
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 300},
                },
                "required": ["cmd"],
                "additionalProperties": False,
            },
            executor=self._tool_shell_run,
        )

        self._tools["code.python"] = ToolSpec(
            name="code.python",
            label="Run Python",
            description="Execute Python code in a subprocess and return output.",
            group="code",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 300},
                    "python_bin": {"type": "string"},
                },
                "required": ["code"],
                "additionalProperties": False,
            },
            executor=self._tool_code_python,
        )

        self._tools["docker.run"] = ToolSpec(
            name="docker.run",
            label="Run Docker",
            description="Run a Docker container command with optional workspace mount.",
            group="docker",
            parameters={
                "type": "object",
                "properties": {
                    "image": {"type": "string"},
                    "cmd": {"type": "string"},
                    "mount_workspace": {"type": "boolean"},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 1800},
                },
                "required": ["image", "cmd"],
                "additionalProperties": False,
            },
            executor=self._tool_docker_run,
        )

        self._tools["tools.list"] = ToolSpec(
            name="tools.list",
            label="List tools",
            description="List all available tools, including dynamic tools.",
            group="tools",
            parameters={
                "type": "object",
                "properties": {
                    "include_parameters": {"type": "boolean"},
                },
                "required": [],
                "additionalProperties": False,
            },
            executor=self._tool_tools_list,
        )

        self._tools["tools.create"] = ToolSpec(
            name="tools.create",
            label="Create tool",
            description=(
                "Create or update a dynamic Python tool. Code must define run(arguments, context) or run(arguments)."
            ),
            group="tools",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "parameters": {"type": "object"},
                    "code": {"type": "string"},
                    "group": {"type": "string"},
                    "label": {"type": "string"},
                    "persist": {"type": "boolean"},
                },
                "required": ["name", "description", "parameters", "code"],
                "additionalProperties": False,
            },
            executor=self._tool_tools_create,
        )

        self._tools["memory.record"] = ToolSpec(
            name="memory.record",
            label="Record memory",
            description="Store a memory artifact into persistent conversation memory.",
            group="memory",
            parameters={
                "type": "object",
                "properties": {
                    "session_key": {"type": "string"},
                    "run_id": {"type": "string"},
                    "kind": {"type": "string"},
                    "title": {"type": "string"},
                    "text": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            executor=self._tool_memory_record,
        )

        self._tools["memory.search"] = ToolSpec(
            name="memory.search",
            label="Search memory",
            description="Search persisted memory artifacts by text query and optional filters.",
            group="memory",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "session_key": {"type": "string"},
                    "kinds": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "required": [],
                "additionalProperties": False,
            },
            executor=self._tool_memory_search,
        )

        self._tools["memory.recent"] = ToolSpec(
            name="memory.recent",
            label="Recent memory",
            description="Fetch recent memory artifacts for a session or workspace.",
            group="memory",
            parameters={
                "type": "object",
                "properties": {
                    "session_key": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "required": [],
                "additionalProperties": False,
            },
            executor=self._tool_memory_recent,
        )

        self._tools["packages.install"] = ToolSpec(
            name="packages.install",
            label="Install packages",
            description="Install Python packages with pip in the current runtime environment.",
            group="tools",
            parameters={
                "type": "object",
                "properties": {
                    "packages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "upgrade": {"type": "boolean"},
                    "pre": {"type": "boolean"},
                    "index_url": {"type": "string"},
                    "extra_index_url": {"type": "string"},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 3600},
                },
                "required": ["packages"],
                "additionalProperties": False,
            },
            executor=self._tool_packages_install,
        )

        self._tools["vault.list"] = ToolSpec(
            name="vault.list",
            label="List vault keys",
            description="List encrypted vault keys without revealing secret values.",
            group="vault",
            parameters={
                "type": "object",
                "properties": {
                    "prefix": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
                },
                "required": [],
                "additionalProperties": False,
            },
            executor=self._tool_vault_list,
        )

        self._tools["vault.set"] = ToolSpec(
            name="vault.set",
            label="Store vault secret",
            description="Encrypt and store a secret value in the local vault.",
            group="vault",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                    "overwrite": {"type": "boolean"},
                },
                "required": ["key", "value"],
                "additionalProperties": False,
            },
            executor=self._tool_vault_set,
        )

        self._tools["vault.get"] = ToolSpec(
            name="vault.get",
            label="Get vault secret",
            description="Read and decrypt a secret value from the local vault.",
            group="vault",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                },
                "required": ["key"],
                "additionalProperties": False,
            },
            executor=self._tool_vault_get,
        )

        self._tools["vault.delete"] = ToolSpec(
            name="vault.delete",
            label="Delete vault secret",
            description="Delete a secret key from the local vault.",
            group="vault",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                },
                "required": ["key"],
                "additionalProperties": False,
            },
            executor=self._tool_vault_delete,
        )

        self._tools["web.fetch"] = ToolSpec(
            name="web.fetch",
            label="Fetch URL",
            description="Fetch an HTTP/HTTPS URL and return status, headers, and body text.",
            group="web",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                    "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 120},
                    "verify_ssl": {"type": "boolean"},
                    "prefer_curl": {"type": "boolean"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            executor=self._tool_web_fetch,
        )

        self._tools["web.request"] = ToolSpec(
            name="web.request",
            label="HTTP request",
            description="Perform an HTTP/HTTPS request (GET/POST/PUT/PATCH/DELETE/etc) with headers and optional body.",
            group="web",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "method": {"type": "string"},
                    "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                    "query": {"type": "object", "additionalProperties": {"type": "string"}},
                    "json": {"type": "object"},
                    "body": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 300},
                    "verify_ssl": {"type": "boolean"},
                    "prefer_curl": {"type": "boolean"},
                    "follow_redirects": {"type": "boolean"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            executor=self._tool_web_request,
        )

        self._tools["api.run"] = ToolSpec(
            name="api.run",
            label="Run API connection",
            description=(
                "Call a configured API connection with automatic authentication handling. "
                "Supports either a saved connection name, the built-in 'moio_internal' connection, "
                "or a tenant integration slug/key."
            ),
            group="api",
            parameters={
                "type": "object",
                "properties": {
                    "connection": {"type": "string"},
                    "integration": {"type": "string"},
                    "integration_slug": {"type": "string"},
                    "endpoint": {"type": "string"},
                    "method": {"type": "string"},
                    "params": {"type": "object"},
                    "payload": {"type": "object"},
                    "graphql_query": {"type": "string"},
                    "graphql_variables": {"type": "object"},
                    "soap_action": {"type": "string"},
                    "soap_xml": {"type": "string"},
                    "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 300},
                    "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000},
                    "extract_fields": {"type": "array", "items": {"type": "string"}},
                    "truncate_lists": {"type": "boolean"},
                    "max_items_per_list": {"type": "integer", "minimum": 1, "maximum": 5000},
                    "summarize": {"type": "boolean"},
                },
                "required": [],
                "additionalProperties": False,
            },
            executor=self._tool_api_run,
        )
        self._tools["moio_api.run"] = ToolSpec(
            name="moio_api.run",
            label="Run Moio API (priority)",
            description=(
                "High-priority internal Moio API runner. Uses the initiating user's JWT, "
                "calls the built-in internal connection, and can enrich results with endpoint contract metadata."
            ),
            group="api",
            parameters={
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string"},
                    "method": {"type": "string"},
                    "params": {"type": "object"},
                    "payload": {"type": "object"},
                    "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 300},
                    "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000},
                    "extract_fields": {"type": "array", "items": {"type": "string"}},
                    "truncate_lists": {"type": "boolean"},
                    "max_items_per_list": {"type": "integer", "minimum": 1, "maximum": 5000},
                    "summarize": {"type": "boolean"},
                    "include_contract": {"type": "boolean"},
                    "strict_contract": {"type": "boolean"},
                    "canonicalize_endpoint": {"type": "boolean"},
                },
                "required": ["endpoint"],
                "additionalProperties": False,
            },
            executor=self._tool_moio_api_run,
        )

        self._tools["web.extract"] = ToolSpec(
            name="web.extract",
            label="Extract webpage",
            description="Fetch a webpage and extract title, text, links, and image URLs.",
            group="web",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 120},
                    "max_links": {"type": "integer", "minimum": 1, "maximum": 500},
                    "verify_ssl": {"type": "boolean"},
                    "prefer_curl": {"type": "boolean"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            executor=self._tool_web_extract,
        )

        self._tools["web.scrape"] = ToolSpec(
            name="web.scrape",
            label="Scrape selector",
            description="Fetch a webpage and extract elements via CSS selector.",
            group="web",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "selector": {"type": "string"},
                    "attr": {"type": "string"},
                    "max_items": {"type": "integer", "minimum": 1, "maximum": 500},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 120},
                    "verify_ssl": {"type": "boolean"},
                    "prefer_curl": {"type": "boolean"},
                },
                "required": ["url", "selector"],
                "additionalProperties": False,
            },
            executor=self._tool_web_scrape,
        )

        self._tools["resource.read"] = ToolSpec(
            name="resource.read",
            label="Read resource",
            description=(
                "Read content from URL or file path. Supports html, txt, md, csv, json, pdf, docx, xlsx, "
                "images metadata, and audio metadata/transcription."
            ),
            group="resource",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "max_chars": {"type": "integer", "minimum": 1, "maximum": 200000},
                    "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 120},
                    "sheet": {"type": "string"},
                    "transcribe": {"type": "boolean"},
                    "audio_model": {"type": "string"},
                    "verify_ssl": {"type": "boolean"},
                    "prefer_curl": {"type": "boolean"},
                },
                "required": ["target"],
                "additionalProperties": False,
            },
            executor=self._tool_resource_read,
        )

    @staticmethod
    def _is_url(value: str) -> bool:
        parsed = urllib.parse.urlparse(value)
        return parsed.scheme in {"http", "https"}

    def _resolve_workspace_path(self, raw: str) -> Path:
        candidate = Path(raw)
        target = (self.workspace_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        if not str(target).startswith(str(self.workspace_root)):
            raise ToolError(f"path {raw!r} resolves outside workspace root {self.workspace_root}")
        return target

    @staticmethod
    def _limit_text(text: str, max_chars: int) -> tuple[str, bool]:
        if len(text) <= max_chars:
            return text, False
        return text[:max_chars], True

    @staticmethod
    def _extract_html_summary(html_text: str, base_url: str, max_chars: int, max_links: int) -> dict[str, Any]:
        bs4 = _require_optional("bs4", "beautifulsoup4")
        soup = bs4.BeautifulSoup(html_text, "html.parser")

        title = soup.title.get_text(strip=True) if soup.title else ""
        text = soup.get_text("\n", strip=True)
        text, truncated = ToolRegistry._limit_text(text, max_chars)

        links: list[str] = []
        for node in soup.select("a[href]"):
            href = str(node.get("href", "")).strip()
            if not href:
                continue
            links.append(urllib.parse.urljoin(base_url, href))
            if len(links) >= max_links:
                break

        images: list[str] = []
        for node in soup.select("img[src]"):
            src = str(node.get("src", "")).strip()
            if not src:
                continue
            images.append(urllib.parse.urljoin(base_url, src))
            if len(images) >= max_links:
                break

        return {
            "title": title,
            "text": text,
            "links": links,
            "images": images,
            "truncated": truncated,
        }

    @staticmethod
    def _normalize_headers(raw_headers: Any) -> dict[str, str]:
        headers: dict[str, str] = {}
        if isinstance(raw_headers, dict):
            for key, value in raw_headers.items():
                k = str(key).strip()
                v = str(value).strip()
                if k and v:
                    headers[k] = v
        return headers

    @staticmethod
    def _build_url_with_query(url: str, query: dict[str, str] | None) -> str:
        if not query:
            return url
        parsed = urllib.parse.urlsplit(url)
        merged_query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        for key, value in query.items():
            merged_query.append((str(key), str(value)))
        encoded_query = urllib.parse.urlencode(merged_query, doseq=True)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, encoded_query, parsed.fragment))

    @staticmethod
    def _has_header(headers: dict[str, str], name: str) -> bool:
        target = name.strip().lower()
        return any(key.strip().lower() == target for key in headers.keys())

    def _http_request(
        self,
        *,
        url: str,
        method: str,
        headers: dict[str, str],
        timeout: float,
        max_bytes: int,
        query: dict[str, str] | None = None,
        body_bytes: bytes | None = None,
        verify_ssl: bool = True,
        prefer_curl: bool = True,
        follow_redirects: bool = True,
    ) -> dict[str, Any]:
        method_upper = method.strip().upper() or "GET"
        request_url = self._build_url_with_query(url, query)
        request = urllib.request.Request(url=request_url, method=method_upper, headers=headers, data=body_bytes)
        ssl_context = None if verify_ssl else ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=ssl_context) as response:
                raw = response.read(max_bytes)
                response_headers = {key: value for key, value in response.headers.items()}
                return {
                    "ok": True,
                    "url": response.geturl(),
                    "status_code": int(response.status),
                    "headers": response_headers,
                    "content_type": response.headers.get("Content-Type", ""),
                    "body_bytes": raw,
                }
        except urllib.error.HTTPError as exc:
            body = exc.read(max_bytes)
            response_headers = {key: value for key, value in exc.headers.items()} if exc.headers else {}
            return {
                "ok": False,
                "url": request_url,
                "status_code": int(exc.code),
                "headers": response_headers,
                "content_type": response_headers.get("Content-Type", ""),
                "body_bytes": body,
                "error": str(exc.reason),
            }
        except urllib.error.URLError as exc:
            if prefer_curl and shutil.which("curl"):
                return self._http_request_with_curl(
                    url=request_url,
                    method=method_upper,
                    headers=headers,
                    timeout=timeout,
                    max_bytes=max_bytes,
                    body_bytes=body_bytes,
                    verify_ssl=verify_ssl,
                    follow_redirects=follow_redirects,
                )
            raise ToolError(f"network error: {exc.reason}") from exc

    def _http_get(
        self,
        url: str,
        headers: dict[str, str],
        timeout: float,
        max_bytes: int,
        *,
        verify_ssl: bool = True,
        prefer_curl: bool = True,
    ) -> dict[str, Any]:
        return self._http_request(
            url=url,
            method="GET",
            headers=headers,
            timeout=timeout,
            max_bytes=max_bytes,
            verify_ssl=verify_ssl,
            prefer_curl=prefer_curl,
            follow_redirects=True,
        )

    @staticmethod
    def _parse_header_blocks(raw_headers: str) -> tuple[int, dict[str, str]]:
        blocks = [block for block in raw_headers.split("\r\n\r\n") if block.strip()]
        if len(blocks) <= 1:
            blocks = [block for block in raw_headers.split("\n\n") if block.strip()]
        final = blocks[-1] if blocks else raw_headers
        lines = [line.strip("\r") for line in final.splitlines() if line.strip()]
        status_code = 0
        if lines:
            match = re.match(r"HTTP/\S+\s+(\d{3})", lines[0])
            if match:
                status_code = int(match.group(1))
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
        return status_code, headers

    def _http_request_with_curl(
        self,
        *,
        url: str,
        method: str,
        headers: dict[str, str],
        timeout: float,
        max_bytes: int,
        body_bytes: bytes | None,
        verify_ssl: bool,
        follow_redirects: bool,
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="moio-curl-") as tmp_dir:
            headers_file = Path(tmp_dir) / "headers.txt"
            body_file = Path(tmp_dir) / "body.bin"
            request_body_file = Path(tmp_dir) / "request_body.bin"
            curl_cmd = [
                "curl",
                "-sS",
                "--max-time",
                str(int(max(1.0, timeout))),
                "--connect-timeout",
                str(int(max(1.0, min(timeout, 20.0)))),
                "-X",
                method,
                "-D",
                str(headers_file),
                "-o",
                str(body_file),
                "-w",
                "%{url_effective}\n%{http_code}\n%{content_type}",
            ]
            if follow_redirects:
                curl_cmd.append("-L")
            if not verify_ssl:
                curl_cmd.append("-k")
            for key, value in headers.items():
                curl_cmd.extend(["-H", f"{key}: {value}"])
            if body_bytes is not None:
                request_body_file.write_bytes(body_bytes)
                curl_cmd.extend(["--data-binary", f"@{request_body_file}"])
            curl_cmd.append(url)

            completed = subprocess.run(
                curl_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                raise ToolError(f"network error via curl: {stderr or f'exit code {completed.returncode}'}")

            meta_lines = (completed.stdout or "").splitlines()
            effective_url = meta_lines[0].strip() if len(meta_lines) >= 1 and meta_lines[0].strip() else url
            status_from_meta = int(meta_lines[1]) if len(meta_lines) >= 2 and meta_lines[1].isdigit() else 0
            content_type = meta_lines[2].strip() if len(meta_lines) >= 3 else ""

            raw_headers = headers_file.read_text(encoding="utf-8", errors="replace") if headers_file.exists() else ""
            status_code, parsed_headers = self._parse_header_blocks(raw_headers)
            if not status_code:
                status_code = status_from_meta
            if not content_type:
                content_type = parsed_headers.get("Content-Type") or parsed_headers.get("content-type", "")

            body_bytes = body_file.read_bytes()[:max_bytes] if body_file.exists() else b""
            return {
                "ok": 200 <= status_code < 400,
                "url": effective_url,
                "status_code": status_code,
                "headers": parsed_headers,
                "content_type": content_type,
                "body_bytes": body_bytes,
            }

    async def _tool_tools_list(self, arguments: dict[str, Any]) -> dict[str, Any]:
        include_parameters = bool(arguments.get("include_parameters", False))
        entries: list[dict[str, Any]] = []
        for spec in sorted(self._tools.values(), key=lambda item: item.name):
            entry = {
                "name": spec.name,
                "openai_name": self.to_openai_function_name(spec.name),
                "description": spec.description,
                "group": spec.group,
                "label": spec.label,
                "source": spec.source,
                "dynamic": spec.name in self._dynamic_tool_names,
            }
            if include_parameters:
                entry["parameters"] = spec.parameters
            entries.append(entry)
        return {
            "count": len(entries),
            "dynamic_count": len(self._dynamic_tool_names),
            "tools": entries,
        }

    async def _tool_tools_create(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.dynamic_tools_enabled:
            raise ToolError("dynamic tools are disabled by configuration")

        name = str(arguments.get("name", "")).strip()
        description = str(arguments.get("description", "")).strip()
        parameters = arguments.get("parameters")
        code = str(arguments.get("code", ""))
        group = str(arguments.get("group", "custom")).strip() or "custom"
        label = str(arguments.get("label", "")).strip() or name
        persist = bool(arguments.get("persist", True))

        spec = self._register_dynamic_tool(
            name=name,
            description=description,
            parameters=parameters,
            code=code,
            group=group,
            label=label,
        )

        persisted_path: str | None = None
        if persist:
            path = self._persist_dynamic_tool(
                name=spec.name,
                description=spec.description,
                parameters=spec.parameters,
                code=code,
                group=spec.group,
                label=spec.label,
            )
            persisted_path = str(path)

        return {
            "ok": True,
            "name": spec.name,
            "openai_name": self.to_openai_function_name(spec.name),
            "group": spec.group,
            "label": spec.label,
            "source": spec.source,
            "persisted": persist,
            "persisted_path": persisted_path,
        }

    async def _tool_memory_record(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not callable(self.memory_recorder):
            raise ToolError("memory recorder is not configured for this runtime")

        text = str(arguments.get("text", "")).strip()
        if not text:
            raise ToolError("text is required")

        metadata_raw = arguments.get("metadata")
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        result = await asyncio.to_thread(
            self.memory_recorder,
            session_key=str(arguments.get("session_key", "")).strip() or "main",
            run_id=str(arguments.get("run_id", "")).strip(),
            kind=str(arguments.get("kind", "")).strip() or "note",
            title=str(arguments.get("title", "")).strip(),
            text=text,
            metadata=metadata,
        )
        return {
            "ok": True,
            "artifact": result,
        }

    async def _tool_memory_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not callable(self.memory_searcher):
            raise ToolError("memory search is not configured for this runtime")

        kinds_raw = arguments.get("kinds")
        kinds = [str(item).strip() for item in kinds_raw if str(item).strip()] if isinstance(kinds_raw, list) else None
        limit = int(arguments.get("limit", 20))
        limit = max(1, min(limit, 200))
        items = await asyncio.to_thread(
            self.memory_searcher,
            query=str(arguments.get("query", "")).strip(),
            session_key=str(arguments.get("session_key", "")).strip() or None,
            kinds=kinds,
            limit=limit,
        )
        return {
            "ok": True,
            "count": len(items),
            "items": items,
        }

    async def _tool_memory_recent(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not callable(self.memory_recent):
            raise ToolError("memory recent is not configured for this runtime")

        limit = int(arguments.get("limit", 20))
        limit = max(1, min(limit, 200))
        items = await asyncio.to_thread(
            self.memory_recent,
            session_key=str(arguments.get("session_key", "")).strip() or None,
            limit=limit,
        )
        return {
            "ok": True,
            "count": len(items),
            "items": items,
        }

    async def _tool_packages_install(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.package_install_enabled:
            raise ToolError("package installation is disabled by configuration")

        raw_packages = arguments.get("packages")
        package_values = raw_packages if isinstance(raw_packages, list) else []
        packages: list[str] = []
        for value in package_values:
            package_name = str(value).strip()
            if package_name:
                packages.append(package_name)
        if not packages:
            raise ToolError("packages must include at least one package name")

        timeout = float(arguments.get("timeout_seconds", self.package_install_timeout_seconds))
        timeout = max(1.0, timeout)
        upgrade = bool(arguments.get("upgrade", False))
        pre = bool(arguments.get("pre", False))
        index_url = str(arguments.get("index_url", "")).strip()
        extra_index_url = str(arguments.get("extra_index_url", "")).strip()

        cmd: list[str] = [sys.executable, "-m", "pip", "install"]
        if upgrade:
            cmd.append("--upgrade")
        if pre:
            cmd.append("--pre")
        if index_url:
            cmd.extend(["--index-url", index_url])
        if extra_index_url:
            cmd.extend(["--extra-index-url", extra_index_url])
        cmd.extend(packages)

        def _run() -> dict[str, Any]:
            completed = subprocess.run(
                cmd,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return {
                "ok": completed.returncode == 0,
                "cmd": cmd,
                "packages": packages,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-16000:],
                "stderr": completed.stderr[-16000:],
            }

        try:
            return await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired as exc:
            raise ToolError(f"pip install timed out after {timeout:.1f}s") from exc

    def _require_vault(self) -> EncryptedVault:
        if not self.vault_enabled:
            raise ToolError("vault is disabled by configuration")
        if not self.vault_passphrase:
            raise ToolError("vault is not configured. Set REPLICA_VAULT_PASSPHRASE")
        if self._vault is None:
            self._vault = EncryptedVault(path=self.vault_file, passphrase=self.vault_passphrase)
        return self._vault

    def _tenant_fallback_vault(self) -> EncryptedVault | None:
        if not self.vault_enabled or not self.vault_passphrase:
            return None
        try:
            tenant_dir = self.vault_file.parents[1]
        except IndexError:
            return None
        tenant_vault_file = tenant_dir / self.vault_file.name
        if tenant_vault_file == self.vault_file:
            return None
        return EncryptedVault(path=tenant_vault_file, passphrase=self.vault_passphrase)

    async def _tool_vault_list(self, arguments: dict[str, Any]) -> dict[str, Any]:
        vault = self._require_vault()
        prefix = str(arguments.get("prefix", "")).strip() or None
        limit = int(arguments.get("limit", 200))
        keys = await asyncio.to_thread(vault.list_keys, prefix, limit)
        return {
            "count": len(keys),
            "keys": keys,
            "vaultFile": str(self.vault_file),
        }

    async def _tool_vault_set(self, arguments: dict[str, Any]) -> dict[str, Any]:
        vault = self._require_vault()
        key = str(arguments.get("key", "")).strip()
        if not key:
            raise ToolError("key is required")
        if "value" not in arguments:
            raise ToolError("value is required")
        value = arguments.get("value")
        overwrite = bool(arguments.get("overwrite", True))

        result = await asyncio.to_thread(vault.set, key, value, overwrite)
        return {
            "ok": True,
            **result,
            "stored": True,
        }

    async def _tool_vault_get(self, arguments: dict[str, Any]) -> dict[str, Any]:
        vault = self._require_vault()
        key = str(arguments.get("key", "")).strip()
        if not key:
            raise ToolError("key is required")
        return await asyncio.to_thread(vault.get, key)

    async def _tool_vault_delete(self, arguments: dict[str, Any]) -> dict[str, Any]:
        vault = self._require_vault()
        key = str(arguments.get("key", "")).strip()
        if not key:
            raise ToolError("key is required")
        return await asyncio.to_thread(vault.delete, key)

    async def _tool_files_read(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path_raw = str(arguments.get("path", "")).strip()
        if not path_raw:
            raise ToolError("path is required")
        max_chars = int(arguments.get("max_chars", 20000))
        path = self._resolve_workspace_path(path_raw)
        if not path.exists() or not path.is_file():
            raise ToolError(f"file not found: {path}")
        content = path.read_text(encoding="utf-8")
        content, truncated = self._limit_text(content, max_chars)
        return {
            "path": str(path),
            "truncated": truncated,
            "content": content,
        }

    async def _tool_files_write(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path_raw = str(arguments.get("path", "")).strip()
        if not path_raw:
            raise ToolError("path is required")
        content = arguments.get("content")
        if not isinstance(content, str):
            raise ToolError("content must be a string")
        append = bool(arguments.get("append", False))
        path = self._resolve_workspace_path(path_raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as handle:
            handle.write(content)
        return {
            "path": str(path),
            "bytes": len(content.encode("utf-8")),
            "append": append,
        }

    async def _tool_files_list(self, arguments: dict[str, Any]) -> dict[str, Any]:
        path_raw = str(arguments.get("path", ".")).strip() or "."
        max_entries = int(arguments.get("max_entries", 200))
        path = self._resolve_workspace_path(path_raw)
        if not path.exists() or not path.is_dir():
            raise ToolError(f"directory not found: {path}")
        entries: list[dict[str, Any]] = []
        for index, child in enumerate(sorted(path.iterdir(), key=lambda item: item.name.lower())):
            if index >= max_entries:
                break
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "type": "dir" if child.is_dir() else "file",
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return {
            "path": str(path),
            "entries": entries,
            "count": len(entries),
        }

    async def _tool_files_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        pattern = str(arguments.get("pattern", "")).strip()
        if not pattern:
            raise ToolError("pattern is required")

        path_raw = str(arguments.get("path", ".")).strip() or "."
        max_results = int(arguments.get("max_results", 200))
        search_root = self._resolve_workspace_path(path_raw)
        if not search_root.exists():
            raise ToolError(f"search path not found: {search_root}")

        rg_bin = shutil.which("rg")
        if rg_bin:
            cmd = [
                rg_bin,
                "-n",
                "--no-heading",
                "--color",
                "never",
                "--max-count",
                str(max_results),
                pattern,
                str(search_root),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            lines = [line for line in stdout.splitlines() if line.strip()]
            return {
                "path": str(search_root),
                "engine": "rg",
                "exit_code": proc.returncode,
                "matches": lines[:max_results],
                "stderr": stderr,
            }

        try:
            regex = re.compile(pattern)
            use_regex = True
        except re.error:
            regex = None
            use_regex = False

        matches: list[str] = []
        scanned = 0
        for file_path in search_root.rglob("*"):
            if len(matches) >= max_results:
                break
            if not file_path.is_file():
                continue
            scanned += 1
            if scanned > 3000:
                break
            try:
                if file_path.stat().st_size > 2_000_000:
                    continue
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                ok = bool(regex.search(line)) if use_regex and regex else (pattern in line)
                if ok:
                    matches.append(f"{file_path}:{idx}:{line}")
                    if len(matches) >= max_results:
                        break

        return {
            "path": str(search_root),
            "engine": "python-fallback",
            "matches": matches,
            "count": len(matches),
            "scanned_files": scanned,
        }

    async def _tool_shell_run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.shell_enabled:
            raise ToolError("shell tool is disabled by configuration")
        cmd = str(arguments.get("cmd", "")).strip()
        if not cmd:
            raise ToolError("cmd is required")

        timeout = float(arguments.get("timeout_seconds", self.shell_timeout_seconds))
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=str(self.workspace_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ToolError(f"command timed out after {timeout:.1f}s")

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        return {
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout": stdout[-12000:],
            "stderr": stderr[-12000:],
        }

    async def _tool_code_python(self, arguments: dict[str, Any]) -> dict[str, Any]:
        code = str(arguments.get("code", "")).strip()
        if not code:
            raise ToolError("code is required")
        timeout = float(arguments.get("timeout_seconds", self.shell_timeout_seconds))
        python_bin = str(arguments.get("python_bin", "python3")).strip() or "python3"

        proc = await asyncio.create_subprocess_exec(
            python_bin,
            "-c",
            code,
            cwd=str(self.workspace_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ToolError(f"python execution timed out after {timeout:.1f}s")

        return {
            "python_bin": python_bin,
            "exit_code": proc.returncode,
            "stdout": stdout_bytes.decode("utf-8", errors="replace")[-12000:],
            "stderr": stderr_bytes.decode("utf-8", errors="replace")[-12000:],
        }

    async def _tool_docker_run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.docker_enabled:
            raise ToolError("docker tool is disabled by configuration")
        if not shutil.which("docker"):
            raise ToolError("docker binary is not available in PATH")

        image = str(arguments.get("image", "")).strip()
        cmd = str(arguments.get("cmd", "")).strip()
        if not image or not cmd:
            raise ToolError("image and cmd are required")

        mount_workspace = bool(arguments.get("mount_workspace", True))
        timeout = float(arguments.get("timeout_seconds", self.docker_timeout_seconds))

        docker_cmd = ["docker", "run", "--rm"]
        if mount_workspace:
            docker_cmd.extend(["-v", f"{self.workspace_root}:/workspace", "-w", "/workspace"])
        docker_cmd.extend([image, "sh", "-lc", cmd])

        def _run() -> dict[str, Any]:
            completed = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return {
                "cmd": docker_cmd,
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-12000:],
                "stderr": completed.stderr[-12000:],
            }

        try:
            return await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired as exc:
            raise ToolError(f"docker command timed out after {timeout:.1f}s") from exc

    async def _tool_web_fetch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        url = str(arguments.get("url", "")).strip()
        if not url:
            raise ToolError("url is required")
        if not self._is_url(url):
            raise ToolError("url must use http or https")

        timeout = float(arguments.get("timeout_seconds", 20))
        max_chars = int(arguments.get("max_chars", 40000))
        max_bytes = max(4096, max_chars * 4)
        verify_ssl = bool(arguments.get("verify_ssl", True))
        prefer_curl = bool(arguments.get("prefer_curl", True))

        raw_headers = arguments.get("headers")
        headers: dict[str, str] = {}
        if isinstance(raw_headers, dict):
            for key, value in raw_headers.items():
                k = str(key).strip()
                v = str(value).strip()
                if k and v:
                    headers[k] = v

        payload = await asyncio.to_thread(
            self._http_get,
            url,
            headers,
            timeout,
            max_bytes,
            verify_ssl=verify_ssl,
            prefer_curl=prefer_curl,
        )
        body_bytes = payload.pop("body_bytes", b"")
        text = body_bytes.decode("utf-8", errors="replace")
        text, truncated = self._limit_text(text, max_chars)
        payload["body"] = text
        payload["truncated"] = truncated
        return payload

    async def _tool_web_request(self, arguments: dict[str, Any]) -> dict[str, Any]:
        url = str(arguments.get("url", "")).strip()
        if not url:
            raise ToolError("url is required")
        if not self._is_url(url):
            raise ToolError("url must use http or https")

        method = str(arguments.get("method", "GET")).strip().upper() or "GET"
        if not re.fullmatch(r"[A-Z]+", method):
            raise ToolError("method must contain only letters")

        timeout = float(arguments.get("timeout_seconds", 30))
        max_chars = int(arguments.get("max_chars", 40000))
        max_bytes = max(4096, max_chars * 4)
        verify_ssl = bool(arguments.get("verify_ssl", True))
        prefer_curl = bool(arguments.get("prefer_curl", True))
        follow_redirects = bool(arguments.get("follow_redirects", True))

        headers = self._normalize_headers(arguments.get("headers"))
        raw_query = arguments.get("query")
        query = self._normalize_headers(raw_query) if isinstance(raw_query, dict) else None

        has_json = "json" in arguments and arguments.get("json") is not None
        has_body = "body" in arguments and arguments.get("body") is not None
        if has_json and has_body:
            raise ToolError("provide either json or body, not both")

        body_bytes: bytes | None = None
        if has_json:
            body_bytes = json.dumps(arguments.get("json"), ensure_ascii=False).encode("utf-8")
            if not self._has_header(headers, "content-type"):
                headers["Content-Type"] = "application/json"
        elif has_body:
            body_bytes = str(arguments.get("body", "")).encode("utf-8")

        payload = await asyncio.to_thread(
            self._http_request,
            url=url,
            method=method,
            headers=headers,
            timeout=timeout,
            max_bytes=max_bytes,
            query=query,
            body_bytes=body_bytes,
            verify_ssl=verify_ssl,
            prefer_curl=prefer_curl,
            follow_redirects=follow_redirects,
        )
        body = payload.pop("body_bytes", b"")
        text = body.decode("utf-8", errors="replace")
        text, truncated = self._limit_text(text, max_chars)
        payload["body"] = text
        payload["truncated"] = truncated

        content_type = str(payload.get("content_type", "")).lower()
        if "application/json" in content_type:
            try:
                payload["json"] = json.loads(text)
            except Exception:
                pass

        return payload

    async def _tool_api_run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        connection_name = str(
            arguments.get("connection")
            or arguments.get("integration")
            or arguments.get("integration_slug")
            or ""
        ).strip().lower()
        if not connection_name:
            raise ToolError("connection or integration slug is required")

        connection = await self._resolve_api_connection(connection_name)
        if not isinstance(connection, dict):
            raise ToolError(f"api connection/integration not found: {connection_name}")
        if bool(connection.get("missingCredential")):
            reason = str(connection.get("missingCredentialReason", "") or "").strip().lower()
            if reason == "user_credentials_required":
                raise ToolError(f"user-scoped integration '{connection_name}' is not configured for the initiating user")
            raise ToolError(f"api connection/integration is not ready: {connection_name}")

        method = str(arguments.get("method", "GET")).strip().upper() or "GET"
        if not re.fullmatch(r"[A-Z]+", method):
            raise ToolError("method must contain only letters")
        endpoint = str(arguments.get("endpoint", "")).strip()
        protocol = str(connection.get("protocol", "rest")).strip().lower() or "rest"
        if protocol not in {"rest", "graphql", "soap"}:
            raise ToolError(f"unsupported protocol: {protocol}")
        connection_source = str(connection.get("source", "api_connection") or "api_connection").strip().lower()
        if connection_source == "internal_api" and endpoint:
            endpoint = self._normalize_moio_endpoint_path(endpoint)

        base_url = str(connection.get("baseUrl", "")).strip()
        if not base_url:
            raise ToolError(f"api connection has no baseUrl: {connection_name}")
        if protocol == "graphql" and not endpoint:
            endpoint = "/graphql"
        if protocol == "soap" and not endpoint:
            endpoint = "/"
        url = urllib.parse.urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/")) if endpoint else base_url
        if not self._is_url(url):
            raise ToolError("resolved API URL must use http or https")

        timeout = float(arguments.get("timeout_seconds", connection.get("timeoutSeconds", 30.0) or 30.0))
        timeout = max(1.0, min(timeout, 300.0))
        max_chars = int(arguments.get("max_chars", 40000))
        max_chars = max(200, min(max_chars, 200000))
        max_bytes = max(4096, max_chars * 4)
        follow_redirects = True

        headers = self._normalize_headers(connection.get("defaultHeaders"))
        override_headers = self._normalize_headers(arguments.get("headers"))
        headers.update(override_headers)
        query = self._normalize_query(arguments.get("params")) or {}
        payload = arguments.get("payload")
        body_payload: Any = payload
        body_bytes: bytes | None = None

        # For internal API calls, include tenant/workspace in query so schema/workspace
        # resolution survives intermediate redirects that may drop custom headers.
        if connection_source == "internal_api":
            tenant_hint = ""
            workspace_hint = ""
            for key, value in headers.items():
                normalized = str(key or "").strip().lower()
                if normalized == "x-tenant" and not tenant_hint:
                    tenant_hint = str(value or "").strip()
                if normalized == "x-workspace" and not workspace_hint:
                    workspace_hint = str(value or "").strip()
            if tenant_hint and "tenant" not in query and "tenantId" not in query:
                query["tenant"] = tenant_hint
            if workspace_hint and "workspace" not in query and "workspaceId" not in query:
                query["workspace"] = workspace_hint

        auth_type = str(connection.get("authType", "none")).strip().lower() or "none"
        await self._apply_connection_auth(
            auth_type=auth_type,
            connection=connection,
            headers=headers,
            query=query,
        )

        if protocol == "graphql":
            graphql_query = str(arguments.get("graphql_query", "")).strip()
            if not graphql_query and isinstance(payload, dict):
                graphql_query = str(payload.get("query", "")).strip()
            if not graphql_query:
                raise ToolError("graphql_query is required for graphql protocol")
            graphql_variables = arguments.get("graphql_variables")
            if graphql_variables is None and isinstance(payload, dict) and isinstance(payload.get("variables"), dict):
                graphql_variables = payload.get("variables")
            if graphql_variables is not None and not isinstance(graphql_variables, dict):
                raise ToolError("graphql_variables must be an object")
            method = "POST"
            body_payload = {"query": graphql_query}
            if isinstance(graphql_variables, dict):
                body_payload["variables"] = graphql_variables
            if not self._has_header(headers, "content-type"):
                headers["Content-Type"] = "application/json"
        elif protocol == "soap":
            soap_xml = str(arguments.get("soap_xml", "")).strip()
            if not soap_xml and isinstance(payload, str):
                soap_xml = payload.strip()
            if not soap_xml:
                raise ToolError("soap_xml is required for soap protocol")
            soap_action = str(arguments.get("soap_action", "")).strip()
            method = "POST"
            body_payload = soap_xml
            if soap_action and not self._has_header(headers, "soapaction"):
                headers["SOAPAction"] = soap_action
            if not self._has_header(headers, "content-type"):
                headers["Content-Type"] = "text/xml; charset=utf-8"

        if body_payload is not None:
            if isinstance(body_payload, bytes):
                body_bytes = body_payload
            elif isinstance(body_payload, str):
                body_bytes = body_payload.encode("utf-8")
            else:
                body_bytes = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
                if not self._has_header(headers, "content-type"):
                    headers["Content-Type"] = "application/json"

        raw = await asyncio.to_thread(
            self._http_request,
            url=url,
            method=method,
            headers=headers,
            timeout=timeout,
            max_bytes=max_bytes,
            query=query,
            body_bytes=body_bytes,
            verify_ssl=True,
            prefer_curl=True,
            follow_redirects=follow_redirects,
        )
        body_bytes_out = raw.pop("body_bytes", b"")
        body_text = body_bytes_out.decode("utf-8", errors="replace")
        body_text, body_truncated = self._limit_text(body_text, max_chars)

        content_type = str(raw.get("content_type", "")).lower()
        parsed_json: Any | None = None
        if "application/json" in content_type or body_text.lstrip().startswith(("{", "[")):
            try:
                parsed_json = json.loads(body_text)
            except Exception:
                parsed_json = None

        extract_fields_raw = arguments.get("extract_fields")
        extract_fields = [str(item).strip() for item in extract_fields_raw if str(item).strip()] if isinstance(extract_fields_raw, list) else []
        truncate_lists = bool(arguments.get("truncate_lists", True))
        max_items_per_list = int(arguments.get("max_items_per_list", 30))
        max_items_per_list = max(1, min(max_items_per_list, 5000))
        summarize = bool(arguments.get("summarize", False))

        preview: Any
        preview_truncated = body_truncated
        preview_info = ""
        summary = ""
        if isinstance(parsed_json, (dict, list)):
            preview, preview_truncated, preview_info = self._process_api_response_data(
                parsed_json,
                extract_fields=extract_fields,
                truncate_lists=truncate_lists,
                max_items_per_list=max_items_per_list,
                max_chars=max_chars,
            )
            if summarize:
                summary = self._summarize_api_data(preview)
        else:
            status_code = int(raw.get("status_code", 0) or 0)
            if status_code >= 400 and connection_source == "internal_api" and "text/html" in content_type:
                preview = self._summarize_internal_html_error(
                    body_text=body_text,
                    request_url=str(raw.get("url", url)),
                    endpoint=endpoint or "/",
                    method=method,
                    status_code=status_code,
                )
                preview_truncated = False
                preview_info = "html error condensed for internal API"
            else:
                preview = body_text
                if preview_truncated:
                    preview_info = "body text truncated by max_chars"

        return {
            "ok": bool(raw.get("ok", False)),
            "connection": connection_name,
            "source": str(connection.get("source", "api_connection")),
            "protocol": protocol,
            "request": {
                "method": method,
                "endpoint": endpoint or "/",
                "url": str(raw.get("url", url)),
            },
            "auth_type": auth_type,
            "status_code": int(raw.get("status_code", 0) or 0),
            "content_type": raw.get("content_type", ""),
            "headers": raw.get("headers", {}),
            "data_preview": preview,
            "summary": summary,
            "truncated": bool(preview_truncated),
            "truncated_info": preview_info,
            "error": raw.get("error"),
        }

    async def _tool_moio_api_run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        endpoint_raw = str(arguments.get("endpoint", "") or "").strip()
        if not endpoint_raw:
            raise ToolError("endpoint is required")
        method = str(arguments.get("method", "GET") or "GET").strip().upper() or "GET"
        if not re.fullmatch(r"[A-Z]+", method):
            raise ToolError("method must contain only letters")

        endpoint_path = self._normalize_moio_endpoint_path(endpoint_raw)
        path_only, _, query_string = endpoint_path.partition("?")

        params = self._normalize_query(arguments.get("params")) or {}
        if query_string:
            for key, value in urllib.parse.parse_qsl(query_string, keep_blank_values=True):
                normalized_key = str(key or "").strip()
                if not normalized_key or normalized_key in params:
                    continue
                params[normalized_key] = str(value or "")

        include_contract = bool(arguments.get("include_contract", True))
        strict_contract = bool(arguments.get("strict_contract", False))
        canonicalize_endpoint = bool(arguments.get("canonicalize_endpoint", True))
        endpoint_contract: dict[str, Any] | None = None
        if include_contract or strict_contract or canonicalize_endpoint:
            endpoint_contract = await self._lookup_moio_endpoint_contract(
                endpoint_path=path_only,
                method=method,
            )
            if strict_contract and endpoint_contract is None:
                raise ToolError(f"endpoint contract was not found in /api/v1/meta/endpoints/ for {method} {path_only}")

        resolved_path = path_only
        contract_path = str((endpoint_contract or {}).get("path", "") or "").strip()
        if canonicalize_endpoint and contract_path:
            resolved_path = contract_path
            if query_string:
                query_bits = urllib.parse.parse_qsl(query_string, keep_blank_values=True)
                merged_qs = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(resolved_path).query, keep_blank_values=True))
                for q_key, q_value in query_bits:
                    key = str(q_key or "").strip()
                    if not key or key in merged_qs:
                        continue
                    merged_qs[key] = str(q_value or "")
                base_path = urllib.parse.urlsplit(resolved_path).path or resolved_path
                if merged_qs:
                    resolved_path = f"{base_path}?{urllib.parse.urlencode(merged_qs)}"
                else:
                    resolved_path = base_path

        resolved_path_only, _, resolved_query = resolved_path.partition("?")
        if resolved_query:
            for key, value in urllib.parse.parse_qsl(resolved_query, keep_blank_values=True):
                normalized_key = str(key or "").strip()
                if not normalized_key or normalized_key in params:
                    continue
                params[normalized_key] = str(value or "")

        forwarded: dict[str, Any] = {
            "connection": "moio_internal",
            "endpoint": resolved_path_only,
            "method": method,
            "params": params,
        }
        for key in (
            "payload",
            "headers",
            "timeout_seconds",
            "max_chars",
            "extract_fields",
            "truncate_lists",
            "max_items_per_list",
            "summarize",
        ):
            if key not in arguments:
                continue
            value = arguments.get(key)
            if value is None:
                continue
            forwarded[key] = value
        api_result = await self._tool_api_run(forwarded)

        if not include_contract:
            endpoint_contract = None

        return {
            "ok": bool(api_result.get("ok", False)),
            "tool": "moio_api.run",
            "priority": "high",
            "connection": "moio_internal",
            "auth_type": "initiator_bearer",
            "request": {
                "method": method,
                "requested_endpoint": path_only,
                "endpoint": resolved_path_only,
                "params": params,
            },
            "endpoint_contract": endpoint_contract,
            "response": api_result,
        }

    @staticmethod
    def _normalize_moio_endpoint_path(raw_endpoint: str) -> str:
        text = str(raw_endpoint or "").strip()
        if not text:
            raise ToolError("endpoint is required")
        if text.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(text)
            path = str(parsed.path or "/").strip() or "/"
            if not path.startswith("/"):
                path = f"/{path}"
            path = ToolRegistry._resolve_moio_endpoint_alias(path)
            if parsed.query:
                return f"{path}?{parsed.query}"
            return path
        if not text.startswith("/"):
            text = f"/{text}"
        path_only, _, query = text.partition("?")
        path_only = ToolRegistry._resolve_moio_endpoint_alias(path_only)
        if query:
            return f"{path_only}?{query}"
        return path_only

    @classmethod
    def _resolve_moio_endpoint_alias(cls, path: str) -> str:
        normalized = str(path or "").strip()
        if not normalized:
            return "/"
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        key = normalized.strip("/").lower()
        mapped = cls._MOIO_ENDPOINT_ALIASES.get(key)
        if mapped:
            return mapped
        return normalized

    @staticmethod
    def _summarize_internal_html_error(
        *,
        body_text: str,
        request_url: str,
        endpoint: str,
        method: str,
        status_code: int,
    ) -> dict[str, Any]:
        title_match = re.search(r"<title>([^<]+)</title>", body_text, flags=re.IGNORECASE)
        page_title = str(title_match.group(1)).strip() if title_match else ""
        current_path_match = re.search(r"current path,\s*<code>([^<]+)</code>", body_text, flags=re.IGNORECASE)
        current_path = str(current_path_match.group(1)).strip() if current_path_match else str(endpoint or "/")
        suggested_endpoints = [
            "/api/v1/meta/endpoints/",
            "/api/v1/crm/meta/endpoints/",
            "/api/v1/integrations/meta/endpoints/",
        ]
        if str(current_path).strip("/").lower() in {"chatui/endpoints", "chatui/endpoints/"}:
            current_path = "/api/v1/meta/endpoints/"
        return {
            "errorType": "internal_route_not_found",
            "statusCode": int(status_code),
            "title": page_title or f"HTTP {status_code}",
            "message": "Internal route not found in Moio API.",
            "request": {
                "method": method,
                "endpoint": endpoint,
                "url": request_url,
            },
            "normalizedEndpoint": current_path if current_path.startswith("/") else f"/{current_path}",
            "suggestedEndpoints": suggested_endpoints,
            "hint": "Use moio_api.run with endpoint '/api/v1/meta/endpoints/' to discover canonical routes.",
        }

    @staticmethod
    def _endpoint_search_terms(path: str) -> str:
        uuid_re = re.compile(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
        )
        parts = [part for part in str(path or "").split("/") if part]
        filtered: list[str] = []
        for part in parts:
            token = str(part).strip()
            if not token:
                continue
            if token.isdigit():
                continue
            if uuid_re.fullmatch(token):
                continue
            filtered.append(token)
        return " ".join(filtered).strip()

    async def _lookup_moio_endpoint_contract(self, *, endpoint_path: str, method: str) -> dict[str, Any] | None:
        path_value = str(endpoint_path or "").strip()
        if not path_value.startswith("/"):
            path_value = f"/{path_value}"
        params: dict[str, str] = {"method": method, "limit": "200", "path": path_value.rstrip("/") or "/"}
        if path_value.startswith("/api/v1/crm/"):
            params["module"] = "crm"
        elif path_value.startswith("/api/v1/integrations/"):
            params["module"] = "integrations"
        terms = self._endpoint_search_terms(endpoint_path)
        if terms:
            params["q"] = terms
        lookup = await self._tool_api_run(
            {
                "connection": "moio_internal",
                "endpoint": "/api/v1/meta/endpoints/",
                "method": "GET",
                "params": params,
                "max_chars": 120000,
                "truncate_lists": True,
                "max_items_per_list": 200,
            }
        )
        payload = lookup.get("data_preview")
        if not isinstance(payload, dict):
            return None
        endpoints = payload.get("endpoints")
        if not isinstance(endpoints, list):
            return None
        best = self._select_best_endpoint_contract(
            [entry for entry in endpoints if isinstance(entry, dict)],
            endpoint_path=endpoint_path,
            method=method,
        )
        return dict(best) if isinstance(best, dict) else None

    @staticmethod
    def _select_best_endpoint_contract(
        endpoints: list[dict[str, Any]],
        *,
        endpoint_path: str,
        method: str,
    ) -> dict[str, Any] | None:
        if not endpoints:
            return None
        normalized_target_path = endpoint_path.rstrip("/") or "/"
        target_parts = [part for part in endpoint_path.strip("/").split("/") if part]
        best_row: dict[str, Any] | None = None
        best_score = -10**9
        for row in endpoints:
            row_method = str(row.get("method", "") or "").strip().upper()
            row_path = str(row.get("path", "") or "").strip()
            if not row_path:
                continue
            normalized_row_path = row_path.rstrip("/") or "/"
            score = 0
            if row_method == method:
                score += 100
            if normalized_row_path == normalized_target_path:
                score += 500
            row_parts = [part for part in row_path.strip("/").split("/") if part]
            for idx, part in enumerate(target_parts):
                if idx >= len(row_parts):
                    break
                row_part = row_parts[idx]
                if row_part == part:
                    score += 12
                elif row_part.startswith("{") and row_part.endswith("}"):
                    score += 6
            if normalized_row_path.startswith(normalized_target_path.rstrip("/") + "/"):
                score += 8
            if score > best_score:
                best_score = score
                best_row = row
        return best_row

    async def _resolve_api_connection(self, connection_name: str) -> dict[str, Any] | None:
        if not callable(self.api_connection_resolver):
            raise ToolError("api connections are not configured for this runtime")
        initiator = self._current_initiator()
        if self._api_connection_resolver_accepts_initiator:
            return await asyncio.to_thread(self.api_connection_resolver, connection_name, initiator=initiator)
        return await asyncio.to_thread(self.api_connection_resolver, connection_name)

    @staticmethod
    def _normalize_query(raw_query: Any) -> dict[str, str] | None:
        if not isinstance(raw_query, dict):
            return None
        query: dict[str, str] = {}
        for key, value in raw_query.items():
            k = str(key).strip()
            if not k:
                continue
            if isinstance(value, (dict, list)):
                query[k] = json.dumps(value, ensure_ascii=False)
            else:
                query[k] = str(value)
        return query

    async def _apply_connection_auth(
        self,
        *,
        auth_type: str,
        connection: dict[str, Any],
        headers: dict[str, str],
        query: dict[str, str],
    ) -> None:
        if auth_type == "none":
            return
        if auth_type == "initiator_bearer":
            token = self._initiator_access_token()
            headers["Authorization"] = f"Bearer {token}"
            return
        if auth_type == "bearer":
            token = await self._vault_secret(connection.get("vaultKey"))
            headers["Authorization"] = f"Bearer {token}"
            return
        if auth_type == "api_key_header":
            token = await self._vault_secret(connection.get("vaultKey"))
            header_name = str(connection.get("apiKeyHeaderName", "X-API-Key")).strip() or "X-API-Key"
            headers[header_name] = token
            return
        if auth_type == "api_key_query":
            token = await self._vault_secret(connection.get("vaultKey"))
            param = str(connection.get("apiKeyQueryParamName", "api_key")).strip() or "api_key"
            query[param] = token
            return
        if auth_type == "basic":
            username = await self._vault_secret(connection.get("usernameVaultKey"))
            password = await self._vault_secret(connection.get("passwordVaultKey"))
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
            return
        if auth_type == "oauth2_client_credentials":
            token_type, access_token = await self._oauth2_client_credentials(connection)
            headers["Authorization"] = f"{token_type} {access_token}"
            return
        raise ToolError(f"unsupported auth type: {auth_type}")

    async def _oauth2_client_credentials(self, connection: dict[str, Any]) -> tuple[str, str]:
        token_url = str(connection.get("tokenUrl", "")).strip()
        if not token_url:
            raise ToolError("tokenUrl is required for oauth2_client_credentials")
        if not self._is_url(token_url):
            base_url = str(connection.get("baseUrl", "")).strip()
            if base_url:
                token_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", token_url.lstrip("/"))
        if not self._is_url(token_url):
            raise ToolError("tokenUrl must use http or https")

        client_id = await self._vault_secret(connection.get("clientIdVaultKey"))
        client_secret = await self._vault_secret(connection.get("clientSecretVaultKey"))
        scope = str(connection.get("scope", "")).strip()

        cache_key = hashlib.sha1(
            f"{token_url}|{client_id}|{scope}".encode("utf-8"),
        ).hexdigest()
        now = time.time()
        cached = self._oauth_tokens.get(cache_key)
        if isinstance(cached, dict):
            access_token = str(cached.get("access_token", "")).strip()
            token_type = str(cached.get("token_type", "Bearer")).strip() or "Bearer"
            expires_at = float(cached.get("expires_at", 0.0) or 0.0)
            if access_token and now < max(0.0, expires_at - 30.0):
                return token_type, access_token

        form_payload: dict[str, str] = {"grant_type": "client_credentials"}
        if scope:
            form_payload["scope"] = scope

        basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        response = await asyncio.to_thread(
            self._http_request,
            url=token_url,
            method="POST",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=30.0,
            max_bytes=200000,
            query=None,
            body_bytes=urllib.parse.urlencode(form_payload).encode("utf-8"),
            verify_ssl=True,
            prefer_curl=True,
            follow_redirects=True,
        )

        status_code = int(response.get("status_code", 0) or 0)
        body_text = response.pop("body_bytes", b"").decode("utf-8", errors="replace")
        if status_code < 200 or status_code >= 300:
            snippet = body_text.strip()[:500] if body_text else str(response.get("error", ""))
            raise ToolError(f"oauth token request failed ({status_code}): {snippet}")

        try:
            data = json.loads(body_text)
        except Exception as exc:
            raise ToolError("oauth token response is not valid JSON") from exc
        if not isinstance(data, dict):
            raise ToolError("oauth token response must be an object")

        access_token = str(data.get("access_token", "")).strip()
        if not access_token:
            raise ToolError("oauth token response missing access_token")
        token_type = str(data.get("token_type", "Bearer")).strip() or "Bearer"
        if token_type.lower() == "bearer":
            token_type = "Bearer"

        expires_in_raw = data.get("expires_in", 300)
        try:
            expires_in = float(expires_in_raw)
        except (TypeError, ValueError):
            expires_in = 300.0
        expires_in = max(60.0, min(expires_in, 604800.0))
        self._oauth_tokens[cache_key] = {
            "access_token": access_token,
            "token_type": token_type,
            "expires_at": now + expires_in,
        }
        return token_type, access_token

    async def _vault_secret(self, key_value: Any) -> str:
        key = str(key_value or "").strip()
        if not key:
            raise ToolError("missing vault key for API auth")
        vault = self._require_vault()
        record = await asyncio.to_thread(vault.get, key)
        if not isinstance(record, dict) or not record.get("found"):
            fallback = self._tenant_fallback_vault()
            if fallback is not None:
                record = await asyncio.to_thread(fallback.get, key)
        if not isinstance(record, dict) or not record.get("found"):
            raise ToolError(f"vault secret not found: {key}")
        value = record.get("value")
        if value is None:
            raise ToolError(f"vault secret is empty: {key}")
        return str(value)

    def _initiator_access_token(self) -> str:
        initiator = self._current_initiator()
        if not isinstance(initiator, dict):
            raise ToolError("initiating user access token is unavailable")
        for key in ("accessToken", "access_token", "bearerToken", "bearer_token"):
            value = str(initiator.get(key, "") or "").strip()
            if value:
                return value
        raise ToolError("initiating user access token is unavailable")

    def _process_api_response_data(
        self,
        value: Any,
        *,
        extract_fields: list[str],
        truncate_lists: bool,
        max_items_per_list: int,
        max_chars: int,
    ) -> tuple[Any, bool, str]:
        shaped = value
        if extract_fields:
            shaped = self._extract_fields_from_data(value, extract_fields)
        if truncate_lists:
            shaped, list_truncated = self._truncate_lists_in_data(shaped, max_items_per_list=max_items_per_list)
        else:
            list_truncated = False

        serialized = json.dumps(shaped, ensure_ascii=False, default=str, indent=2)
        hard_limit = max_chars * 4
        if len(serialized) <= hard_limit:
            return shaped, list_truncated, "lists truncated" if list_truncated else ""

        clipped = serialized[:hard_limit].rstrip() + "\n... (truncated by max_chars)"
        try:
            parsed = json.loads(clipped)
            return parsed, True, "payload truncated by max_chars"
        except Exception:
            return clipped, True, "payload truncated by max_chars"

    @staticmethod
    def _extract_fields_from_data(value: Any, fields: list[str]) -> Any:
        if not isinstance(value, dict):
            return value
        output: dict[str, Any] = {}
        for field in fields:
            parts = [part for part in field.split(".") if part]
            if not parts:
                continue
            current: Any = value
            valid = True
            for part in parts:
                if not isinstance(current, dict) or part not in current:
                    valid = False
                    break
                current = current[part]
            if not valid:
                continue
            target = output
            for part in parts[:-1]:
                child = target.get(part)
                if not isinstance(child, dict):
                    child = {}
                    target[part] = child
                target = child
            target[parts[-1]] = current
        return output if output else value

    @classmethod
    def _truncate_lists_in_data(cls, value: Any, *, max_items_per_list: int) -> tuple[Any, bool]:
        if isinstance(value, list):
            truncated_flag = len(value) > max_items_per_list
            items = value[:max_items_per_list]
            next_items: list[Any] = []
            child_truncated = False
            for item in items:
                shaped, child = cls._truncate_lists_in_data(item, max_items_per_list=max_items_per_list)
                next_items.append(shaped)
                child_truncated = child_truncated or child
            if truncated_flag:
                next_items.append(f"... {len(value) - max_items_per_list} more items")
            return next_items, truncated_flag or child_truncated
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            truncated = False
            for key, item in value.items():
                shaped, child = cls._truncate_lists_in_data(item, max_items_per_list=max_items_per_list)
                output[str(key)] = shaped
                truncated = truncated or child
            return output, truncated
        return value, False

    @staticmethod
    def _summarize_api_data(value: Any) -> str:
        if isinstance(value, dict):
            keys = list(value.keys())
            return f"object with {len(keys)} keys: {', '.join(keys[:12])}"
        if isinstance(value, list):
            return f"list with {len(value)} items"
        text = str(value)
        if len(text) > 240:
            text = text[:240] + "..."
        return f"text payload: {text}"

    async def _tool_web_extract(self, arguments: dict[str, Any]) -> dict[str, Any]:
        url = str(arguments.get("url", "")).strip()
        if not url:
            raise ToolError("url is required")
        if not self._is_url(url):
            raise ToolError("url must use http or https")

        timeout = float(arguments.get("timeout_seconds", 20))
        max_chars = int(arguments.get("max_chars", 50000))
        max_links = int(arguments.get("max_links", 100))
        verify_ssl = bool(arguments.get("verify_ssl", True))
        prefer_curl = bool(arguments.get("prefer_curl", True))

        payload = await asyncio.to_thread(
            self._http_get,
            url,
            {},
            timeout,
            max(4096, max_chars * 5),
            verify_ssl=verify_ssl,
            prefer_curl=prefer_curl,
        )
        body_bytes = payload.pop("body_bytes", b"")
        html_text = body_bytes.decode("utf-8", errors="replace")

        summary = self._extract_html_summary(html_text, payload.get("url", url), max_chars, max_links)
        return {
            **payload,
            **summary,
        }

    async def _tool_web_scrape(self, arguments: dict[str, Any]) -> dict[str, Any]:
        url = str(arguments.get("url", "")).strip()
        selector = str(arguments.get("selector", "")).strip()
        if not url or not selector:
            raise ToolError("url and selector are required")
        if not self._is_url(url):
            raise ToolError("url must use http or https")

        attr = str(arguments.get("attr", "")).strip() or None
        max_items = int(arguments.get("max_items", 100))
        timeout = float(arguments.get("timeout_seconds", 20))
        verify_ssl = bool(arguments.get("verify_ssl", True))
        prefer_curl = bool(arguments.get("prefer_curl", True))

        payload = await asyncio.to_thread(
            self._http_get,
            url,
            {},
            timeout,
            2_000_000,
            verify_ssl=verify_ssl,
            prefer_curl=prefer_curl,
        )
        body_bytes = payload.pop("body_bytes", b"")

        bs4 = _require_optional("bs4", "beautifulsoup4")
        soup = bs4.BeautifulSoup(body_bytes.decode("utf-8", errors="replace"), "html.parser")

        items: list[str] = []
        for node in soup.select(selector):
            value = node.get(attr) if attr else node.get_text(" ", strip=True)
            text = str(value).strip() if value is not None else ""
            if not text:
                continue
            items.append(text)
            if len(items) >= max_items:
                break

        return {
            **payload,
            "selector": selector,
            "attr": attr,
            "items": items,
            "count": len(items),
        }

    async def _tool_resource_read(self, arguments: dict[str, Any]) -> dict[str, Any]:
        target = str(arguments.get("target", "")).strip()
        if not target:
            raise ToolError("target is required")

        max_chars = int(arguments.get("max_chars", 50000))
        timeout = float(arguments.get("timeout_seconds", 20))
        verify_ssl = bool(arguments.get("verify_ssl", True))
        prefer_curl = bool(arguments.get("prefer_curl", True))

        if self._is_url(target):
            return await self._read_resource_url(
                target,
                max_chars=max_chars,
                timeout=timeout,
                verify_ssl=verify_ssl,
                prefer_curl=prefer_curl,
            )

        path = self._resolve_workspace_path(target)
        return await self._read_resource_file(
            path,
            max_chars=max_chars,
            sheet=str(arguments.get("sheet", "")).strip() or None,
            transcribe=bool(arguments.get("transcribe", False)),
            audio_model=str(arguments.get("audio_model", "gpt-4o-mini-transcribe")).strip() or "gpt-4o-mini-transcribe",
        )

    async def _read_resource_url(
        self,
        url: str,
        *,
        max_chars: int,
        timeout: float,
        verify_ssl: bool,
        prefer_curl: bool,
    ) -> dict[str, Any]:
        response = await asyncio.to_thread(
            self._http_get,
            url,
            {},
            timeout,
            max(4096, max_chars * 8),
            verify_ssl=verify_ssl,
            prefer_curl=prefer_curl,
        )
        body_bytes = response.pop("body_bytes", b"")
        content_type = str(response.get("content_type", "")).lower()

        if "text/html" in content_type:
            summary = self._extract_html_summary(
                body_bytes.decode("utf-8", errors="replace"),
                response.get("url", url),
                max_chars,
                100,
            )
            return {
                **response,
                "kind": "webpage",
                "text": summary["text"],
                "title": summary["title"],
                "links": summary["links"],
                "images": summary["images"],
                "truncated": summary["truncated"],
            }

        if "application/pdf" in content_type or url.lower().endswith(".pdf"):
            pypdf = _require_optional("pypdf", "pypdf")
            reader = pypdf.PdfReader(io.BytesIO(body_bytes))
            pages: list[str] = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            text = "\n\n".join(pages)
            text, truncated = self._limit_text(text, max_chars)
            return {
                **response,
                "kind": "pdf",
                "pages": len(reader.pages),
                "text": text,
                "truncated": truncated,
            }

        text = body_bytes.decode("utf-8", errors="replace")
        text, truncated = self._limit_text(text, max_chars)
        return {
            **response,
            "kind": "text",
            "text": text,
            "truncated": truncated,
        }

    async def _read_resource_file(
        self,
        path: Path,
        *,
        max_chars: int,
        sheet: str | None,
        transcribe: bool,
        audio_model: str,
    ) -> dict[str, Any]:
        if not path.exists() or not path.is_file():
            raise ToolError(f"file not found: {path}")

        suffix = path.suffix.lower()

        if suffix in {".txt", ".md", ".json", ".yaml", ".yml", ".xml", ".log", ".py", ".ts", ".js", ".tsx", ".jsx"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            text, truncated = self._limit_text(text, max_chars)
            return {
                "kind": "text",
                "path": str(path),
                "text": text,
                "truncated": truncated,
            }

        if suffix in {".html", ".htm"}:
            html_text = path.read_text(encoding="utf-8", errors="replace")
            summary = self._extract_html_summary(html_text, f"file://{path}", max_chars, 100)
            return {
                "kind": "html",
                "path": str(path),
                **summary,
            }

        if suffix in {".csv", ".tsv"}:
            delimiter = "\t" if suffix == ".tsv" else ","
            rows: list[list[str]] = []
            with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                for idx, row in enumerate(reader):
                    if idx >= 300:
                        break
                    rows.append([str(cell) for cell in row])
            text = "\n".join(delimiter.join(row) for row in rows)
            text, truncated = self._limit_text(text, max_chars)
            return {
                "kind": "csv",
                "path": str(path),
                "rows": rows,
                "text": text,
                "truncated": truncated,
            }

        if suffix == ".pdf":
            pypdf = _require_optional("pypdf", "pypdf")
            reader = pypdf.PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(pages)
            text, truncated = self._limit_text(text, max_chars)
            return {
                "kind": "pdf",
                "path": str(path),
                "pages": len(reader.pages),
                "text": text,
                "truncated": truncated,
            }

        if suffix == ".docx":
            docx = _require_optional("docx", "python-docx")
            document = docx.Document(str(path))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
            text, truncated = self._limit_text(text, max_chars)
            return {
                "kind": "docx",
                "path": str(path),
                "text": text,
                "truncated": truncated,
            }

        if suffix in {".xlsx", ".xlsm", ".xltx"}:
            openpyxl = _require_optional("openpyxl", "openpyxl")
            workbook = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
            sheet_name = sheet if sheet in workbook.sheetnames else workbook.sheetnames[0]
            worksheet = workbook[sheet_name]
            rows: list[list[str]] = []
            for row_idx, row in enumerate(worksheet.iter_rows(values_only=True)):
                if row_idx >= 500:
                    break
                rows.append(["" if cell is None else str(cell) for cell in row])
            text = "\n".join("\t".join(row) for row in rows)
            text, truncated = self._limit_text(text, max_chars)
            return {
                "kind": "xlsx",
                "path": str(path),
                "sheet": sheet_name,
                "sheets": workbook.sheetnames,
                "rows": rows,
                "text": text,
                "truncated": truncated,
            }

        if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}:
            pil = _require_optional("PIL", "pillow")
            image = pil.Image.open(str(path))
            return {
                "kind": "image",
                "path": str(path),
                "format": image.format,
                "mode": image.mode,
                "size": {"width": image.width, "height": image.height},
            }

        if suffix in {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".opus"}:
            mutagen = _require_optional("mutagen", "mutagen")
            media = mutagen.File(str(path))
            meta: dict[str, Any] = {
                "kind": "audio",
                "path": str(path),
                "mime": mimetypes.guess_type(str(path))[0],
            }
            if media is not None:
                duration = getattr(getattr(media, "info", None), "length", None)
                if isinstance(duration, (int, float)):
                    meta["duration_seconds"] = round(float(duration), 3)
                tags = getattr(media, "tags", None)
                if tags:
                    sample_tags: dict[str, str] = {}
                    for index, (key, value) in enumerate(tags.items()):
                        if index >= 20:
                            break
                        sample_tags[str(key)] = str(value)
                    meta["tags"] = sample_tags

            if transcribe:
                openai = _require_optional("openai", "openai")
                # Environment-only by design to avoid leaking secrets in config dumps.
                key = os.getenv("REPLICA_MODEL_API_KEY") or os.getenv("OPENAI_API_KEY")
                if not key:
                    raise ToolError("OPENAI_API_KEY is required for transcription")
                client = openai.OpenAI(api_key=key)
                with path.open("rb") as handle:
                    transcript = await asyncio.to_thread(
                        client.audio.transcriptions.create,
                        model=audio_model,
                        file=handle,
                    )
                text = getattr(transcript, "text", "") or ""
                text, truncated = self._limit_text(text, max_chars)
                meta["transcript"] = text
                meta["transcript_truncated"] = truncated

            return meta

        text = path.read_text(encoding="utf-8", errors="replace")
        text, truncated = self._limit_text(text, max_chars)
        return {
            "kind": "text",
            "path": str(path),
            "text": text,
            "truncated": truncated,
            "note": f"fallback reader used for extension {suffix or '<none>'}",
        }


def format_tool_result_for_model(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=True)
