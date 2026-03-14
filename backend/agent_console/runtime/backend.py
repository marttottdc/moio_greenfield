from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
import re
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path
from typing import Any, Awaitable, Callable

from .config import ModelConfig, ReplicaConfig
from .llm_client import OpenAIModelClient
from .media_store import MediaStore
from .plugins import resolve_active_plugins
from .session_store import (
    build_event_log_from_messages,
    SessionMessage,
    SessionStore,
    make_text_content,
    normalize_session_author,
    normalize_session_context_scope,
    normalize_session_scope,
    session_scope_visible_to_actor,
)
from .skills import SkillEntry, build_skills_prompt, load_skills
from .tools import ToolError, ToolRegistry, format_tool_result_for_model
from .vendor_store import DEFAULT_CAPABILITIES, VendorStore

EventSink = Callable[[dict[str, Any]], Awaitable[None]]
UserNotificationSender = Callable[[dict[str, Any], dict[str, Any]], Awaitable[None]]


@dataclass(slots=True)
class ActiveRun:
    run_id: str
    session_key: str
    task: asyncio.Task[None]
    started_at_ms: int
    initiator: dict[str, Any] | None = None
    selected_profile: str = ""
    agent_runtime: dict[str, Any] | None = None


class AgentConsoleBackend:
    _ATTACHMENT_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
    _SUMMARY_HEADER_RE = re.compile(r"^\s*#{1,3}\s*(.+?)\s*$")
    _MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")

    def __init__(
        self,
        config: ReplicaConfig,
        logger: logging.Logger | None = None,
        *,
        tenant_schema: str = "public",
        workspace_slug: str = "main",
        api_connection_resolver: Callable[[str], dict[str, Any] | None] | None = None,
        session_store: SessionStore | None = None,
        memory_recorder: Callable[..., dict[str, Any]] | None = None,
        memory_searcher: Callable[..., list[dict[str, Any]]] | None = None,
        memory_recent: Callable[..., list[dict[str, Any]]] | None = None,
        integration_guidance_resolver: Callable[[], str] | None = None,
        integration_status_resolver: Callable[[], dict[str, Any]] | None = None,
        agent_profile_state_resolver: Callable[[dict[str, Any] | None, str | None], dict[str, Any]] | None = None,
        agent_profiles_catalog_resolver: Callable[[], dict[str, Any]] | None = None,
        agent_profile_upsert_handler: Callable[[dict[str, Any], dict[str, Any] | None], dict[str, Any]] | None = None,
        workspace_profile_resolver: Callable[[], dict[str, Any]] | None = None,
        workspace_skills_resolver: Callable[[], list[dict[str, Any]]] | None = None,
        plugin_user_allowlist_resolver: Callable[[dict[str, Any] | None], list[str]] | None = None,
        plugin_runtime_config_resolver: Callable[[], dict[str, dict[str, Any]]] | None = None,
        installed_plugins_resolver: Callable[[], list[dict[str, Any]]] | None = None,
    ):
        self.config = config
        self.log = logger or logging.getLogger("agent_console.runtime.backend")
        self.sessions = session_store or SessionStore(config.sessions_dir)
        self.vendors = VendorStore(config.tools.vendors_file)
        self.vendors.seed_defaults(self._default_vendor_entries())
        self.tenant_schema = str(tenant_schema or "public").strip() or "public"
        self.workspace_slug = str(workspace_slug or "main").strip() or "main"
        installed_plugins_payload: list[dict[str, Any]] = []
        if callable(installed_plugins_resolver):
            try:
                resolved_plugins = installed_plugins_resolver()
                if isinstance(resolved_plugins, list):
                    installed_plugins_payload = [item for item in resolved_plugins if isinstance(item, dict)]
            except Exception as exc:
                self.log.warning("installed plugins resolution failed: %s", exc)
        runtime_plugin_configs: dict[str, dict[str, Any]] = {}
        if callable(plugin_runtime_config_resolver):
            try:
                resolved_runtime_configs = plugin_runtime_config_resolver()
                if isinstance(resolved_runtime_configs, dict):
                    runtime_plugin_configs = {
                        str(key or "").strip().lower(): dict(value)
                        for key, value in resolved_runtime_configs.items()
                        if str(key or "").strip() and isinstance(value, dict)
                    }
            except Exception as exc:
                self.log.warning("plugin runtime config resolution failed: %s", exc)
        self.active_plugins, self.plugin_reports = resolve_active_plugins(
            config.plugins,
            installed_plugins=installed_plugins_payload,
            runtime_plugin_configs=runtime_plugin_configs,
        )
        use_django_storage = getattr(session_store, "_database_store", False)
        self.media_store = MediaStore(
            workspace_root=config.tools.workspace_root,
            tenant_schema=self.tenant_schema,
            workspace_slug=self.workspace_slug,
            logger=self.log,
            use_django_storage=use_django_storage,
        )
        self.tools = ToolRegistry(
            workspace_root=config.tools.workspace_root,
            shell_enabled=config.tools.shell_enabled,
            shell_timeout_seconds=config.tools.shell_timeout_seconds,
            docker_enabled=config.tools.docker_enabled,
            docker_timeout_seconds=config.tools.docker_timeout_seconds,
            dynamic_tools_enabled=config.tools.dynamic_tools_enabled,
            dynamic_tools_dir=config.tools.dynamic_tools_dir,
            package_install_enabled=config.tools.package_install_enabled,
            package_install_timeout_seconds=config.tools.package_install_timeout_seconds,
            vault_enabled=config.tools.vault_enabled,
            vault_file=config.tools.vault_file,
            vault_passphrase=config.tools.vault_passphrase,
            api_connection_resolver=api_connection_resolver,
            memory_recorder=memory_recorder,
            memory_searcher=memory_searcher,
            memory_recent=memory_recent,
            active_plugins=self.active_plugins,
        )
        self.memory_recorder = memory_recorder
        self.memory_recent = memory_recent
        self.integration_guidance_resolver = integration_guidance_resolver
        self.integration_status_resolver = integration_status_resolver
        self.agent_profile_state_resolver = agent_profile_state_resolver
        self.agent_profiles_catalog_resolver = agent_profiles_catalog_resolver
        self.agent_profile_upsert_handler = agent_profile_upsert_handler
        self.workspace_profile_resolver = workspace_profile_resolver
        self.workspace_skills_resolver = workspace_skills_resolver
        self.plugin_user_allowlist_resolver = plugin_user_allowlist_resolver
        self._model_clients: dict[str, OpenAIModelClient] = {}
        self.model = self._client_for_config(config.model)
        self.skills: list[SkillEntry] = []

        self._active_runs: dict[str, ActiveRun] = {}
        self._active_lock = asyncio.Lock()
        self._event_sink: EventSink | None = None
        self._user_notification_sender: UserNotificationSender | None = None
        self._run_seq: dict[str, int] = {}
        self._run_started_at: dict[str, int] = {}
        self._run_waiters: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._run_generated_files: dict[str, list[dict[str, Any]]] = {}
        self._summary_refresh_tasks: dict[str, asyncio.Task[None]] = {}

    def set_event_sink(self, sink: EventSink) -> None:
        self._event_sink = sink

    def set_user_notification_sender(self, sender: UserNotificationSender) -> None:
        self._user_notification_sender = sender

    async def start(self) -> None:
        if not getattr(self.sessions, "_database_store", False):
            self.config.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.skills = load_skills(self.config.skills.directories, self.config.skills.enabled)

    async def stop(self) -> None:
        async with self._active_lock:
            runs = list(self._active_runs.values())
        summary_tasks = list(self._summary_refresh_tasks.values())
        for run in runs:
            run.task.cancel()
        for task in summary_tasks:
            task.cancel()
        if runs:
            await asyncio.gather(*(run.task for run in runs), return_exceptions=True)
        if summary_tasks:
            await asyncio.gather(*summary_tasks, return_exceptions=True)

    async def _session_load_messages(self, session_key: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.sessions.load_messages, session_key)

    async def _session_load_event_log(
        self,
        session_key: str,
        *,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if hasattr(self.sessions, "load_event_log"):
            loaded = await asyncio.to_thread(getattr(self.sessions, "load_event_log"), session_key, limit)
            if isinstance(loaded, list):
                return [item for item in loaded if isinstance(item, dict)]
        messages = await self._session_load_messages(session_key)
        return build_event_log_from_messages(messages, limit=limit)

    async def _session_load_summary(self, session_key: str) -> tuple[str, int]:
        return await asyncio.to_thread(self.sessions.load_summary, session_key)

    async def _session_save_summary(self, session_key: str, summary: str, summary_upto: int) -> None:
        await asyncio.to_thread(self.sessions.save_summary, session_key, summary, summary_upto)

    async def _session_load_title(self, session_key: str) -> str:
        if hasattr(self.sessions, "load_session_title"):
            loaded = await asyncio.to_thread(getattr(self.sessions, "load_session_title"), session_key)
            if isinstance(loaded, str):
                return loaded.strip()
        return ""

    async def _session_load_meta(self, session_key: str) -> dict[str, Any]:
        if hasattr(self.sessions, "load_session_meta"):
            loaded = await asyncio.to_thread(getattr(self.sessions, "load_session_meta"), session_key)
            if isinstance(loaded, dict):
                return {
                    "sessionKey": str(loaded.get("sessionKey", "") or "").strip() or (session_key.strip() or "main"),
                    "scope": normalize_session_scope(loaded.get("scope")),
                    "owner": normalize_session_author(loaded.get("owner")),
                }
        return {
            "sessionKey": session_key.strip() or "main",
            "scope": "shared",
            "owner": None,
        }

    async def _ensure_session_access(self, session_key: str, initiator: dict[str, Any] | None = None) -> dict[str, Any]:
        meta = await self._session_load_meta(session_key)
        if session_scope_visible_to_actor(meta.get("scope"), meta.get("owner"), initiator):
            return meta
        raise PermissionError("private conversation is only available to its owner")

    async def _session_save_title(self, session_key: str, title: str) -> str:
        normalized = str(title or "").strip()
        if hasattr(self.sessions, "save_session_title"):
            saved = await asyncio.to_thread(getattr(self.sessions, "save_session_title"), session_key, normalized)
            if isinstance(saved, str):
                return saved.strip()
        return normalized

    async def _session_append(self, session_key: str, message: SessionMessage) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.sessions.append, session_key, message)

    async def _session_create(
        self,
        session_key: str,
        *,
        scope: str = "shared",
        initiator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if hasattr(self.sessions, "create_session"):
            create_fn = getattr(self.sessions, "create_session")
            try:
                created = await asyncio.to_thread(
                    create_fn,
                    session_key,
                    normalize_session_scope(scope),
                    normalize_session_author(initiator),
                )
            except TypeError:
                created = await asyncio.to_thread(create_fn, session_key)
            if isinstance(created, dict):
                return created
        await asyncio.to_thread(self.sessions.save_messages, session_key, await self._session_load_messages(session_key))
        return {"sessionKey": session_key, "scope": normalize_session_scope(scope)}

    async def _session_set_scope(
        self,
        session_key: str,
        *,
        scope: str = "shared",
        initiator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_scope = normalize_session_scope(scope)
        normalized_owner = normalize_session_author(initiator)
        if normalized_scope == "private" and normalized_owner is None:
            raise PermissionError("private conversation requires an authenticated owner")
        if hasattr(self.sessions, "set_session_scope"):
            set_scope_fn = getattr(self.sessions, "set_session_scope")
            try:
                updated = await asyncio.to_thread(
                    set_scope_fn,
                    session_key,
                    normalized_scope,
                    normalized_owner,
                )
            except TypeError:
                updated = await asyncio.to_thread(set_scope_fn, session_key, normalized_scope)
            if isinstance(updated, dict):
                return updated
        if hasattr(self.sessions, "create_session"):
            create_fn = getattr(self.sessions, "create_session")
            try:
                updated = await asyncio.to_thread(
                    create_fn,
                    session_key,
                    normalized_scope,
                    normalized_owner,
                )
            except TypeError:
                updated = await asyncio.to_thread(create_fn, session_key, normalized_scope)
            if isinstance(updated, dict):
                return updated
        return {"sessionKey": session_key, "scope": normalized_scope}

    async def _session_load_queue(self, session_key: str) -> list[dict[str, Any]]:
        if hasattr(self.sessions, "load_queue"):
            loaded = await asyncio.to_thread(getattr(self.sessions, "load_queue"), session_key)
            if isinstance(loaded, list):
                return [item for item in loaded if isinstance(item, dict)]
        return []

    async def _session_save_queue(self, session_key: str, queued_turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if hasattr(self.sessions, "save_queue"):
            saved = await asyncio.to_thread(getattr(self.sessions, "save_queue"), session_key, queued_turns)
            if isinstance(saved, list):
                return [item for item in saved if isinstance(item, dict)]
        return queued_turns

    def _serialize_queue_item(self, item: dict[str, Any]) -> dict[str, Any]:
        attachments = item.get("attachments")
        attachments_count = len(attachments) if isinstance(attachments, list) else int(item.get("attachmentsCount", 0) or 0)
        return {
            "id": str(item.get("id", "") or "").strip(),
            "message": str(item.get("message", "") or "").strip(),
            "attachmentsCount": max(0, attachments_count),
            "author": normalize_session_author(item.get("author")),
            "createdAtMs": int(item.get("createdAtMs", 0) or 0),
            "selectedProfile": str(item.get("selectedProfile", "") or "").strip(),
        }

    def _queue_payload_from_items(
        self,
        session_key: str,
        *,
        scope: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "payload": {
                "sessionKey": session_key,
                "scope": normalize_session_scope(scope),
                "items": [self._serialize_queue_item(item) for item in items if isinstance(item, dict)],
                "count": len(items),
            },
        }

    async def _queue_payload(self, session_key: str) -> dict[str, Any]:
        meta = await self._session_load_meta(session_key)
        items = await self._session_load_queue(session_key)
        return self._queue_payload_from_items(
            session_key,
            scope=str(meta.get("scope") or "shared"),
            items=items,
        )

    async def _emit_queue_state(self, session_key: str) -> None:
        if not self._event_sink:
            return
        await self._event_sink(
            {
                "type": "chat_queue",
                "payload": await self._queue_payload(session_key),
            }
        )

    @staticmethod
    def _queue_item_owned_by_actor(item: dict[str, Any], actor: dict[str, Any] | None) -> bool:
        author = normalize_session_author(item.get("author"))
        normalized_actor = normalize_session_author(actor)
        if author is None or normalized_actor is None:
            return False
        author_id = int(author.get("id", 0) or 0)
        actor_id = int(normalized_actor.get("id", 0) or 0)
        if author_id > 0 and author_id == actor_id:
            return True
        author_email = str(author.get("email", "") or "").strip().lower()
        actor_email = str(normalized_actor.get("email", "") or "").strip().lower()
        return bool(author_email and actor_email and author_email == actor_email)

    def _active_run_for_session_unlocked(self, session_key: str) -> ActiveRun | None:
        key = str(session_key or "").strip() or "main"
        for active in self._active_runs.values():
            if str(active.session_key or "").strip() == key:
                return active
        return None

    async def _start_queued_turn(self, session_key: str) -> bool:
        queued_item: dict[str, Any] | None = None
        task: asyncio.Task[None] | None = None
        run_id = ""
        removed_invalid = False
        try:
            async with self._active_lock:
                if self._active_run_for_session_unlocked(session_key) is not None:
                    return False
                queue = await self._session_load_queue(session_key)
                if not queue:
                    return False
                queued_item = dict(queue[0]) if isinstance(queue[0], dict) else None
                if not queued_item:
                    queue = queue[1:]
                    await self._session_save_queue(session_key, queue)
                    removed_invalid = True
                else:
                    run_id = str(queued_item.get("id", "") or "").strip() or str(uuid.uuid4())
                    initiator = queued_item.get("initiator") if isinstance(queued_item.get("initiator"), dict) else None
                    requested_allowlist = (
                        list(queued_item.get("toolAllowlist", []))
                        if isinstance(queued_item.get("toolAllowlist"), list)
                        else None
                    )
                    selected_profile = str(queued_item.get("selectedProfile", "") or "").strip() or None
                    agent_runtime = await self.agent_runtime(
                        initiator=initiator,
                        selected_profile=selected_profile,
                        requested_tool_allowlist=requested_allowlist,
                    )
                    resolved_profile_key = str(
                        (((agent_runtime.get("activeProfile") or {}) if isinstance(agent_runtime.get("activeProfile"), dict) else {}).get("key"))
                        or selected_profile
                        or ""
                    ).strip()
                    queue = queue[1:]
                    await self._session_save_queue(session_key, queue)
                    task = asyncio.create_task(
                        self._execute_run(
                            run_id=run_id,
                            session_key=session_key,
                            message=str(queued_item.get("message", "") or ""),
                            attachments=(
                                list(queued_item.get("attachments", []))
                                if isinstance(queued_item.get("attachments"), list)
                                else None
                            ),
                            thinking=str(queued_item.get("thinking", "") or "").strip() or None,
                            verbosity=str(queued_item.get("verbosity", "") or "").strip() or None,
                            model_overrides=(
                                dict(queued_item.get("modelOverrides", {}))
                                if isinstance(queued_item.get("modelOverrides"), dict)
                                else None
                            ),
                            tool_allowlist=requested_allowlist,
                            timeout_ms=(
                                int(queued_item.get("timeoutMs", 0) or 0)
                                if int(queued_item.get("timeoutMs", 0) or 0) > 0
                                else None
                            ),
                            initiator=initiator,
                            selected_profile=resolved_profile_key,
                            agent_runtime=agent_runtime,
                        ),
                        name=f"run:{run_id}",
                    )
                    started_at_ms = int(time.time() * 1000)
                    self._active_runs[run_id] = ActiveRun(
                        run_id=run_id,
                        session_key=session_key,
                        task=task,
                        started_at_ms=started_at_ms,
                        initiator=(dict(initiator) if isinstance(initiator, dict) else None),
                        selected_profile=resolved_profile_key,
                        agent_runtime=agent_runtime,
                    )
                    self._run_started_at[run_id] = started_at_ms
        except Exception as exc:
            self.log.exception("queued turn start failed: %s", exc)
            return False
        if removed_invalid:
            await self._emit_queue_state(session_key)
            return False
        await self._emit_queue_state(session_key)
        if task is not None:
            task.add_done_callback(lambda _: asyncio.create_task(self._finalize_run(run_id)))
        return task is not None

    async def chat_queue(self, session_key: str, initiator: dict[str, Any] | None = None) -> dict[str, Any]:
        await self._ensure_session_access(session_key, initiator)
        return await self._queue_payload(session_key)

    async def retire_queued_turn(
        self,
        *,
        session_key: str,
        queue_item_id: str,
        initiator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = await self._ensure_session_access(session_key, initiator)
        queue = await self._session_load_queue(session_key)
        target_id = str(queue_item_id or "").strip()
        if not target_id:
            raise ValueError("queueItemId is required")
        removed: dict[str, Any] | None = None
        remaining: list[dict[str, Any]] = []
        for item in queue:
            item_id = str(item.get("id", "") or "").strip()
            if item_id == target_id and removed is None:
                if normalize_session_scope(meta.get("scope")) == "private" or self._queue_item_owned_by_actor(item, initiator):
                    removed = item
                    continue
                raise PermissionError("you can only retire your own queued messages")
            remaining.append(item)
        if removed is None:
            raise ValueError("queued message not found")
        await self._session_save_queue(session_key, remaining)
        await self._emit_queue_state(session_key)
        return await self._queue_payload(session_key)

    async def force_push_queued_turn(
        self,
        *,
        session_key: str,
        queue_item_id: str,
        initiator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = await self._ensure_session_access(session_key, initiator)
        if normalize_session_scope(meta.get("scope")) != "private":
            raise PermissionError("force push is only available in private conversations")
        queue = await self._session_load_queue(session_key)
        target_id = str(queue_item_id or "").strip()
        if not target_id:
            raise ValueError("queueItemId is required")
        index = next((idx for idx, item in enumerate(queue) if str(item.get("id", "") or "").strip() == target_id), -1)
        if index < 0:
            raise ValueError("queued message not found")
        if index > 0:
            item = queue.pop(index)
            queue.insert(0, item)
            await self._session_save_queue(session_key, queue)
            await self._emit_queue_state(session_key)
        return await self._queue_payload(session_key)

    async def status(self) -> dict[str, Any]:
        return {
            "backend": "standalone",
            "connected": True,
            "provider": self._normalize_vendor(self.config.model.provider),
            "model": self.config.model.model,
            "workspaceRoot": str(self.config.tools.workspace_root),
            "sessionsDir": str(self.config.sessions_dir),
            "vendorsFile": str(self.config.tools.vendors_file),
            "mediaBackend": self.media_store.mode,
            "mediaRoot": str(self.media_store.local_root),
        }

    async def _load_workspace_profile(self) -> dict[str, Any]:
        if self.workspace_profile_resolver is None:
            return {}
        try:
            loaded = await asyncio.to_thread(self.workspace_profile_resolver)
        except Exception as exc:
            self.log.warning("workspace profile load failed: %s", exc)
            return {}
        return loaded if isinstance(loaded, dict) else {}

    async def _load_agent_profile_state(
        self,
        *,
        initiator: dict[str, Any] | None = None,
        selected_profile: str | None = None,
    ) -> dict[str, Any]:
        if self.agent_profile_state_resolver is None:
            return {
                "profiles": [],
                "activeProfile": {},
                "diagnostics": {
                    "requestedProfile": str(selected_profile or "").strip(),
                    "resolvedProfile": "",
                    "selectionSource": "runtime_default",
                    "requestedProfileRejected": False,
                    "hasExplicitAssignments": False,
                    "initiatorIsAdmin": False,
                },
            }
        try:
            loaded = await asyncio.to_thread(self.agent_profile_state_resolver, initiator, selected_profile)
        except Exception as exc:
            self.log.warning("agent profile state load failed: %s", exc)
            return {
                "profiles": [],
                "activeProfile": {},
                "diagnostics": {
                    "requestedProfile": str(selected_profile or "").strip(),
                    "resolvedProfile": "",
                    "selectionSource": "runtime_default",
                    "requestedProfileRejected": False,
                    "hasExplicitAssignments": False,
                    "initiatorIsAdmin": False,
                    "resolutionError": str(exc),
                },
            }
        return loaded if isinstance(loaded, dict) else {}

    def _runtime_defaults_for_request(
        self,
        *,
        workspace_profile: dict[str, Any] | None,
        agent_profile_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        workspace = workspace_profile if isinstance(workspace_profile, dict) else {}
        active_profile = (
            agent_profile_state.get("activeProfile")
            if isinstance(agent_profile_state, dict) and isinstance(agent_profile_state.get("activeProfile"), dict)
            else {}
        )

        fallback_fields: list[str] = []

        raw_vendor = str(active_profile.get("defaultVendor") or "").strip() or str(workspace.get("defaultVendor") or "").strip()
        if not str(active_profile.get("defaultVendor") or "").strip() and str(workspace.get("defaultVendor") or "").strip():
            fallback_fields.append("defaultVendor")
        vendor = self._normalize_vendor(raw_vendor or self.config.model.provider)

        model = str(active_profile.get("defaultModel") or "").strip()
        if not model:
            model = str(workspace.get("defaultModel") or "").strip()
            if model:
                fallback_fields.append("defaultModel")

        thinking = str(active_profile.get("defaultThinking") or "").strip().lower()
        if not thinking:
            thinking = str(workspace.get("defaultThinking") or "").strip().lower()
            if thinking:
                fallback_fields.append("defaultThinking")
        if not thinking:
            thinking = str(self.config.agent.thinking or "default").strip().lower()
        thinking = thinking or "default"

        verbosity = str(active_profile.get("defaultVerbosity") or "").strip().lower()
        if not verbosity:
            verbosity = str(workspace.get("defaultVerbosity") or "").strip().lower()
            if verbosity:
                fallback_fields.append("defaultVerbosity")
        if not verbosity:
            verbosity = str(self.config.agent.verbosity or "minimal").strip().lower()
        verbosity = verbosity or "minimal"

        tool_allowlist = active_profile.get("toolAllowlist")
        profile_tool_allowlist = [str(item).strip() for item in tool_allowlist if str(item).strip()] if isinstance(tool_allowlist, list) else []
        if not profile_tool_allowlist:
            workspace_tool_allowlist = workspace.get("toolAllowlist")
            profile_tool_allowlist = (
                [str(item).strip() for item in workspace_tool_allowlist if str(item).strip()]
                if isinstance(workspace_tool_allowlist, list)
                else []
            )

        return {
            "vendor": vendor,
            "model": model,
            "thinking": thinking,
            "verbosity": verbosity,
            "systemPrompt": str(active_profile.get("systemPrompt") or "").strip(),
            "profileToolAllowlist": profile_tool_allowlist,
            "workspaceFallbackFields": fallback_fields,
        }

    async def agent_runtime(
        self,
        *,
        initiator: dict[str, Any] | None = None,
        selected_profile: str | None = None,
        requested_tool_allowlist: list[str] | None = None,
    ) -> dict[str, Any]:
        workspace_profile = await self._load_workspace_profile()
        agent_profile_state = await self._load_agent_profile_state(
            initiator=initiator,
            selected_profile=selected_profile,
        )
        runtime_defaults = self._runtime_defaults_for_request(
            workspace_profile=workspace_profile,
            agent_profile_state=agent_profile_state,
        )
        effective_tool_allowlist = await self.effective_tool_allowlist(
            initiator=initiator,
            requested=requested_tool_allowlist,
            profile_allowlist=runtime_defaults.get("profileToolAllowlist"),
        )

        provider = str(runtime_defaults.get("vendor") or self._normalize_vendor(self.config.model.provider)).strip() or "openai"
        current_model = str(runtime_defaults.get("model") or "").strip() or self.config.model.model
        diagnostics = (
            dict(agent_profile_state.get("diagnostics", {}))
            if isinstance(agent_profile_state.get("diagnostics"), dict)
            else {}
        )
        diagnostics["workspaceFallbackFields"] = list(runtime_defaults.get("workspaceFallbackFields", []))
        diagnostics["effectiveToolAllowlist"] = list(effective_tool_allowlist)

        active_profile = (
            dict(agent_profile_state.get("activeProfile", {}))
            if isinstance(agent_profile_state.get("activeProfile"), dict)
            else {}
        )
        profiles = (
            list(agent_profile_state.get("profiles", []))
            if isinstance(agent_profile_state.get("profiles"), list)
            else []
        )
        return {
            "profiles": profiles,
            "activeProfile": active_profile,
            "workspaceProfile": workspace_profile if isinstance(workspace_profile, dict) else {},
            "effective": {
                "provider": provider,
                "model": current_model,
                "thinking": str(runtime_defaults.get("thinking") or "default"),
                "verbosity": str(runtime_defaults.get("verbosity") or "minimal"),
                "toolAllowlist": effective_tool_allowlist,
                "hasSystemPromptAugmentation": bool(str(runtime_defaults.get("systemPrompt") or "").strip()),
            },
            "diagnostics": diagnostics,
        }

    async def effective_tool_allowlist(
        self,
        *,
        initiator: dict[str, Any] | None = None,
        requested: list[str] | None = None,
        profile_allowlist: list[str] | None = None,
    ) -> list[str]:
        return await self._effective_runtime_tool_allowlist(
            requested,
            initiator=initiator,
            profile_allowlist=profile_allowlist,
        )

    async def _resolved_user_allowed_plugins(self, initiator: dict[str, Any] | None = None) -> set[str]:
        if callable(self.plugin_user_allowlist_resolver):
            resolver_failed = False
            try:
                resolved = await asyncio.to_thread(
                    self.plugin_user_allowlist_resolver,
                    initiator if isinstance(initiator, dict) else None,
                )
            except TypeError:
                resolved = await asyncio.to_thread(self.plugin_user_allowlist_resolver, None)
            except Exception as exc:
                self.log.warning("plugin user allowlist resolution failed: %s", exc)
                resolved = []
                resolver_failed = True
            if not resolver_failed:
                # Resolver output is authoritative (including empty set) for tenant plugin enablement.
                return {str(item or "").strip().lower() for item in resolved if str(item or "").strip()}
        else:
            resolved = list(self.config.plugins.user_allowed)
        resolved_set = {str(item or "").strip().lower() for item in resolved if str(item or "").strip()}
        if resolved_set:
            return resolved_set
        configured = {
            str(item or "").strip().lower()
            for item in getattr(self.config.plugins, "user_allowed", [])
            if str(item or "").strip()
        }
        if configured:
            return configured
        # Last-resort safety: if no explicit user gate is configured, do not suppress
        # all plugin tools silently. Active plugin readiness checks still apply.
        return {
            str(plugin.manifest.plugin_id or "").strip().lower()
            for plugin in self.active_plugins
            if str(plugin.manifest.plugin_id or "").strip()
        }

    async def agent_profiles_catalog(self, *, initiator: dict[str, Any] | None = None) -> dict[str, Any]:
        runtime_state = await self.agent_runtime(initiator=initiator)
        catalog_payload = {
            "profiles": list(runtime_state.get("profiles", [])) if isinstance(runtime_state.get("profiles"), list) else [],
            "assignments": [],
            "activeProfile": (
                dict(runtime_state.get("activeProfile", {}))
                if isinstance(runtime_state.get("activeProfile"), dict)
                else {}
            ),
            "diagnostics": (
                dict(runtime_state.get("diagnostics", {}))
                if isinstance(runtime_state.get("diagnostics"), dict)
                else {}
            ),
            "managementMode": "runtime",
        }
        if self._initiator_role(initiator) != "admin" or self.agent_profiles_catalog_resolver is None:
            return {"ok": True, "payload": catalog_payload}
        try:
            loaded = await asyncio.to_thread(self.agent_profiles_catalog_resolver)
        except Exception as exc:
            self.log.warning("agent profiles catalog load failed: %s", exc)
            catalog_payload["error"] = str(exc)
            return {"ok": False, "payload": catalog_payload}
        loaded_payload = loaded if isinstance(loaded, dict) else {}
        catalog_payload["profiles"] = (
            list(loaded_payload.get("profiles", []))
            if isinstance(loaded_payload.get("profiles"), list)
            else catalog_payload["profiles"]
        )
        catalog_payload["assignments"] = (
            list(loaded_payload.get("assignments", []))
            if isinstance(loaded_payload.get("assignments"), list)
            else []
        )
        catalog_payload["managementMode"] = "admin"
        return {"ok": True, "payload": catalog_payload}

    async def agent_profile_upsert(
        self,
        payload: dict[str, Any],
        *,
        initiator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._initiator_role(initiator) != "admin":
            raise PermissionError("agent profile management requires a tenant admin initiator")
        if self.agent_profile_upsert_handler is None:
            raise ValueError("agent profile management is not configured")
        saved = await asyncio.to_thread(self.agent_profile_upsert_handler, payload, initiator)
        catalog = await self.agent_profiles_catalog(initiator=initiator)
        return {
            "ok": True,
            "payload": {
                "profile": saved if isinstance(saved, dict) else {},
                "catalog": (catalog.get("payload", {}) if isinstance(catalog, dict) else {}),
            },
        }

    async def resources(
        self,
        *,
        initiator: dict[str, Any] | None = None,
        selected_profile: str | None = None,
        requested_tool_allowlist: list[str] | None = None,
    ) -> dict[str, Any]:
        agent_runtime = await self.agent_runtime(
            initiator=initiator,
            selected_profile=selected_profile,
            requested_tool_allowlist=requested_tool_allowlist,
        )
        effective = (
            dict(agent_runtime.get("effective", {}))
            if isinstance(agent_runtime.get("effective"), dict)
            else {}
        )
        tool_catalog = self.tools.tools_catalog_exact(
            list(effective.get("toolAllowlist", [])) if isinstance(effective.get("toolAllowlist"), list) else []
        )
        workspace_profile = (
            dict(agent_runtime.get("workspaceProfile", {}))
            if isinstance(agent_runtime.get("workspaceProfile"), dict)
            else {}
        )
        provider = str(effective.get("provider") or self._normalize_vendor(self.config.model.provider)).strip() or "openai"
        current_model = str(effective.get("model") or "").strip()
        vendors = self.vendors.list(include_secret=False)
        vendor_entry = next((entry for entry in vendors if entry.get("id") == provider), None)
        if vendor_entry is None:
            provider = self._normalize_vendor(self.config.model.provider)
            vendor_entry = next((entry for entry in vendors if entry.get("id") == provider), vendors[0] if vendors else None)
        if not current_model:
            vendor_models = list(vendor_entry.get("models", [])) if vendor_entry else []
            first_model = ""
            if vendor_models and isinstance(vendor_models[0], dict):
                first_model = str(vendor_models[0].get("id", "")).strip()
            current_model = first_model or self.config.model.model
        skills_payload = {
            "skills": [
                {
                    "key": skill.key,
                    "name": skill.name,
                    "enabled": skill.enabled,
                    "path": str(skill.path),
                }
                for skill in self.skills
            ],
            "enabledCount": len([skill for skill in self.skills if skill.enabled]),
        }
        workspace_skills: list[dict[str, Any]] = []
        if self.workspace_skills_resolver is not None:
            try:
                workspace_skills = await asyncio.to_thread(self.workspace_skills_resolver)
            except Exception as exc:
                self.log.warning("workspace skills load failed: %s", exc)
                workspace_skills = []
        tenant_integrations_payload: dict[str, Any] = {"enabledCount": 0, "integrations": []}
        if self.integration_status_resolver is not None:
            try:
                loaded = await asyncio.to_thread(self.integration_status_resolver)
                if isinstance(loaded, dict):
                    tenant_integrations_payload = {
                        "enabledCount": int(loaded.get("enabledCount", 0) or 0),
                        "integrations": loaded.get("integrations", []) if isinstance(loaded.get("integrations", []), list) else [],
                    }
            except Exception as exc:
                self.log.warning("tenant integrations load failed: %s", exc)

        user_allowed_plugins = await self._resolved_user_allowed_plugins(initiator)
        active_plugins = [
            plugin
            for plugin in self.active_plugins
            if str(plugin.manifest.plugin_id or "").strip().lower() in user_allowed_plugins
        ]
        blocked_plugin_ids = {
            str(plugin.manifest.plugin_id or "").strip().lower()
            for plugin in self.active_plugins
            if str(plugin.manifest.plugin_id or "").strip().lower() not in user_allowed_plugins
        }
        reports: list[dict[str, Any]] = []
        for report in self.plugin_reports:
            plugin_id = str(report.plugin_id or "").strip().lower()
            if plugin_id in blocked_plugin_ids:
                reports.append(
                    {
                        "pluginId": plugin_id,
                        "active": False,
                        "stage": "user_assignment",
                        "reasons": ["plugin is not assigned or allowed for this user"],
                        "missing": {},
                    }
                )
                continue
            reports.append(report.to_dict())

        return {
            "status": {"ok": True, "payload": await self.status()},
            "models": {
                "ok": True,
                "payload": {
                    "provider": provider,
                    "models": list(vendor_entry.get("models", [])) if vendor_entry else [],
                    "current": current_model,
                    "vendors": vendors,
                    "temperature": self.config.model.temperature,
                    "maxOutputTokens": self.config.model.max_output_tokens,
                },
            },
            "agents": {
                "ok": True,
                "payload": {
                    "agents": [
                        {
                            "id": "default",
                            "name": "Default",
                            "workspaceDir": str(self.config.tools.workspace_root),
                        }
                    ]
                },
            },
            "toolsCatalog": {
                "ok": True,
                "payload": {
                    "agentId": "default",
                    **tool_catalog,
                },
            },
            "skillsStatus": {"ok": True, "payload": skills_payload},
            "agentProfiles": {
                "ok": True,
                "payload": {
                    "profiles": list(agent_runtime.get("profiles", [])) if isinstance(agent_runtime.get("profiles"), list) else [],
                    "activeProfile": (
                        dict(agent_runtime.get("activeProfile", {}))
                        if isinstance(agent_runtime.get("activeProfile"), dict)
                        else {}
                    ),
                },
            },
            "agentRuntime": {"ok": True, "payload": agent_runtime},
            "workspaceProfile": {"ok": True, "payload": workspace_profile or {}},
            "workspaceSkills": {"ok": True, "payload": {"skills": workspace_skills}},
            "tenantIntegrations": {"ok": True, "payload": tenant_integrations_payload},
            "pluginsStatus": {
                "ok": True,
                "payload": {
                    "activeCount": len(active_plugins),
                    "active": [plugin.to_dict() for plugin in active_plugins],
                    "reports": reports,
                },
            },
        }

    async def chat_history(
        self,
        session_key: str,
        limit: int = 200,
        initiator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = await self._ensure_session_access(session_key, initiator)
        messages = await self._session_load_messages(session_key)
        event_log = await self._session_load_event_log(session_key, limit=limit)
        return {
            "ok": True,
            "payload": {
                "sessionKey": session_key,
                "scope": normalize_session_scope(meta.get("scope")),
                "messages": messages[-limit:],
                "eventLog": event_log,
            },
        }

    async def chat_summary(self, session_key: str, initiator: dict[str, Any] | None = None) -> dict[str, Any]:
        meta = await self._ensure_session_access(session_key, initiator)
        summary, summary_upto = await self._session_load_summary(session_key)
        title = await self._session_load_title(session_key)
        return {
            "ok": True,
            "payload": {
                "sessionKey": session_key,
                "scope": normalize_session_scope(meta.get("scope")),
                "title": title,
                "summary": summary,
                "summaryUpTo": summary_upto,
                "hasSummary": bool(summary.strip()),
            },
        }

    async def chat_sessions_list(self, limit: int = 200, initiator: dict[str, Any] | None = None) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        if hasattr(self.sessions, "list_sessions"):
            list_fn = getattr(self.sessions, "list_sessions")
            try:
                loaded = await asyncio.to_thread(list_fn, limit, initiator)
            except TypeError:
                loaded = await asyncio.to_thread(list_fn, limit)
            if isinstance(loaded, list):
                rows = [item for item in loaded if isinstance(item, dict)]
        if not rows:
            rows = [{"sessionKey": "main", "title": "", "scope": "shared", "updatedAtMs": 0, "messageCount": 0}]
        has_main = any(str(item.get("sessionKey", "")).strip() == "main" for item in rows)
        if not has_main:
            rows.append({"sessionKey": "main", "title": "", "scope": "shared", "updatedAtMs": 0, "messageCount": 0})
        rows = sorted(rows, key=lambda item: int(item.get("updatedAtMs", 0) or 0), reverse=True)
        return {
            "ok": True,
            "payload": {
                "sessions": rows[: max(1, min(limit, 2000))],
            },
        }

    async def chat_session_create(
        self,
        session_key: str | None = None,
        *,
        scope: str = "shared",
        initiator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = (session_key or "").strip()
        if not key:
            key = time.strftime("chat-%Y%m%d-%H%M%S")
        normalized_scope = normalize_session_scope(scope)
        if normalized_scope == "private" and normalize_session_author(initiator) is None:
            raise PermissionError("private conversation requires an authenticated owner")
        created = await self._session_create(key, scope=normalized_scope, initiator=initiator)
        sessions = await self.chat_sessions_list(initiator=initiator)
        return {
            "ok": True,
            "payload": {
                "session": created,
                "sessions": sessions.get("payload", {}).get("sessions", []),
            },
        }

    async def chat_session_rename(
        self,
        *,
        session_key: str,
        title: str,
        initiator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self._ensure_session_access(session_key, initiator)
        key = (session_key or "").strip() or "main"
        normalized_title = str(title or "").strip()

        session_payload: dict[str, Any] = {"sessionKey": key, "title": normalized_title}
        if hasattr(self.sessions, "rename_session"):
            renamed = await asyncio.to_thread(getattr(self.sessions, "rename_session"), key, normalized_title)
            if isinstance(renamed, dict):
                session_payload = renamed
        elif hasattr(self.sessions, "save_session_title"):
            saved = await asyncio.to_thread(getattr(self.sessions, "save_session_title"), key, normalized_title)
            session_payload["title"] = str(saved or "").strip()

        sessions = await self.chat_sessions_list(limit=300, initiator=initiator)
        return {
            "ok": True,
            "payload": {
                "session": session_payload,
                "sessions": sessions.get("payload", {}).get("sessions", []),
            },
        }

    async def chat_session_set_scope(
        self,
        *,
        session_key: str,
        scope: str,
        initiator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = (session_key or "").strip() or "main"
        normalized_scope = normalize_session_scope(scope)
        await self._ensure_session_access(key, initiator)
        session_payload = await self._session_set_scope(
            key,
            scope=normalized_scope,
            initiator=initiator,
        )
        sessions = await self.chat_sessions_list(limit=300, initiator=initiator)
        return {
            "ok": True,
            "payload": {
                "session": session_payload,
                "sessions": sessions.get("payload", {}).get("sessions", []),
            },
        }

    async def chat_usage(self, session_key: str, initiator: dict[str, Any] | None = None) -> dict[str, Any]:
        meta = await self._ensure_session_access(session_key, initiator)
        if hasattr(self.sessions, "load_usage"):
            usage = await asyncio.to_thread(getattr(self.sessions, "load_usage"), session_key)
            if isinstance(usage, dict):
                input_tokens = int(usage.get("input", 0) or 0)
                output_tokens = int(usage.get("output", 0) or 0)
                total_tokens = int(usage.get("total", input_tokens + output_tokens) or 0)
                return {
                    "ok": True,
                    "payload": {
                        "sessionKey": session_key,
                        "scope": normalize_session_scope(meta.get("scope")),
                        "input": input_tokens,
                        "output": output_tokens,
                        "total": total_tokens,
                    },
                }

        messages = await self._session_load_messages(session_key)
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        for message in messages:
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            input_tokens += int(usage.get("input", 0) or 0)
            output_tokens += int(usage.get("output", 0) or 0)
            total_tokens += int(usage.get("totalTokens", usage.get("total", 0)) or 0)
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens
        return {
            "ok": True,
            "payload": {
                "sessionKey": session_key,
                "scope": normalize_session_scope(meta.get("scope")),
                "input": input_tokens,
                "output": output_tokens,
                "total": total_tokens,
            },
        }

    async def vendors_list(self) -> dict[str, Any]:
        return {
            "ok": True,
            "payload": {
                "vendors": self.vendors.list(include_secret=False),
            },
        }

    async def vendor_upsert(self, payload: dict[str, Any]) -> dict[str, Any]:
        vendor = await asyncio.to_thread(self.vendors.upsert, payload)
        return {
            "ok": True,
            "payload": {
                "vendor": vendor,
            },
        }

    async def vendor_delete(self, vendor_id: str) -> dict[str, Any]:
        deleted = await asyncio.to_thread(self.vendors.delete, vendor_id)
        return {
            "ok": True,
            "payload": {
                "vendorId": vendor_id,
                "deleted": deleted,
            },
        }

    async def vendor_models(self, vendor_id: str) -> dict[str, Any]:
        result = await asyncio.to_thread(self.vendors.list_models_from_endpoint, vendor_id)
        return {"ok": True, "payload": result}

    @staticmethod
    def _normalize_vendor(value: str | None) -> str:
        normalized = str(value or "openai").strip().lower()
        if normalized in {"claude", "anthropic"}:
            return "anthropic"
        return normalized or "openai"

    @staticmethod
    def _default_base_url_for_vendor(vendor: str) -> str | None:
        if vendor == "openai":
            return "https://api.openai.com/v1"
        if vendor == "xai":
            return "https://api.x.ai/v1"
        if vendor == "anthropic":
            return "https://api.anthropic.com/v1"
        return None

    def _default_vendor_entries(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "openai",
                "label": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "models_endpoint": "/models",
                "api_key_env": "OPENAI_API_KEY",
                "enabled": True,
                "source": "default",
                "models": [
                    {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini"},
                    {"id": "gpt-4.1", "label": "GPT-4.1"},
                    {"id": "o4-mini", "label": "o4-mini"},
                ],
                "capabilities": dict(DEFAULT_CAPABILITIES),
            },
            {
                "id": "xai",
                "label": "xAI",
                "base_url": "https://api.x.ai/v1",
                "models_endpoint": "/models",
                "api_key_env": "XAI_API_KEY",
                "enabled": True,
                "source": "default",
                "models": [
                    {"id": "grok-4", "label": "Grok 4"},
                    {"id": "grok-3-mini", "label": "Grok 3 mini"},
                ],
                "capabilities": dict(DEFAULT_CAPABILITIES),
            },
            {
                "id": "anthropic",
                "label": "Anthropic Claude",
                "base_url": "https://api.anthropic.com/v1",
                "models_endpoint": "/models",
                "api_key_env": "ANTHROPIC_API_KEY",
                "enabled": False,
                "source": "default",
                "reason": "not wired in this replica runtime yet",
                "models": [
                    {"id": "claude-3-7-sonnet", "label": "Claude 3.7 Sonnet"},
                ],
                "capabilities": dict(DEFAULT_CAPABILITIES),
            },
        ]

    def _api_key_for_vendor(self, vendor: str, explicit: str | None = None) -> str | None:
        if explicit and explicit.strip():
            return explicit.strip()
        from_store = self.vendors.resolve_api_key(vendor)
        if from_store:
            return from_store
        return os.getenv("REPLICA_MODEL_API_KEY") or self.config.model.api_key

    @staticmethod
    def _model_client_cache_key(cfg: ModelConfig) -> str:
        return "|".join(
            [
                str(cfg.provider or ""),
                str(cfg.base_url or ""),
                str(cfg.api_key or ""),
                str(cfg.model or ""),
                str(cfg.temperature),
                str(cfg.max_output_tokens),
                str(cfg.timeout_seconds),
            ]
        )

    def _client_for_config(self, cfg: ModelConfig) -> OpenAIModelClient:
        key = self._model_client_cache_key(cfg)
        existing = self._model_clients.get(key)
        if existing is not None:
            return existing
        client = OpenAIModelClient(cfg)
        self._model_clients[key] = client
        return client

    def _resolve_runtime_model_config(self, overrides: dict[str, Any] | None) -> ModelConfig:
        payload = overrides or {}
        vendor = self._normalize_vendor(payload.get("provider") or self.config.model.provider)
        vendor_entry = self.vendors.get(vendor, include_secret=True)
        if vendor_entry is None:
            raise ValueError(f"vendor not configured: {vendor}")
        if not bool(vendor_entry.get("enabled", True)):
            raise ValueError(f"vendor {vendor!r} is disabled")

        explicit_model = str(payload.get("model", "")).strip()
        if explicit_model:
            model_name = explicit_model
        elif vendor != self._normalize_vendor(self.config.model.provider):
            vendor_models = list(vendor_entry.get("models", [])) if isinstance(vendor_entry.get("models", []), list) else []
            first_model = ""
            if vendor_models and isinstance(vendor_models[0], dict):
                first_model = str(vendor_models[0].get("id", "")).strip()
            model_name = first_model or self.config.model.model
        else:
            model_name = self.config.model.model
        raw_base_url = str(payload.get("base_url", "")).strip()
        if raw_base_url:
            base_url = raw_base_url
        elif str(vendor_entry.get("base_url", "")).strip():
            base_url = str(vendor_entry.get("base_url", "")).strip()
        elif vendor == self._normalize_vendor(self.config.model.provider):
            base_url = self.config.model.base_url or self._default_base_url_for_vendor(vendor)
        else:
            base_url = self._default_base_url_for_vendor(vendor)
        api_key = self._api_key_for_vendor(vendor, str(payload.get("api_key", "")).strip() or None)
        if not api_key:
            raise ValueError(
                f"missing API key for vendor {vendor!r}. Set REPLICA_MODEL_API_KEY or the vendor-specific key env var."
            )

        temperature_raw = payload.get("temperature")
        if isinstance(temperature_raw, (int, float)):
            temperature = float(temperature_raw)
        else:
            temperature = self.config.model.temperature

        max_tokens_raw = payload.get("max_output_tokens")
        max_output_tokens = int(max_tokens_raw) if isinstance(max_tokens_raw, int) and max_tokens_raw > 0 else self.config.model.max_output_tokens

        return ModelConfig(
            provider=vendor,
            base_url=base_url,
            api_key=api_key,
            model=model_name,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            timeout_seconds=self.config.model.timeout_seconds,
        )

    async def start_run(
        self,
        *,
        session_key: str,
        message: str,
        attachments: list[dict[str, Any]] | None = None,
        thinking: str | None,
        verbosity: str | None,
        model_overrides: dict[str, Any] | None,
        tool_allowlist: list[str] | None,
        timeout_ms: int | None,
        idempotency_key: str | None,
        initiator: dict[str, Any] | None = None,
        selected_profile: str | None = None,
    ) -> dict[str, Any]:
        run_id = (idempotency_key or str(uuid.uuid4())).strip()
        if not run_id:
            run_id = str(uuid.uuid4())
        meta = await self._ensure_session_access(session_key, initiator)
        queued_response: dict[str, Any] | None = None
        emit_queue_state = False
        kick_queue = False
        started_task: asyncio.Task[None] | None = None
        started_agent_runtime: dict[str, Any] | None = None
        started_profile_key = str(selected_profile or "").strip()

        async with self._active_lock:
            existing = self._active_runs.get(run_id)
            if existing:
                return {
                    "ok": True,
                    "payload": {
                        "runId": run_id,
                        "status": "in_flight",
                        "agentRuntime": (
                            dict(existing.agent_runtime)
                            if isinstance(existing.agent_runtime, dict)
                            else agent_runtime
                        ),
                    },
                }
            queue = await self._session_load_queue(session_key)
            existing_queued_idx = next(
                (idx for idx, item in enumerate(queue) if str(item.get("id", "") or "").strip() == run_id),
                -1,
            )
            if existing_queued_idx >= 0:
                return {
                    "ok": True,
                    "payload": {
                        "runId": run_id,
                        "queueItemId": run_id,
                        "queuePosition": existing_queued_idx + 1,
                        "status": "queued",
                        "queue": self._queue_payload_from_items(
                            session_key,
                            scope=str(meta.get("scope") or "shared"),
                            items=queue,
                        ),
                    },
                }
            active_for_session = self._active_run_for_session_unlocked(session_key)
            if active_for_session is not None or queue:
                queued_item = {
                    "id": run_id,
                    "message": str(message or ""),
                    "attachments": attachments if isinstance(attachments, list) else [],
                    "attachmentsCount": len(attachments or []),
                    "author": normalize_session_author(initiator),
                    "initiator": dict(initiator) if isinstance(initiator, dict) else None,
                    "createdAtMs": int(time.time() * 1000),
                    "thinking": str(thinking or self.config.agent.thinking or "default").strip() or "default",
                    "verbosity": str(verbosity or self.config.agent.verbosity or "minimal").strip() or "minimal",
                    "selectedProfile": str(selected_profile or "").strip(),
                    "modelOverrides": dict(model_overrides) if isinstance(model_overrides, dict) else {},
                    "toolAllowlist": list(tool_allowlist or []),
                    "timeoutMs": int(timeout_ms or 0) if isinstance(timeout_ms, int) and timeout_ms > 0 else 0,
                }
                queue.append(queued_item)
                queue = await self._session_save_queue(session_key, queue)
                queued_response = {
                    "ok": True,
                    "payload": {
                        "runId": run_id,
                        "queueItemId": run_id,
                        "queuePosition": len(queue),
                        "status": "queued",
                        "queue": self._queue_payload_from_items(
                            session_key,
                            scope=str(meta.get("scope") or "shared"),
                            items=queue,
                        ),
                    },
                }
                emit_queue_state = True
                kick_queue = active_for_session is None
            else:
                started_agent_runtime = await self.agent_runtime(
                    initiator=initiator,
                    selected_profile=selected_profile,
                    requested_tool_allowlist=tool_allowlist,
                )
                started_profile_key = str(
                    (
                        ((started_agent_runtime.get("activeProfile") or {}) if isinstance(started_agent_runtime.get("activeProfile"), dict) else {})
                        .get("key")
                    )
                    or selected_profile
                    or ""
                ).strip()

                started_task = asyncio.create_task(
                    self._execute_run(
                        run_id=run_id,
                        session_key=session_key,
                        message=message,
                        attachments=attachments,
                        thinking=thinking,
                        verbosity=verbosity,
                        model_overrides=model_overrides,
                        tool_allowlist=tool_allowlist,
                        timeout_ms=timeout_ms,
                        initiator=initiator,
                        selected_profile=started_profile_key,
                        agent_runtime=started_agent_runtime,
                    ),
                    name=f"run:{run_id}",
                )
                started_at_ms = int(time.time() * 1000)
                self._active_runs[run_id] = ActiveRun(
                    run_id=run_id,
                    session_key=session_key,
                    task=started_task,
                    started_at_ms=started_at_ms,
                    initiator=(dict(initiator) if isinstance(initiator, dict) else None),
                    selected_profile=started_profile_key,
                    agent_runtime=started_agent_runtime,
                )
                self._run_started_at[run_id] = started_at_ms

        if queued_response is not None:
            if emit_queue_state:
                await self._emit_queue_state(session_key)
            if kick_queue:
                await self._start_queued_turn(session_key)
            return queued_response

        if started_task is None or started_agent_runtime is None:
            raise RuntimeError("failed to initialize run")

        started_task.add_done_callback(lambda _: asyncio.create_task(self._finalize_run(run_id)))

        return {
            "ok": True,
            "payload": {
                "runId": run_id,
                "status": "started",
                "agentRuntime": started_agent_runtime,
            },
        }

    async def run_once(
        self,
        *,
        session_key: str,
        message: str,
        attachments: list[dict[str, Any]] | None = None,
        thinking: str | None = None,
        verbosity: str | None = None,
        model_overrides: dict[str, Any] | None = None,
        tool_allowlist: list[str] | None = None,
        timeout_ms: int | None = None,
        run_id: str | None = None,
        initiator: dict[str, Any] | None = None,
        selected_profile: str | None = None,
    ) -> dict[str, Any]:
        final_run_id = str(run_id or uuid.uuid4()).strip() or str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[dict[str, Any]] = loop.create_future()
        agent_runtime = await self.agent_runtime(
            initiator=initiator,
            selected_profile=selected_profile,
            requested_tool_allowlist=tool_allowlist,
        )
        selected_profile_key = str(
            (((agent_runtime.get("activeProfile") or {}) if isinstance(agent_runtime.get("activeProfile"), dict) else {}).get("key"))
            or ""
        ).strip()

        async with self._active_lock:
            existing = self._active_runs.get(final_run_id)
            if existing:
                raise ValueError(f"run already active: {final_run_id}")
            task = asyncio.create_task(
                self._execute_run(
                    run_id=final_run_id,
                    session_key=session_key,
                    message=message,
                    attachments=attachments,
                    thinking=thinking,
                    verbosity=verbosity,
                    model_overrides=model_overrides,
                    tool_allowlist=tool_allowlist,
                    timeout_ms=timeout_ms,
                    initiator=initiator,
                    selected_profile=selected_profile_key,
                    agent_runtime=agent_runtime,
                ),
                name=f"run:{final_run_id}",
            )
            started_at_ms = int(time.time() * 1000)
            self._active_runs[final_run_id] = ActiveRun(
                run_id=final_run_id,
                session_key=session_key,
                task=task,
                started_at_ms=started_at_ms,
                initiator=(dict(initiator) if isinstance(initiator, dict) else None),
                selected_profile=selected_profile_key,
                agent_runtime=agent_runtime,
            )
            self._run_started_at[final_run_id] = started_at_ms
            self._run_waiters[final_run_id] = waiter
            self._run_generated_files[final_run_id] = []

        task.add_done_callback(lambda _: asyncio.create_task(self._finalize_run(final_run_id)))

        try:
            outcome = await waiter
            await asyncio.gather(task, return_exceptions=True)
        finally:
            if not waiter.done():
                waiter.cancel()
        return {
            "runId": final_run_id,
            "sessionKey": session_key,
            "agentRuntime": agent_runtime,
            **outcome,
        }

    async def abort(
        self,
        *,
        session_key: str,
        run_id: str | None,
        initiator: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self._ensure_session_access(session_key, initiator)
        aborted: list[str] = []

        async with self._active_lock:
            if run_id:
                run = self._active_runs.get(run_id)
                if run and run.session_key == session_key:
                    run.task.cancel()
                    aborted.append(run_id)
            else:
                for active in self._active_runs.values():
                    if active.session_key == session_key:
                        active.task.cancel()
                        aborted.append(active.run_id)

        for cancelled_run in aborted:
            await self._emit_chat_event(
                {
                    "runId": cancelled_run,
                    "sessionKey": session_key,
                    "seq": self._next_seq(cancelled_run),
                    "state": "aborted",
                    "errorMessage": "aborted by user",
                }
            )

        return {
            "ok": True,
            "payload": {
                "aborted": bool(aborted),
                "runIds": aborted,
            },
        }

    async def _finalize_run(self, run_id: str) -> None:
        finished_run: ActiveRun | None = None
        async with self._active_lock:
            finished_run = self._active_runs.pop(run_id, None)
            self._run_started_at.pop(run_id, None)
            self._run_seq.pop(run_id, None)
            self._run_generated_files.pop(run_id, None)
            waiter = self._run_waiters.pop(run_id, None)
        if waiter is not None and not waiter.done():
            waiter.set_result(
                {
                    "state": "error",
                    "errorMessage": "run finished without a terminal state",
                    "message": None,
                }
            )
        if finished_run is not None:
            await self._start_queued_turn(finished_run.session_key)

    async def _execute_run(
        self,
        *,
        run_id: str,
        session_key: str,
        message: str,
        attachments: list[dict[str, Any]] | None,
        thinking: str | None,
        verbosity: str | None,
        model_overrides: dict[str, Any] | None,
        tool_allowlist: list[str] | None,
        timeout_ms: int | None,
        initiator: dict[str, Any] | None,
        selected_profile: str | None,
        agent_runtime: dict[str, Any] | None,
    ) -> None:
        timeout_seconds = (
            max(1.0, float(timeout_ms) / 1000.0)
            if isinstance(timeout_ms, int) and timeout_ms > 0
            else (self.config.model.timeout_seconds + 15.0)
        )
        resolved_agent_runtime = agent_runtime if isinstance(agent_runtime, dict) else await self.agent_runtime(
            initiator=initiator,
            selected_profile=selected_profile,
            requested_tool_allowlist=tool_allowlist,
        )
        effective_runtime = (
            dict(resolved_agent_runtime.get("effective", {}))
            if isinstance(resolved_agent_runtime.get("effective"), dict)
            else {}
        )
        effective_thinking = str(thinking or effective_runtime.get("thinking") or "default").strip().lower() or "default"
        effective_verbosity = (
            str(verbosity or effective_runtime.get("verbosity") or "minimal").strip().lower() or "minimal"
        )
        merged_model_overrides: dict[str, Any] = {}
        default_vendor = str(effective_runtime.get("provider") or "").strip()
        default_model = str(effective_runtime.get("model") or "").strip()
        if default_vendor:
            merged_model_overrides["provider"] = default_vendor
        if default_model:
            merged_model_overrides["model"] = default_model
        if isinstance(model_overrides, dict):
            for key, value in model_overrides.items():
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                merged_model_overrides[key] = value
        effective_model_overrides = merged_model_overrides or None

        user_text = message.strip()
        attachment_payloads = self._normalize_attachments_payload(attachments)
        await self._emit_agent_loop_event(
            run_id=run_id,
            session_key=session_key,
            phase="run_start",
            data={
                "hasMessage": bool(user_text),
                "attachmentCount": len(attachment_payloads),
                "thinking": effective_thinking,
                "verbosity": effective_verbosity,
                "agentRuntime": {
                    "profileKey": str(
                        (((resolved_agent_runtime.get("activeProfile") or {}) if isinstance(resolved_agent_runtime.get("activeProfile"), dict) else {}).get("key"))
                        or ""
                    ).strip(),
                    "provider": default_vendor or self._normalize_vendor(self.config.model.provider),
                    "model": default_model or self.config.model.model,
                    "toolAllowlist": list(effective_runtime.get("toolAllowlist", []))
                    if isinstance(effective_runtime.get("toolAllowlist"), list)
                    else [],
                    "diagnostics": (
                        dict(resolved_agent_runtime.get("diagnostics", {}))
                        if isinstance(resolved_agent_runtime.get("diagnostics"), dict)
                        else {}
                    ),
                },
            },
        )
        attachment_context = await self._prepare_attachments_context(
            run_id=run_id,
            session_key=session_key,
            attachments=attachment_payloads,
        )

        if not user_text and not attachment_context["items"]:
            await self._emit_agent_loop_event(
                run_id=run_id,
                session_key=session_key,
                phase="rejected",
                data={"reason": "message_required"},
            )
            await self._emit_chat_event(
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": self._next_seq(run_id),
                    "state": "error",
                    "errorMessage": "message required",
                }
            )
            return

        attachment_names = [str(item.get("name", "")).strip() for item in attachment_context["items"] if item.get("name")]
        if user_text:
            user_text_for_session = user_text
        else:
            user_text_for_session = "Please analyze the attached files."
        if attachment_names:
            user_text_for_session += "\n\n[Attachments: " + ", ".join(attachment_names[:8]) + "]"

        message_author = normalize_session_author(initiator)
        user_session_message = SessionMessage(
            role="user",
            content=make_text_content(user_text_for_session),
            timestamp=int(time.time() * 1000),
            author=message_author,
            context_scope="shared",
            owner=message_author,
            meta={
                "runId": run_id,
                "attachments": [self._compact_attachment_entry(item) for item in attachment_context["items"]],
            },
        )
        await self._session_append(
            session_key,
            user_session_message,
        )
        await self._emit_chat_event(
            {
                "runId": run_id,
                "sessionKey": session_key,
                "seq": self._next_seq(run_id),
                "state": "accepted",
                "message": user_session_message.to_dict(),
            }
        )
        await self._record_memory_artifact(
            session_key=session_key,
            run_id=run_id,
            kind="user_message",
            title="User message",
            text=user_text_for_session,
            metadata={
                "attachments": [dict(item) for item in attachment_context["items"]],
                **({"author": dict(message_author)} if message_author else {}),
            },
        )
        for item in attachment_context["items"]:
            extracted = str(item.get("extracted", "")).strip()
            if not extracted:
                continue
            await self._record_memory_artifact(
                session_key=session_key,
                run_id=run_id,
                kind="attachment",
                title=str(item.get("name") or "attachment"),
                text=extracted[:8000],
                metadata={
                    "path": item.get("path"),
                    "downloadUrl": item.get("downloadUrl"),
                    "mimeType": item.get("mimeType"),
                    "sizeBytes": item.get("sizeBytes"),
                    "summary": self._attachment_memory_summary(item),
                },
            )

        model_messages = await self._build_model_messages(
            session_key,
            effective_thinking,
            effective_verbosity,
            agent_runtime=resolved_agent_runtime,
        )
        attachment_prompt = str(attachment_context.get("prompt", "")).strip()
        attachment_model_content = attachment_context.get("modelContent")
        if attachment_prompt:
            model_messages.append({"role": "system", "content": attachment_prompt})
        try:
            await asyncio.wait_for(
                self._run_steps(
                    run_id=run_id,
                    session_key=session_key,
                    model_messages=model_messages,
                    thinking=effective_thinking,
                    model_overrides=effective_model_overrides,
                    tool_allowlist=(
                        list(effective_runtime.get("toolAllowlist", []))
                        if isinstance(effective_runtime.get("toolAllowlist"), list)
                        else tool_allowlist
                    ),
                    initiator=initiator,
                    agent_runtime=resolved_agent_runtime,
                    attachment_model_content=attachment_model_content if isinstance(attachment_model_content, list) else None,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            await self._emit_agent_loop_event(
                run_id=run_id,
                session_key=session_key,
                phase="timeout",
                data={"timeoutSeconds": round(timeout_seconds, 2)},
            )
            await self._emit_chat_event(
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": self._next_seq(run_id),
                    "state": "error",
                    "errorMessage": "run timed out",
                }
            )
        except asyncio.CancelledError:
            await self._emit_agent_loop_event(
                run_id=run_id,
                session_key=session_key,
                phase="aborted",
                data={"reason": "user_abort"},
            )
            await self._emit_chat_event(
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": self._next_seq(run_id),
                    "state": "aborted",
                    "errorMessage": "aborted",
                }
            )
            raise
        except Exception as exc:
            self.log.exception("run failed: %s", exc)
            await self._emit_agent_loop_event(
                run_id=run_id,
                session_key=session_key,
                phase="error",
                data={"message": str(exc)},
            )
            await self._emit_chat_event(
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": self._next_seq(run_id),
                    "state": "error",
                    "errorMessage": str(exc),
                }
            )

    @classmethod
    def _safe_attachment_name(cls, raw_name: str, fallback: str) -> str:
        candidate = cls._ATTACHMENT_NAME_RE.sub("_", (raw_name or "").strip()).strip("._")
        if not candidate:
            candidate = fallback
        if len(candidate) > 120:
            stem, dot, suffix = candidate.rpartition(".")
            if dot and suffix:
                candidate = (stem[:100] or "file") + "." + suffix[:18]
            else:
                candidate = candidate[:120]
        return candidate or fallback

    def _normalize_attachments_payload(self, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list):
            return []
        normalized: list[dict[str, Any]] = []
        for entry in raw[:8]:
            if not isinstance(entry, dict):
                continue
            data = entry.get("data")
            if not isinstance(data, str) or not data.strip():
                continue
            name = str(entry.get("name", "")).strip()
            mime_type = str(entry.get("type", "")).strip().lower()
            size = int(entry.get("size", 0) or 0)
            normalized.append(
                {
                    "name": name,
                    "mimeType": mime_type,
                    "sizeBytes": max(0, size),
                    "data": data.strip(),
                }
            )
        return normalized

    async def _prepare_attachments_context(
        self,
        *,
        run_id: str,
        session_key: str,
        attachments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not attachments:
            return {"items": [], "prompt": "", "modelContent": []}

        items: list[dict[str, Any]] = []
        model_content: list[dict[str, Any]] = []
        for index, attachment in enumerate(attachments, start=1):
            encoded = str(attachment.get("data", "")).strip()
            try:
                blob = base64.b64decode(encoded, validate=True)
            except Exception:
                blob = b""
            if not blob:
                continue
            if len(blob) > 10 * 1024 * 1024:
                continue

            default_name = f"attachment_{index}"
            safe_name = self._safe_attachment_name(str(attachment.get("name", "")), default_name)
            mime_type = str(attachment.get("mimeType", "")).strip().lower() or "application/octet-stream"
            stored = await self.media_store.store_bytes(
                session_key=session_key,
                run_id=run_id,
                category="uploads",
                filename=safe_name,
                payload=blob,
                mime_type=mime_type,
            )
            target = stored.local_path

            extracted = ""
            try:
                parsed = await self.tools.execute(
                    "resource.read",
                    {"target": str(target), "max_chars": 12000, "transcribe": False},
                )
                extracted = self._attachment_extracted_text(parsed, max_chars=3500)
            except Exception as exc:
                extracted = f"[attachment parsing error] {exc}"

            items.append(
                {
                    "name": safe_name,
                    "mimeType": mime_type,
                    "sizeBytes": int(attachment.get("sizeBytes", len(blob)) or len(blob)),
                    "path": str(target),
                    "downloadUrl": stored.download_url,
                    "localUrl": stored.local_url,
                    "s3Url": stored.s3_url,
                    "s3Key": stored.s3_key,
                    "relativePath": stored.relative_path,
                    "extracted": extracted,
                }
            )
            if mime_type.startswith("image/"):
                model_content.append(
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{encoded}",
                    }
                )
            else:
                model_content.append(
                    {
                        "type": "input_file",
                        "filename": safe_name,
                        "file_data": encoded,
                    }
                )

        if not items:
            return {"items": [], "prompt": "", "modelContent": []}

        lines = [
            "Current user turn includes uploaded attachments.",
            "Use the extracted context and attached file payloads; never reveal internal file paths or storage URLs.",
        ]
        for idx, item in enumerate(items, start=1):
            lines.append(
                f"Attachment {idx}: {item['name']} | mime={item.get('mimeType') or 'unknown'} | size={item.get('sizeBytes', 0)} bytes"
            )
            extracted = str(item.get("extracted", "")).strip()
            if extracted:
                lines.append("Extracted:")
                lines.append(extracted[:4000])
            lines.append("")
        prompt = "\n".join(lines).strip()
        if len(prompt) > 24000:
            prompt = prompt[:24000].rstrip() + "\n...[attachments context truncated]"
        return {"items": items, "prompt": prompt, "modelContent": model_content}

    @staticmethod
    def _attachment_extracted_text(parsed: Any, max_chars: int = 3500) -> str:
        if isinstance(parsed, dict):
            kind = str(parsed.get("kind", "")).strip()
            if isinstance(parsed.get("text"), str) and parsed.get("text", "").strip():
                text = str(parsed["text"]).strip()
                return (f"[{kind or 'resource'}]\n" + text)[:max_chars]
            summary_parts: list[str] = []
            for key in ("kind", "path", "title", "format", "mime", "duration_seconds", "size"):
                if key in parsed and parsed.get(key) not in (None, "", {}):
                    summary_parts.append(f"{key}: {parsed.get(key)}")
            if "rows" in parsed and isinstance(parsed.get("rows"), list):
                summary_parts.append(f"rows: {len(parsed.get('rows') or [])}")
            if summary_parts:
                return "\n".join(summary_parts)[:max_chars]
            try:
                return json.dumps(parsed, ensure_ascii=False, default=str)[:max_chars]
            except Exception:
                return str(parsed)[:max_chars]
        if isinstance(parsed, str):
            return parsed[:max_chars]
        try:
            return json.dumps(parsed, ensure_ascii=False, default=str)[:max_chars]
        except Exception:
            return str(parsed)[:max_chars]

    @staticmethod
    def _attachment_memory_summary(item: dict[str, Any], max_chars: int = 240) -> str:
        extracted = str(item.get("extracted", "")).strip()
        if extracted:
            compact = re.sub(r"\s+", " ", extracted).strip()
            if len(compact) > max_chars:
                compact = compact[: max_chars - 3].rstrip() + "..."
            return compact
        mime_type = str(item.get("mimeType", "")).strip() or "unknown"
        size_bytes = int(item.get("sizeBytes", 0) or 0)
        return f"{mime_type}, {size_bytes} bytes"

    @classmethod
    def _compact_attachment_entry(cls, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(item.get("name", "")).strip(),
            "mimeType": str(item.get("mimeType", "")).strip(),
            "sizeBytes": int(item.get("sizeBytes", 0) or 0),
            "downloadUrl": str(item.get("downloadUrl", "")).strip(),
            "summary": cls._attachment_memory_summary(item),
        }

    @staticmethod
    def _compact_generated_file_entry(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(item.get("name", "")).strip(),
            "path": str(item.get("path", "")).strip(),
            "downloadUrl": str(item.get("downloadUrl", "")).strip(),
            "mimeType": str(item.get("mimeType", "")).strip(),
            "tool": str(item.get("tool", "")).strip(),
        }

    @staticmethod
    def _generated_file_markdown_links(items: list[dict[str, Any]], max_items: int = 4) -> str:
        lines: list[str] = []
        seen_urls: set[str] = set()
        for item in items[: max(1, max_items)]:
            if not isinstance(item, dict):
                continue
            download_url = str(item.get("downloadUrl", "")).strip()
            if not download_url or download_url in seen_urls:
                continue
            seen_urls.add(download_url)
            name = str(item.get("name", "")).strip() or "file"
            lines.append(f"- [{name}]({download_url})")
        if not lines:
            return ""
        return "Downloads:\n" + "\n".join(lines)

    async def _build_model_messages(
        self,
        session_key: str,
        thinking: str | None,
        verbosity: str | None,
        *,
        agent_runtime: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        history = await self._session_load_messages(session_key)
        resolved_agent_runtime = agent_runtime if isinstance(agent_runtime, dict) else {}
        active_profile = (
            dict(resolved_agent_runtime.get("activeProfile", {}))
            if isinstance(resolved_agent_runtime.get("activeProfile"), dict)
            else {}
        )
        effective_runtime = (
            dict(resolved_agent_runtime.get("effective", {}))
            if isinstance(resolved_agent_runtime.get("effective"), dict)
            else {}
        )
        workspace_profile = (
            dict(resolved_agent_runtime.get("workspaceProfile", {}))
            if isinstance(resolved_agent_runtime.get("workspaceProfile"), dict)
            else {}
        )

        verbosity_value = (verbosity or self.config.agent.verbosity or "minimal").strip().lower()
        system_parts = [self.config.agent.system_prompt]
        if verbosity_value in {"minimal", "low", "short"}:
            system_parts.append(
                "Response verbosity policy: minimal. Keep responses concise and action-first. "
                "Use the fewest words needed to be correct."
            )
        elif verbosity_value in {"normal", "balanced"}:
            system_parts.append(
                "Response verbosity policy: normal. Be concise but include essential context."
            )
        else:
            system_parts.append(
                "Response verbosity policy: detailed. Include additional explanation and tradeoffs."
            )
        system_parts.append(
            "Autonomy policy: execute the next best tool actions directly when they are low-risk and reversible "
            "(read/fetch/explore/analyze, API calls, code execution in workspace). Do not ask for permission at each "
            "iteration."
        )
        system_parts.append(
            "If existing tools are insufficient, you may create a new tool with tools.create. "
            "If a required Python package is missing and package installs are enabled, use packages.install."
        )
        system_parts.append(
            "When a user shares URLs or asks to inspect external resources, use web/resource tools directly. "
            "Do not claim lack of internet browsing if tools are available."
        )
        system_parts.append(
            "For HTTP APIs, prefer web.request (or web.fetch/resource.read/shell.run curl) instead of asking the user "
            "to run commands manually. Do not block on missing requests library."
        )
        system_parts.append(
            "Use vault.set / vault.get for credentials or sensitive values instead of leaving secrets in plain text files."
        )
        system_parts.append(
            "Do not answer that you cannot install packages as a reason to skip API actions when HTTP tools are available. "
            "Use available tools first."
        )
        system_parts.append(
            "Only ask the user when truly blocked by missing credentials, missing authorization, destructive side effects, "
            "or ambiguous high-impact decisions."
        )
        system_parts.append(
            "When tool outputs include a downloadUrl for generated files, always include that URL in your final answer "
            "as a markdown link so the user can download the artifact."
        )
        profile_prompt = str(active_profile.get("systemPrompt") or "").strip()
        if profile_prompt:
            system_parts.append("Active agent profile instructions:\n" + profile_prompt)
        profile_name = str(active_profile.get("name") or active_profile.get("key") or "").strip()
        if profile_name:
            system_parts.append(f"Active agent profile: {profile_name}.")
        if thinking:
            system_parts.append(f"Thinking level requested: {thinking}.")
        if effective_runtime:
            system_parts.append(
                "Resolved runtime defaults: "
                f"provider={str(effective_runtime.get('provider') or '').strip() or self._normalize_vendor(self.config.model.provider)}, "
                f"model={str(effective_runtime.get('model') or '').strip() or self.config.model.model}, "
                f"thinking={str(effective_runtime.get('thinking') or '').strip() or 'default'}, "
                f"verbosity={str(effective_runtime.get('verbosity') or '').strip() or 'minimal'}."
            )

        if not workspace_profile and self.workspace_profile_resolver is not None:
            try:
                workspace_profile = await asyncio.to_thread(self.workspace_profile_resolver)
            except Exception as exc:
                self.log.warning("workspace profile load failed: %s", exc)
                workspace_profile = {}
        specialty_prompt = str((workspace_profile or {}).get("specialtyPrompt", "")).strip()
        workspace_name = str((workspace_profile or {}).get("name", "")).strip()
        if workspace_name:
            system_parts.append(f"Workspace: {workspace_name}.")
        if specialty_prompt:
            system_parts.append("Workspace specialization:\n" + specialty_prompt)

        if self.config.skills.include_in_system_prompt:
            skills_prompt = build_skills_prompt(self.skills, self.config.skills.max_skill_chars)
            if skills_prompt:
                system_parts.append(skills_prompt)
        if self.workspace_skills_resolver is not None:
            try:
                workspace_skills = await asyncio.to_thread(self.workspace_skills_resolver)
            except Exception as exc:
                self.log.warning("workspace skills load failed: %s", exc)
                workspace_skills = []
            workspace_skills_prompt = self._build_workspace_skills_prompt(
                workspace_skills,
                max_chars=self.config.skills.max_skill_chars,
            )
            if workspace_skills_prompt:
                system_parts.append(workspace_skills_prompt)
        if self.integration_guidance_resolver is not None:
            try:
                guidance = await asyncio.to_thread(self.integration_guidance_resolver)
            except Exception as exc:
                self.log.warning("integration guidance load failed: %s", exc)
                guidance = ""
            if guidance:
                system_parts.append("Tenant integration guidance:\n" + guidance)
        runtime_tool_allowlist = (
            list(effective_runtime.get("toolAllowlist", []))
            if isinstance(effective_runtime.get("toolAllowlist"), list)
            else []
        )
        plugins_prompt = self._build_active_plugins_prompt(runtime_tool_allowlist)
        if plugins_prompt:
            system_parts.append(plugins_prompt)

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": "\n\n".join(system_parts),
            }
        ]

        history_items = self._extract_history_items(history)
        if self.config.agent.context_compaction_enabled:
            summary, _ = await self._session_load_summary(session_key)
            if summary:
                messages.append(
                    {
                        "role": "system",
                        "content": "Conversation memory summary:\n" + summary,
                    }
                )

            tail_items = self._last_interactions(history_items, self.config.agent.context_last_interactions)
            for item in tail_items:
                messages.append({"role": item["role"], "content": item["text"]})
        else:
            for item in history_items:
                messages.append({"role": item["role"], "content": item["text"]})

        return messages

    @staticmethod
    def _extract_history_items(history: list[dict[str, Any]]) -> list[dict[str, str]]:
        history_items: list[dict[str, str]] = []
        for item in history:
            role = str(item.get("role", "")).strip().lower()
            content_entries = item.get("content")
            text = ""
            if isinstance(content_entries, list):
                text = "\n".join(
                    str(entry.get("text", ""))
                    for entry in content_entries
                    if isinstance(entry, dict)
                ).strip()
            text = AgentConsoleBackend._append_message_artifact_hints(item, text)
            if not text:
                continue
            context_scope = normalize_session_context_scope(item.get("contextScope"))
            if context_scope == "personal":
                owner_label = AgentConsoleBackend._history_owner_label(item)
                prefix = f"[Private context for {owner_label}]" if owner_label else "[Private context]"
                text = f"{prefix}\n{text}"
            elif role == "user":
                author_label = AgentConsoleBackend._history_author_label(item)
                if author_label:
                    text = f"[User: {author_label}]\n{text}"
            if role in {"system", "user", "assistant"}:
                history_items.append({"role": role, "text": text})
        return history_items

    @staticmethod
    def _history_author_label(message: dict[str, Any]) -> str:
        author = normalize_session_author(message.get("author"))
        if not author:
            return ""
        display_name = str(author.get("displayName", "")).strip()
        email = str(author.get("email", "")).strip()
        if display_name and email and display_name.lower() != email.lower():
            return f"{display_name} ({email})"
        return display_name or email

    @staticmethod
    def _history_owner_label(message: dict[str, Any]) -> str:
        owner = normalize_session_author(message.get("owner"))
        if not owner:
            return ""
        display_name = str(owner.get("displayName", "")).strip()
        email = str(owner.get("email", "")).strip()
        if display_name and email and display_name.lower() != email.lower():
            return f"{display_name} ({email})"
        return display_name or email

    @staticmethod
    def _append_message_artifact_hints(message: dict[str, Any], text: str) -> str:
        base = str(text or "").strip()
        hint_lines: list[str] = []
        if "[Attachments:" not in base and "[Attachment paths]" not in base:
            attachments = message.get("attachments")
            if isinstance(attachments, list):
                for item in attachments[:4]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip() or "attachment"
                    summary = str(item.get("summary", "")).strip()
                    line = f"- {name}"
                    if summary:
                        line += f": {summary}"
                    hint_lines.append(line)
        generated_files = message.get("generatedFiles")
        if isinstance(generated_files, list):
            for item in generated_files[:4]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip() or "generated file"
                path = str(item.get("path", "")).strip()
                line = f"- {name}"
                if path:
                    line += f" ({path})"
                hint_lines.append(line)
        if not hint_lines:
            return base
        hint_block = "Files referenced in this turn:\n" + "\n".join(hint_lines)
        return f"{base}\n\n{hint_block}".strip()

    @staticmethod
    def _last_interactions(items: list[dict[str, str]], interaction_count: int) -> list[dict[str, str]]:
        if not items:
            return []
        count = max(1, int(interaction_count))
        user_indexes = [index for index, item in enumerate(items) if item.get("role") == "user"]
        if not user_indexes:
            keep_messages = min(len(items), count * 2)
            return items[-keep_messages:]

        start_user_pos = max(0, len(user_indexes) - count)
        start_index = user_indexes[start_user_pos]
        return items[start_index:]

    @staticmethod
    def _summarize_history_for_context(items: list[dict[str, str]], max_chars: int) -> str:
        if not items:
            return ""
        max_chars = max(800, max_chars)
        sampled = items
        if len(items) > 48:
            sampled = items[:12] + [{"role": "system", "text": "..."}] + items[-35:]

        lines: list[str] = []
        for item in sampled:
            role = item.get("role", "system")
            text = item.get("text", "").replace("\n", " ").strip()
            if not text:
                continue
            if role == "user":
                prefix = "User"
            elif role == "assistant":
                prefix = "Assistant"
            else:
                prefix = "System"
            snippet = text[:220]
            if len(text) > 220:
                snippet += "..."
            lines.append(f"- {prefix}: {snippet}")

        summary = "Older conversation summary (compacted context):\n" + "\n".join(lines)
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "\n...[summary truncated]"
        return summary

    @staticmethod
    def _build_workspace_skills_prompt(skills: list[dict[str, Any]] | None, max_chars: int) -> str:
        if not isinstance(skills, list):
            return ""
        lines = [
            "Workspace skill instructions (enabled for this workspace). "
            "Use these when relevant before asking user follow-ups:"
        ]
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            key = str(skill.get("key", "")).strip()
            name = str(skill.get("name", "")).strip() or key
            body = str(skill.get("bodyMarkdown", "")).strip()
            if not body:
                continue
            title = f"{name} ({key})" if key and key.lower() != name.lower() else (name or key)
            lines.append(f"\n## {title}")
            description = str(skill.get("description", "")).strip()
            if description:
                lines.append(description)
            lines.append(body)
        prompt = "\n".join(lines).strip()
        if not prompt:
            return ""
        limit = max(1000, int(max_chars or 0))
        if len(prompt) > limit:
            return prompt[:limit].rstrip() + "\n...[workspace skills truncated]"
        return prompt

    def _build_active_plugins_prompt(self, runtime_allowlist: list[str] | None) -> str:
        def _config_value_hint(key: str, value: Any) -> str:
            normalized_key = str(key or "").strip().lower()
            sensitive_markers = ("token", "secret", "password", "credential", "api_key", "apikey")
            if any(marker in normalized_key for marker in sensitive_markers):
                return "configured" if value not in (None, "", [], {}, ()) else "missing"
            if isinstance(value, str):
                text = value.strip()
                return text if text else "empty"
            if value is None:
                return "missing"
            if isinstance(value, bool):
                return "true" if value else "false"
            return str(value)

        allowed = {
            str(item).strip()
            for item in (runtime_allowlist or [])
            if str(item).strip()
        }
        if not allowed:
            return ""
        plugin_tools: dict[str, list[str]] = {}
        for tool_name in sorted(allowed):
            plugin_id = str(self.tools.plugin_id_for_tool(tool_name) or "").strip().lower()
            if not plugin_id:
                continue
            plugin_tools.setdefault(plugin_id, []).append(tool_name)
        if not plugin_tools:
            return ""
        plugin_by_id = {
            str(plugin.manifest.plugin_id or "").strip().lower(): plugin
            for plugin in self.active_plugins
        }
        lines = [
            "Active plugins available in this runtime. Prefer these plugin tools directly when the request matches their domain:"
        ]
        for plugin_id in sorted(plugin_tools.keys()):
            plugin = plugin_by_id.get(plugin_id)
            plugin_name = (
                str(plugin.manifest.name or "").strip()
                if plugin is not None
                else plugin_id
            ) or plugin_id
            plugin_description = (
                str(plugin.manifest.description or "").strip()
                if plugin is not None
                else ""
            )
            header = f"{plugin_name} ({plugin_id})"
            if plugin_description:
                lines.append(f"- {header}: {plugin_description}")
            else:
                lines.append(f"- {header}")
            runtime_config = dict(getattr(plugin, "runtime_config", {})) if plugin is not None else {}
            if runtime_config:
                config_bits = [
                    f"{str(key).strip()}={_config_value_hint(str(key), value)}"
                    for key, value in sorted(runtime_config.items(), key=lambda item: str(item[0]))
                    if str(key).strip()
                ]
                if config_bits:
                    lines.append("  config: " + ", ".join(config_bits))
            for tool_name in plugin_tools.get(plugin_id, []):
                try:
                    spec = self.tools.get(tool_name)
                    tool_description = str(spec.description or "").strip()
                except Exception:
                    tool_description = ""
                if tool_description:
                    lines.append(f"  - {tool_name}: {tool_description}")
                else:
                    lines.append(f"  - {tool_name}")
        return "\n".join(lines).strip()

    async def _run_steps(
        self,
        *,
        run_id: str,
        session_key: str,
        model_messages: list[dict[str, Any]],
        thinking: str | None = None,
        model_overrides: dict[str, Any] | None = None,
        tool_allowlist: list[str] | None = None,
        initiator: dict[str, Any] | None = None,
        agent_runtime: dict[str, Any] | None = None,
        attachment_model_content: list[dict[str, Any]] | None = None,
    ) -> None:
        resolved_agent_runtime = agent_runtime if isinstance(agent_runtime, dict) else {}
        effective_runtime = (
            dict(resolved_agent_runtime.get("effective", {}))
            if isinstance(resolved_agent_runtime.get("effective"), dict)
            else {}
        )
        runtime_model_cfg = self._resolve_runtime_model_config(model_overrides)
        model_client = self._client_for_config(runtime_model_cfg)
        max_steps = max(1, self.config.agent.max_steps)
        thinking_normalized = (thinking or "").strip().lower()
        if thinking_normalized == "high":
            max_steps += 6
        elif thinking_normalized in {"medium", "med"}:
            max_steps += 3
        permission_retry_count = 0
        runtime_allowlist = await self._effective_runtime_tool_allowlist(tool_allowlist, initiator=initiator)

        for step in range(max_steps):
            step_no = step + 1
            await self._emit_agent_loop_event(
                run_id=run_id,
                session_key=session_key,
                phase="step_start",
                step=step_no,
                max_steps=max_steps,
            )
            tools = self.tools.openai_tool_schemas_exact(runtime_allowlist)
            delta_buffer = ""
            last_delta_emit = time.monotonic()

            async def emit_delta(force: bool = False) -> None:
                nonlocal delta_buffer, last_delta_emit
                if not delta_buffer:
                    return
                now = time.monotonic()
                if not force and len(delta_buffer) < 36 and (now - last_delta_emit) < 0.15:
                    return
                chunk = delta_buffer
                delta_buffer = ""
                last_delta_emit = now
                await self._emit_chat_event(
                    {
                        "runId": run_id,
                        "sessionKey": session_key,
                        "seq": self._next_seq(run_id),
                        "state": "delta",
                        "message": {
                            "role": "assistant",
                            "content": [{"type": "text", "text": chunk}],
                        },
                    }
                )

            async def on_text_delta(text: str) -> None:
                nonlocal delta_buffer
                if not text:
                    return
                delta_buffer += text
                await emit_delta(force=False)

            await self._emit_agent_loop_event(
                run_id=run_id,
                session_key=session_key,
                phase="model_request",
                step=step_no,
                max_steps=max_steps,
                data={
                    "contextMessages": len(model_messages),
                    "toolSchemas": len(tools),
                    "model": runtime_model_cfg.model,
                    "provider": runtime_model_cfg.provider,
                },
            )
            response = await model_client.complete_stream(
                messages=model_messages,
                tools=tools,
                extra_user_content=attachment_model_content if step == 0 else None,
                on_text_delta=on_text_delta,
            )
            await emit_delta(force=True)
            model_messages.append(response.raw_message)
            await self._emit_agent_loop_event(
                run_id=run_id,
                session_key=session_key,
                phase="model_response",
                step=step_no,
                max_steps=max_steps,
                data={
                    "toolCalls": len(response.tool_calls),
                    "outputChars": len((response.text or "").strip()),
                    "stopReason": str(getattr(response, "stop_reason", "") or "").strip(),
                },
            )

            if response.tool_calls:
                tool_names: list[str] = []
                for call in response.tool_calls[:8]:
                    function = call.get("function") if isinstance(call.get("function"), dict) else {}
                    raw_name = str(function.get("name", "")).strip()
                    if raw_name:
                        tool_names.append(self.tools.resolve_tool_name(raw_name))
                await self._emit_agent_loop_event(
                    run_id=run_id,
                    session_key=session_key,
                    phase="tool_calls",
                    step=step_no,
                    max_steps=max_steps,
                    data={"count": len(response.tool_calls), "toolNames": tool_names},
                )
                for call in response.tool_calls:
                    await self._handle_tool_call(
                        run_id=run_id,
                        session_key=session_key,
                        model_messages=model_messages,
                        tool_call=call,
                        runtime_allowlist=runtime_allowlist,
                    )
                await self._emit_agent_loop_event(
                    run_id=run_id,
                    session_key=session_key,
                    phase="step_complete",
                    step=step_no,
                    max_steps=max_steps,
                    data={"continued": True, "reason": "awaiting_tool_results"},
                )
                continue

            final_text = response.text.strip()
            if not final_text:
                final_text = "(empty response)"

            if step < (max_steps - 1) and permission_retry_count < 2 and self._looks_like_permission_gate(final_text):
                permission_retry_count += 1
                await self._emit_agent_loop_event(
                    run_id=run_id,
                    session_key=session_key,
                    phase="permission_retry",
                    step=step_no,
                    max_steps=max_steps,
                    data={"retryCount": permission_retry_count},
                )
                model_messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Your previous assistant message asked the user for permission or delegated execution. "
                            "Continue autonomously now: choose and run tools directly. Only ask if blocked by missing "
                            "credentials/access or high-risk side effects."
                        ),
                    }
                )
                continue

            generated_files = self._run_generated_files.get(run_id, [])
            if generated_files:
                fallback_links = self._generated_file_markdown_links(generated_files)
                if fallback_links:
                    missing_urls = [
                        str(item.get("downloadUrl", "")).strip()
                        for item in generated_files
                        if isinstance(item, dict) and str(item.get("downloadUrl", "")).strip()
                    ]
                    # Only append fallback links when model text doesn't include any generated file URL.
                    if not any(url in final_text for url in missing_urls):
                        final_text = f"{final_text.rstrip()}\n\n{fallback_links}".strip()

            await self._emit_agent_loop_event(
                run_id=run_id,
                session_key=session_key,
                phase="finalizing",
                step=step_no,
                max_steps=max_steps,
                data={"finalChars": len(final_text)},
            )
            assistant_message = SessionMessage(
                role="assistant",
                content=make_text_content(final_text),
                timestamp=int(time.time() * 1000),
                context_scope="shared",
                meta={
                    "runId": run_id,
                    "stopReason": "stop",
                    "model": {
                        "provider": runtime_model_cfg.provider,
                        "name": runtime_model_cfg.model,
                    },
                    "usage": {
                        "input": int(response.usage.get("input", 0)),
                        "output": int(response.usage.get("output", 0)),
                        "totalTokens": int(response.usage.get("total", 0)),
                    },
                    "agentRuntime": {
                        "profileKey": str(
                            (((resolved_agent_runtime.get("activeProfile") or {}) if isinstance(resolved_agent_runtime.get("activeProfile"), dict) else {}).get("key"))
                            or ""
                        ).strip(),
                        "provider": runtime_model_cfg.provider,
                        "model": runtime_model_cfg.model,
                        "toolAllowlist": list(effective_runtime.get("toolAllowlist", []))
                        if isinstance(effective_runtime.get("toolAllowlist"), list)
                        else [],
                        "diagnostics": (
                            dict(resolved_agent_runtime.get("diagnostics", {}))
                            if isinstance(resolved_agent_runtime.get("diagnostics"), dict)
                            else {}
                        ),
                    },
                    "generatedFiles": [
                        dict(item) for item in self._run_generated_files.get(run_id, [])
                    ],
                },
            )
            await self._session_append(session_key, assistant_message)
            await self._record_memory_artifact(
                session_key=session_key,
                run_id=run_id,
                kind="assistant_final",
                title="Assistant final response",
                text=final_text,
                metadata={
                    "model": runtime_model_cfg.model,
                    "provider": runtime_model_cfg.provider,
                    "usage": assistant_message.meta.get("usage") if assistant_message.meta else {},
                },
            )

            await self._emit_chat_event(
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": self._next_seq(run_id),
                    "state": "final",
                    "message": assistant_message.to_dict(),
                }
            )
            await self._emit_agent_loop_event(
                run_id=run_id,
                session_key=session_key,
                phase="completed",
                step=step_no,
                max_steps=max_steps,
                data={
                    "inputTokens": int(response.usage.get("input", 0)),
                    "outputTokens": int(response.usage.get("output", 0)),
                    "totalTokens": int(response.usage.get("total", 0)),
                },
            )
            self._schedule_context_summary_refresh(session_key, model_client=model_client)
            return

        await self._emit_agent_loop_event(
            run_id=run_id,
            session_key=session_key,
            phase="max_steps_exceeded",
            step=max_steps,
            max_steps=max_steps,
        )
        await self._emit_chat_event(
            {
                "runId": run_id,
                "sessionKey": session_key,
                "seq": self._next_seq(run_id),
                "state": "error",
                "errorMessage": f"max steps exceeded ({max_steps})",
            }
        )

    @staticmethod
    def _initiator_role(initiator: dict[str, Any] | None) -> str:
        if not isinstance(initiator, dict):
            return ""
        if bool(initiator.get("tenantAdmin")):
            return "admin"
        return str(initiator.get("tenantRole", "") or "").strip().lower()

    def _tool_is_admin_only(self, tool_name: str) -> bool:
        admin_only = {str(name).strip() for name in self.config.tools.admin_only if str(name).strip()}
        if not admin_only:
            return False
        return self.tools._is_allowed_by_allowlist(tool_name, admin_only)

    async def _effective_runtime_tool_allowlist(
        self,
        requested: list[str] | None,
        *,
        initiator: dict[str, Any] | None = None,
        profile_allowlist: list[str] | None = None,
    ) -> list[str]:
        base_specs = self.tools.list_specs(self.config.tools.allowlist)
        requested_patterns, requested_excludes = self._split_tool_allowlist_patterns(requested)
        profile_patterns, profile_excludes = self._split_tool_allowlist_patterns(profile_allowlist)
        filtered: list[str] = []
        seen: set[str] = set()
        initiator_is_admin = self._initiator_role(initiator) == "admin"
        allowed_plugins = await self._resolved_user_allowed_plugins(initiator)

        for spec in base_specs:
            tool_name = spec.name
            if tool_name in seen:
                continue
            plugin_id = str(self.tools.plugin_id_for_tool(tool_name) or "").strip().lower()
            # Profile-level tool allowlists should not silently suppress plugin tools.
            # Plugin availability is governed by platform/tenant/user plugin gating.
            if not plugin_id and profile_patterns and not self.tools._is_allowed_by_allowlist(tool_name, profile_patterns):
                continue
            if requested_patterns and not self.tools._is_allowed_by_allowlist(tool_name, requested_patterns):
                continue
            if plugin_id:
                if plugin_id not in allowed_plugins:
                    continue
            if profile_excludes and self.tools._is_allowed_by_allowlist(tool_name, profile_excludes):
                continue
            if requested_excludes and self.tools._is_allowed_by_allowlist(tool_name, requested_excludes):
                continue
            if not initiator_is_admin and self._tool_is_admin_only(tool_name):
                continue
            filtered.append(tool_name)
            seen.add(tool_name)
        if not filtered and base_specs:
            self.log.warning(
                "effective tool allowlist resolved empty; applying base tool fallback (requested=%s profile=%s)",
                requested,
                profile_allowlist,
            )
            for spec in base_specs:
                tool_name = spec.name
                if tool_name in seen:
                    continue
                plugin_id = str(self.tools.plugin_id_for_tool(tool_name) or "").strip().lower()
                if plugin_id and plugin_id not in allowed_plugins:
                    continue
                if not initiator_is_admin and self._tool_is_admin_only(tool_name):
                    continue
                filtered.append(tool_name)
                seen.add(tool_name)
        return filtered

    @staticmethod
    def _split_tool_allowlist_patterns(values: list[str] | None) -> tuple[set[str], set[str]]:
        include: set[str] = set()
        exclude: set[str] = set()
        for raw in values or []:
            token = str(raw or "").strip()
            if not token:
                continue
            if token[0] in {"-", "!"}:
                normalized = token[1:].strip()
                if normalized:
                    exclude.add(normalized)
                continue
            include.add(token)
        return include, exclude

    @staticmethod
    def _looks_like_permission_gate(text: str) -> bool:
        normalized = text.strip().lower()
        patterns = (
            "quieres que",
            "¿quieres que",
            "puedes compartir",
            "podrias compartir",
            "podrías compartir",
            "puedes proporcionar",
            "podrias proporcionar",
            "podrías proporcionar",
            "do you want me to",
            "can you share",
            "could you share",
            "can you provide",
            "could you provide",
            "i can help you build",
            "from your local environment",
        )
        return any(pattern in normalized for pattern in patterns)

    async def _safe_refresh_context_summary(self, session_key: str, model_client: OpenAIModelClient | None = None) -> None:
        try:
            await self._refresh_context_summary(session_key, model_client=model_client)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.log.warning("context summary refresh task failed: %s", exc)

    def _schedule_context_summary_refresh(
        self,
        session_key: str,
        *,
        model_client: OpenAIModelClient | None = None,
    ) -> None:
        if not self.config.agent.context_compaction_enabled:
            return
        existing = self._summary_refresh_tasks.get(session_key)
        if existing and not existing.done():
            existing.cancel()
        task = asyncio.create_task(
            self._safe_refresh_context_summary(session_key, model_client=model_client)
        )
        self._summary_refresh_tasks[session_key] = task

        def _cleanup(done_task: asyncio.Task[None]) -> None:
            current = self._summary_refresh_tasks.get(session_key)
            if current is done_task:
                self._summary_refresh_tasks.pop(session_key, None)
            try:
                done_task.result()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                self.log.warning("context summary cleanup failed: %s", exc)

        task.add_done_callback(_cleanup)

    async def _refresh_context_summary(self, session_key: str, model_client: OpenAIModelClient | None = None) -> None:
        history = await self._session_load_messages(session_key)
        history_items = self._extract_history_items(history)
        if not history_items:
            await self._session_save_summary(session_key, self._ensure_summary_sections(""), 0)
            return

        existing_summary, _ = await self._session_load_summary(session_key)
        latest_response = ""
        latest_user_message = ""
        found_latest_assistant = False
        for item in reversed(history_items):
            role = item.get("role")
            if role == "assistant" and not found_latest_assistant:
                latest_response = item.get("text", "").strip()
                if latest_response:
                    found_latest_assistant = True
                continue
            if found_latest_assistant and role == "user":
                latest_user_message = item.get("text", "").strip()
                if latest_user_message:
                    break
        if not latest_response:
            return

        max_chars = max(1200, int(self.config.agent.context_summary_max_chars))
        recent_artifacts = await self._recent_artifacts_summary_for_session(session_key=session_key)
        summarizer_messages = [
            {
                "role": "system",
                "content": (
                    "You maintain a rolling truth-aware memory summary for an autonomous software agent. "
                    "Update the summary using the previous summary and the latest turn data. "
                    "Goal: preserve durable truth, keep the newest validated facts as canonical, and track what changed.\n\n"
                    "Rules:\n"
                    "1) Distill atomic facts. Remove chatter.\n"
                    "2) If new information clearly contradicts an older fact, keep only the newer fact in active sections.\n"
                    "3) Move contradicted/obsolete items to 'Superseded / Invalidated' with a short reason.\n"
                    "4) Keep older facts that are still true. Do not delete valid historical context.\n"
                    "5) Prefer concrete data (IDs, counts, endpoints, dates, file paths) over vague text.\n"
                    "6) Never include secrets/tokens/passwords.\n"
                    "7) When files were uploaded or generated, list them in 'Key Artifacts' with a short purpose or content reminder.\n\n"
                    "Output concise markdown with sections exactly named:\n"
                    "Goals\n"
                    "Truth Ledger\n"
                    "Decisions\n"
                    "Constraints\n"
                    "Open Items\n"
                    "Key Artifacts\n"
                    "Superseded / Invalidated\n"
                    "Do Not Forget\n\n"
                    "For Truth Ledger bullets, prefix with one of: [active], [historical], [uncertain]."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Previous summary:\n{existing_summary or '(empty)'}\n\n"
                    f"Recent file artifacts:\n{recent_artifacts or '(none)'}\n\n"
                    f"Latest user message (if any):\n{latest_user_message or '(none)'}\n\n"
                    f"Latest assistant response:\n{latest_response}\n\n"
                    f"Return updated summary under {max_chars} characters."
                ),
            },
        ]

        try:
            client = model_client or self.model
            result = await client.complete(messages=summarizer_messages, tools=[])
            updated_summary = result.text.strip()
        except Exception as exc:
            self.log.warning("context summary update failed: %s", exc)
            updated_summary = ""

        if not updated_summary:
            updated_summary = existing_summary or self._summarize_history_for_context(history_items, max_chars)
        updated_summary = self._ensure_summary_sections(updated_summary)
        if len(updated_summary) > max_chars:
            updated_summary = updated_summary[:max_chars].rstrip() + "\n...[truncated]"

        await self._session_save_summary(session_key, updated_summary, len(history_items))
        next_title = self._derive_session_title(updated_summary, history_items)
        if next_title:
            current_title = await self._session_load_title(session_key)
            if next_title != current_title:
                await self._session_save_title(session_key, next_title)

    async def _recent_artifacts_summary_for_session(self, *, session_key: str, limit: int = 8) -> str:
        if not callable(self.memory_recent):
            return ""
        try:
            items = await asyncio.to_thread(self.memory_recent, session_key=session_key, limit=max(1, min(limit, 20)))
        except Exception:
            return ""
        if not isinstance(items, list):
            return ""
        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "")).strip().lower()
            if kind not in {"attachment", "generated_file"}:
                continue
            title = str(item.get("title", "")).strip() or kind
            metadata = item.get("metadata")
            meta = metadata if isinstance(metadata, dict) else {}
            summary = str(meta.get("summary") or "").strip()
            path = str(meta.get("path") or "").strip()
            download_url = str(meta.get("downloadUrl") or "").strip()
            line = f"- [{kind}] {title}"
            if summary:
                line += f": {summary}"
            elif path:
                line += f": {path}"
            lines.append(line)
            if download_url:
                lines.append(f"  download: {download_url}")
            if len(lines) >= (limit * 2):
                break
        return "\n".join(lines).strip()

    @staticmethod
    def _ensure_summary_sections(summary: str) -> str:
        required = [
            "Goals",
            "Truth Ledger",
            "Decisions",
            "Constraints",
            "Open Items",
            "Key Artifacts",
            "Superseded / Invalidated",
            "Do Not Forget",
        ]
        text = (summary or "").strip()
        if not text:
            return "\n\n".join(f"## {section}\n- (none)" for section in required)

        for section in required:
            pattern = re.compile(rf"^\s*#{0,3}\s*{re.escape(section)}\s*$", re.IGNORECASE | re.MULTILINE)
            if not pattern.search(text):
                text += f"\n\n## {section}\n- (none)"
        return text

    @classmethod
    def _derive_session_title(cls, summary: str, history_items: list[dict[str, str]]) -> str:
        sections = cls._parse_summary_sections(summary)
        ordered_sections = [
            "goals",
            "open items",
            "truth ledger",
            "decisions",
            "key artifacts",
            "constraints",
            "do not forget",
        ]
        candidates: list[str] = []
        for section_name in ordered_sections:
            block = sections.get(section_name, "")
            if not block:
                continue
            for line in block.splitlines():
                candidate = cls._normalize_title_candidate(line)
                if candidate:
                    candidates.append(candidate)

        for item in reversed(history_items):
            if item.get("role") != "user":
                continue
            fallback = cls._normalize_title_candidate(item.get("text", ""))
            if fallback:
                candidates.append(fallback)
                break

        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            return cls._truncate_session_title(candidate, limit=80)
        return ""

    @classmethod
    def _parse_summary_sections(cls, summary: str) -> dict[str, str]:
        sections: dict[str, list[str]] = {}
        current_section = ""
        for line in str(summary or "").splitlines():
            match = cls._SUMMARY_HEADER_RE.match(line)
            if match:
                current_section = match.group(1).strip().lower()
                sections.setdefault(current_section, [])
                continue
            if current_section:
                sections.setdefault(current_section, []).append(line)
        return {name: "\n".join(lines) for name, lines in sections.items()}

    @classmethod
    def _normalize_title_candidate(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = cls._MARKDOWN_LINK_RE.sub(r"\1", text)
        text = re.sub(r"^\s*(?:[-*+]|>\s*|\d+[.)])\s*", "", text)
        text = re.sub(r"^\s*\[[^\]]+\]\s*", "", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = text.strip(" .,:;|")
        lowered = text.lower()
        if lowered in {"", "(none)", "none", "n/a", "na"}:
            return ""
        if lowered.startswith("session:"):
            return ""
        if text.startswith("## "):
            return ""
        return text

    @staticmethod
    def _truncate_session_title(value: str, limit: int = 80) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        clipped = text[: max(0, limit - 1)].rstrip()
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0]
        clipped = clipped.strip()
        return f"{clipped}…" if clipped else text[:limit]

    async def _handle_tool_call(
        self,
        *,
        run_id: str,
        session_key: str,
        model_messages: list[dict[str, Any]],
        tool_call: dict[str, Any],
        runtime_allowlist: list[str],
    ) -> None:
        call_id = str(tool_call.get("id") or uuid.uuid4())
        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        tool_name_raw = str(function.get("name", "")).strip()
        tool_name = self.tools.resolve_tool_name(tool_name_raw)
        raw_arguments = str(function.get("arguments", "{}")).strip() or "{}"

        await self._emit_agent_tool_event(
            run_id=run_id,
            session_key=session_key,
            tool_call_id=call_id,
            name=tool_name,
            phase="start",
            args=self._redact_tool_args_for_event(tool_name, raw_arguments),
        )

        try:
            allowed_tools = {str(name).strip() for name in runtime_allowlist if str(name).strip()}
            if tool_name not in allowed_tools:
                if self._tool_is_admin_only(tool_name):
                    raise ToolError(f"tool '{tool_name}' requires a tenant admin initiator")
                raise ToolError(f"tool '{tool_name}' is not allowed for this run")
            parsed_arguments = json.loads(raw_arguments)
            if not isinstance(parsed_arguments, dict):
                raise ToolError("tool arguments must be a JSON object")
            active_run = self._active_runs.get(run_id)
            execution_context = {
                "runId": run_id,
                "sessionKey": session_key,
                "initiator": dict(active_run.initiator) if active_run is not None and isinstance(active_run.initiator, dict) else None,
                "selectedProfile": (
                    str(active_run.selected_profile or "").strip()
                    if active_run is not None
                    else ""
                ),
                "agentRuntime": (
                    dict(active_run.agent_runtime)
                    if active_run is not None and isinstance(active_run.agent_runtime, dict)
                    else {}
                ),
            }
            result = await self.tools.execute(tool_name, parsed_arguments, execution_context=execution_context)
            result = await self._enrich_tool_result_with_media(
                tool_name=tool_name,
                result=result,
                session_key=session_key,
                run_id=run_id,
            )
            result_text = format_tool_result_for_model(result)
            await self._record_memory_artifact(
                session_key=session_key,
                run_id=run_id,
                kind="tool_result",
                title=tool_name,
                text=result_text[:8000],
                metadata={"tool": tool_name, "phase": "result"},
            )
            await self._emit_agent_tool_event(
                run_id=run_id,
                session_key=session_key,
                tool_call_id=call_id,
                name=tool_name,
                phase="result",
                result=self._redact_tool_result_for_event(tool_name, result_text),
            )
        except Exception as exc:
            result = {"error": str(exc)}
            result_text = format_tool_result_for_model(result)
            await self._record_memory_artifact(
                session_key=session_key,
                run_id=run_id,
                kind="tool_error",
                title=tool_name,
                text=result_text[:8000],
                metadata={"tool": tool_name, "phase": "error"},
            )
            await self._emit_agent_tool_event(
                run_id=run_id,
                session_key=session_key,
                tool_call_id=call_id,
                name=tool_name,
                phase="error",
                result=self._redact_tool_result_for_event(tool_name, result_text),
            )

        model_messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": result_text,
            }
        )
        download_url = str(result.get("downloadUrl", "")).strip() if isinstance(result, dict) else ""
        if download_url:
            model_messages.append(
                {
                    "role": "system",
                    "content": (
                        "A tool generated a downloadable file for this turn. "
                        f"You must include this markdown link in your next response: [Download file]({download_url})"
                    ),
                }
            )

    async def _enrich_tool_result_with_media(
        self,
        *,
        tool_name: str,
        result: dict[str, Any],
        session_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        if not isinstance(result, dict):
            return result
        if tool_name == "moio_api.run":
            return await self._enrich_moio_api_result_with_media(
                result=result,
                tool_name=tool_name,
                session_key=session_key,
                run_id=run_id,
            )
        if tool_name != "files.write":
            return result
        raw_path = str(result.get("path", "")).strip()
        if not raw_path:
            return result
        source_path = Path(raw_path)
        if not source_path.exists() or not source_path.is_file():
            return result

        mime_type = mimetypes.guess_type(source_path.name)[0] or "text/plain"
        try:
            stored = await self.media_store.mirror_file(
                source_path=source_path,
                session_key=session_key,
                run_id=run_id,
                category="generated",
                preferred_name=source_path.name,
                mime_type=mime_type,
            )
        except Exception as exc:
            self.log.warning("failed to mirror generated media for %s: %s", raw_path, exc)
            return result

        enriched = dict(result)
        enriched["downloadUrl"] = stored.download_url
        if stored.s3_url:
            enriched["s3Url"] = stored.s3_url
        else:
            enriched["localMediaUrl"] = stored.local_url
        if stored.s3_key:
            enriched["s3Key"] = stored.s3_key
        enriched["conversationMediaPath"] = stored.relative_path
        artifact_entry = self._compact_generated_file_entry(
            {
                "name": source_path.name,
                "path": str(source_path),
                "downloadUrl": stored.download_url,
                "mimeType": mime_type,
                "tool": tool_name,
            }
        )
        self._run_generated_files.setdefault(run_id, []).append(artifact_entry)
        await self._record_memory_artifact(
            session_key=session_key,
            run_id=run_id,
            kind="generated_file",
            title=source_path.name,
            text=(
                f"Generated file {source_path.name} via {tool_name}.\n"
                f"Path: {source_path}\n"
                f"Download URL: {stored.download_url}"
            ),
            metadata=artifact_entry,
        )
        return enriched

    @staticmethod
    def _looks_like_download_url(value: str) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        lower = text.lower()
        if lower.startswith(("http://", "https://")):
            return True
        return lower.startswith("/media/") or lower.startswith("media/")

    @classmethod
    def _extract_file_entries_from_moio_api_result(cls, result: dict[str, Any], limit: int = 8) -> list[dict[str, str]]:
        response = result.get("response")
        if not isinstance(response, dict):
            return []
        payload = response.get("data_preview")
        out: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        def _entry_name(url: str, preferred: str) -> str:
            if preferred:
                return preferred
            parsed = urllib.parse.urlparse(url)
            tail = Path(parsed.path).name if parsed.path else ""
            return str(tail or "generated file")

        def _add(url: str, *, name: str = "", mime: str = "") -> None:
            normalized_url = str(url or "").strip()
            if not cls._looks_like_download_url(normalized_url):
                return
            if normalized_url in seen_urls:
                return
            seen_urls.add(normalized_url)
            out.append(
                {
                    "name": _entry_name(normalized_url, str(name or "").strip()),
                    "downloadUrl": normalized_url,
                    "mimeType": str(mime or "").strip(),
                }
            )

        def _walk(node: Any, *, hint_name: str = "", hint_mime: str = "", depth: int = 0) -> None:
            if len(out) >= limit or depth > 7:
                return
            if isinstance(node, dict):
                local_name = str(
                    node.get("name")
                    or node.get("filename")
                    or node.get("file_name")
                    or node.get("title")
                    or hint_name
                    or ""
                ).strip()
                local_mime = str(
                    node.get("mimeType")
                    or node.get("mime_type")
                    or node.get("content_type")
                    or hint_mime
                    or ""
                ).strip()
                for key, value in node.items():
                    key_n = str(key or "").strip().lower()
                    if isinstance(value, str):
                        if key_n in {"downloadurl", "download_url", "fileurl", "file_url"}:
                            _add(value, name=local_name, mime=local_mime)
                        elif key_n == "url":
                            _add(value, name=local_name, mime=local_mime)
                        continue
                    if isinstance(value, (dict, list)):
                        _walk(value, hint_name=local_name, hint_mime=local_mime, depth=depth + 1)
                        if len(out) >= limit:
                            return
                return
            if isinstance(node, list):
                for item in node:
                    _walk(item, hint_name=hint_name, hint_mime=hint_mime, depth=depth + 1)
                    if len(out) >= limit:
                        return

        _walk(payload)
        return out

    @staticmethod
    def _absolutize_download_url(url: str, request_url: str) -> str:
        text = str(url or "").strip()
        if not text:
            return ""
        if text.startswith(("http://", "https://")):
            return text
        base = str(request_url or "").strip()
        if base:
            try:
                return urllib.parse.urljoin(base, text)
            except Exception:
                pass
        return text

    @staticmethod
    def _download_url_bytes_sync(url: str, max_bytes: int = 25 * 1024 * 1024) -> tuple[bytes, str]:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "moio-agent-console/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:  # nosec B310 - controlled runtime mirror utility
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise ValueError("downloaded file exceeds maximum mirror size")
            content_type = str(response.headers.get("Content-Type", "")).strip()
            mime_type = content_type.split(";", 1)[0].strip().lower()
            return payload, mime_type

    async def _enrich_moio_api_result_with_media(
        self,
        *,
        result: dict[str, Any],
        tool_name: str,
        session_key: str,
        run_id: str,
    ) -> dict[str, Any]:
        file_entries = self._extract_file_entries_from_moio_api_result(result)
        if not file_entries:
            return result

        request_url = ""
        response = result.get("response")
        if isinstance(response, dict):
            request = response.get("request")
            if isinstance(request, dict):
                request_url = str(request.get("url", "")).strip()

        enriched = dict(result)

        existing_items = self._run_generated_files.setdefault(run_id, [])
        existing_urls = {
            str(item.get("downloadUrl", "")).strip()
            for item in existing_items
            if isinstance(item, dict)
        }
        for entry in file_entries:
            raw_download_url = str(entry.get("downloadUrl", "")).strip()
            download_url = raw_download_url
            if not download_url or download_url in existing_urls:
                continue
            mirrored_download_url = ""
            try:
                resolved_url = self._absolutize_download_url(raw_download_url, request_url)
                if resolved_url.startswith(("http://", "https://")):
                    payload, detected_mime = await asyncio.to_thread(self._download_url_bytes_sync, resolved_url)
                    preferred_name = str(entry.get("name", "")).strip()
                    if not preferred_name:
                        preferred_name = Path(urllib.parse.urlparse(resolved_url).path or "").name or "generated_file"
                    stored = await self.media_store.store_bytes(
                        session_key=session_key,
                        run_id=run_id,
                        category="generated",
                        filename=preferred_name,
                        payload=payload,
                        mime_type=str(entry.get("mimeType", "")).strip() or detected_mime or None,
                    )
                    mirrored_download_url = str(stored.download_url or "").strip()
            except Exception as exc:
                self.log.debug("moio_api artifact mirror skipped for %s: %s", raw_download_url, exc)

            if mirrored_download_url:
                download_url = mirrored_download_url

            if download_url in existing_urls:
                continue
            existing_urls.add(download_url)
            artifact_entry = self._compact_generated_file_entry(
                {
                    "name": str(entry.get("name", "")).strip() or "generated file",
                    "path": "",
                    "downloadUrl": download_url,
                    "mimeType": str(entry.get("mimeType", "")).strip(),
                    "tool": tool_name,
                }
            )
            existing_items.append(artifact_entry)
            await self._record_memory_artifact(
                session_key=session_key,
                run_id=run_id,
                kind="generated_file",
                title=str(entry.get("name", "")).strip() or "generated file",
                text=f"Generated downloadable artifact via {tool_name}.\nDownload URL: {download_url}",
                metadata=artifact_entry,
            )
            if not str(enriched.get("downloadUrl", "")).strip():
                enriched["downloadUrl"] = download_url
        if existing_items and not str(enriched.get("downloadUrl", "")).strip():
            first_url = str(existing_items[0].get("downloadUrl", "")).strip() if isinstance(existing_items[0], dict) else ""
            if first_url:
                enriched["downloadUrl"] = first_url
        return enriched

    async def _record_memory_artifact(
        self,
        *,
        session_key: str,
        run_id: str,
        kind: str,
        title: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not callable(self.memory_recorder):
            return
        payload_text = str(text or "").strip()
        if not payload_text:
            return
        try:
            await asyncio.to_thread(
                self.memory_recorder,
                session_key=session_key,
                run_id=run_id,
                kind=kind,
                title=title,
                text=payload_text,
                metadata=metadata or {},
            )
        except Exception as exc:
            self.log.debug("memory artifact record skipped: %s", exc)

    def _next_seq(self, run_id: str) -> int:
        next_value = self._run_seq.get(run_id, 0) + 1
        self._run_seq[run_id] = next_value
        return next_value

    async def _emit_chat_event(self, payload: dict[str, Any]) -> None:
        run_id = str(payload.get("runId", "")).strip()
        state = str(payload.get("state", "")).strip().lower()
        if run_id and state == "final" and self._user_notification_sender is not None:
            active_run = self._active_runs.get(run_id)
            initiator = active_run.initiator if active_run is not None else None
            if isinstance(initiator, dict):
                title = "Response ready"
                message_payload = payload.get("message")
                preview = ""
                if isinstance(message_payload, dict):
                    content = message_payload.get("content")
                    if isinstance(content, list):
                        parts: list[str] = []
                        for entry in content:
                            if not isinstance(entry, dict):
                                continue
                            text = entry.get("text")
                            if isinstance(text, str) and text.strip():
                                parts.append(text.strip())
                        preview = "\n".join(parts).strip()
                body = preview.strip() or "The agent finished responding."
                body = re.sub(r"\s+", " ", body).strip()
                if len(body) > 180:
                    body = f"{body[:177].rstrip()}..."
                try:
                    await self._user_notification_sender(
                        initiator,
                        {
                            "title": title,
                            "body": body,
                            "tag": f"run:{run_id}",
                            "sessionKey": str(payload.get("sessionKey", "") or "").strip(),
                            "runId": run_id,
                        },
                    )
                except Exception as exc:
                    self.log.debug("user notification skipped: %s", exc)
        if run_id and state in {"final", "error", "aborted"}:
            waiter = self._run_waiters.get(run_id)
            if waiter is not None and not waiter.done():
                waiter.set_result(
                    {
                        "state": state,
                        "errorMessage": str(payload.get("errorMessage", "") or "").strip(),
                        "message": payload.get("message"),
                    }
                )
        if not self._event_sink:
            return
        await self._event_sink(
            {
                "type": "chat_event",
                "payload": payload,
                "seq": payload.get("seq"),
            }
        )

    async def _emit_agent_tool_event(
        self,
        *,
        run_id: str,
        session_key: str,
        tool_call_id: str,
        name: str,
        phase: str,
        args: str | None = None,
        result: str | None = None,
    ) -> None:
        if not self._event_sink:
            return

        data: dict[str, Any] = {
            "toolCallId": tool_call_id,
            "name": name,
            "phase": phase,
        }
        if args is not None:
            data["args"] = args
        if result is not None:
            data["result"] = result

        await self._event_sink(
            {
                "type": "agent_event",
                "payload": {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "stream": "tool",
                    "data": data,
                },
                "seq": self._next_seq(run_id),
            }
        )

    @staticmethod
    def _loop_status_for_phase(phase: str) -> str:
        key = str(phase or "").strip().lower()
        if key in {"error", "timeout", "max_steps_exceeded"}:
            return "error"
        if key in {"aborted", "rejected"}:
            return "aborted"
        if key in {"completed"}:
            return "done"
        if key in {"tool_calls"}:
            return "tools"
        if key in {"run_start"}:
            return "queued"
        return "thinking"

    @staticmethod
    def _loop_phase_label(phase: str) -> str:
        labels = {
            "run_start": "Run start",
            "step_start": "Step start",
            "model_request": "Model request",
            "model_response": "Model response",
            "tool_calls": "Tool calls",
            "step_complete": "Step complete",
            "permission_retry": "Permission retry",
            "finalizing": "Finalizing",
            "completed": "Completed",
            "max_steps_exceeded": "Max steps exceeded",
            "timeout": "Timeout",
            "aborted": "Aborted",
            "rejected": "Rejected",
            "error": "Error",
        }
        key = str(phase or "").strip().lower()
        if key in labels:
            return labels[key]
        return key.replace("_", " ").strip().title() or "Loop event"

    @classmethod
    def _humanize_loop_event(cls, phase: str, payload_data: dict[str, Any]) -> str:
        key = str(phase or "").strip().lower()
        step = payload_data.get("step")
        max_steps = payload_data.get("maxSteps")
        prefix = ""
        if isinstance(step, int) and step > 0 and isinstance(max_steps, int) and max_steps > 0:
            prefix = f"Step {step}/{max_steps}. "

        if key == "run_start":
            attachment_count = int(payload_data.get("attachmentCount", 0) or 0)
            thinking = str(payload_data.get("thinking", "")).strip() or "default"
            if attachment_count > 0:
                return f"Run queued with {attachment_count} attachment(s); thinking={thinking}."
            return f"Run queued; thinking={thinking}."
        if key == "step_start":
            return f"{prefix}Starting reasoning cycle."
        if key == "model_request":
            context_messages = payload_data.get("contextMessages")
            tool_schemas = payload_data.get("toolSchemas")
            model = str(payload_data.get("model", "")).strip()
            pieces: list[str] = []
            if isinstance(context_messages, int) and context_messages >= 0:
                pieces.append(f"context={context_messages}")
            if isinstance(tool_schemas, int) and tool_schemas >= 0:
                pieces.append(f"tools={tool_schemas}")
            if model:
                pieces.append(f"model={model}")
            suffix = f" ({', '.join(pieces)})" if pieces else ""
            return f"{prefix}Sending request to model{suffix}."
        if key == "model_response":
            tool_calls = int(payload_data.get("toolCalls", 0) or 0)
            output_chars = int(payload_data.get("outputChars", 0) or 0)
            if tool_calls > 0:
                return f"{prefix}Model returned {tool_calls} tool call(s)."
            return f"{prefix}Model returned text ({output_chars} chars)."
        if key == "tool_calls":
            count = int(payload_data.get("count", 0) or 0)
            names = payload_data.get("toolNames")
            if isinstance(names, list) and names:
                return f"{prefix}Executing {count} tool call(s): {', '.join(str(item) for item in names[:4])}."
            return f"{prefix}Executing {count} tool call(s)."
        if key == "step_complete":
            return f"{prefix}Step complete; continuing."
        if key == "permission_retry":
            retry_count = int(payload_data.get("retryCount", 0) or 0)
            return f"{prefix}Permission-seeking reply detected; retrying autonomously (retry {retry_count})."
        if key == "finalizing":
            final_chars = int(payload_data.get("finalChars", 0) or 0)
            return f"{prefix}Finalizing assistant response ({final_chars} chars)."
        if key == "completed":
            total_tokens = int(payload_data.get("totalTokens", 0) or 0)
            if total_tokens > 0:
                return f"{prefix}Run completed ({total_tokens} tokens)."
            return f"{prefix}Run completed."
        if key == "max_steps_exceeded":
            return f"{prefix}Max step budget reached before a final answer."
        if key == "timeout":
            timeout_seconds = payload_data.get("timeoutSeconds")
            if isinstance(timeout_seconds, (int, float)):
                return f"Run timed out after {timeout_seconds}s."
            return "Run timed out."
        if key == "aborted":
            return "Run aborted by user."
        if key == "rejected":
            reason = str(payload_data.get("reason", "")).strip()
            if reason:
                return f"Run rejected: {reason}."
            return "Run rejected."
        if key == "error":
            message = str(payload_data.get("message", "")).strip()
            if message:
                return f"Run failed: {message}"
            return "Run failed."
        return f"{prefix}{cls._loop_phase_label(key)}."

    async def _emit_agent_loop_event(
        self,
        *,
        run_id: str,
        session_key: str,
        phase: str,
        step: int | None = None,
        max_steps: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        if not self._event_sink:
            return

        phase_key = str(phase or "").strip().lower() or "unknown"
        now_ms = int(time.time() * 1000)
        payload_data: dict[str, Any] = {
            "phase": phase_key,
            "timestampMs": now_ms,
            "phaseLabel": self._loop_phase_label(phase_key),
            "status": self._loop_status_for_phase(phase_key),
        }
        started_at_ms = self._run_started_at.get(run_id)
        if isinstance(started_at_ms, int) and started_at_ms > 0:
            payload_data["elapsedMs"] = max(0, now_ms - started_at_ms)
        if isinstance(step, int) and step > 0:
            payload_data["step"] = step
        if isinstance(max_steps, int) and max_steps > 0:
            payload_data["maxSteps"] = max_steps
        if isinstance(data, dict):
            payload_data.update(data)
        step_value = payload_data.get("step")
        max_value = payload_data.get("maxSteps")
        if isinstance(step_value, int) and step_value > 0 and isinstance(max_value, int) and max_value > 0:
            payload_data["progressPct"] = max(0, min(100, int(round((step_value / max_value) * 100))))
        payload_data["humanMessage"] = self._humanize_loop_event(phase_key, payload_data)

        await self._event_sink(
            {
                "type": "agent_event",
                "payload": {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "stream": "loop",
                    "data": payload_data,
                },
                "seq": self._next_seq(run_id),
            }
        )

    @staticmethod
    def _sanitize_for_logs(value: Any) -> Any:
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, item in value.items():
                key_l = str(key).lower()
                if key_l in {"password", "passphrase", "secret", "token", "access", "refresh", "api_key", "authorization"}:
                    redacted[str(key)] = "[REDACTED]"
                else:
                    redacted[str(key)] = AgentConsoleBackend._sanitize_for_logs(item)
            return redacted
        if isinstance(value, list):
            return [AgentConsoleBackend._sanitize_for_logs(item) for item in value]
        return value

    @staticmethod
    def _redact_tool_args_for_event(tool_name: str, raw_arguments: str) -> str:
        try:
            payload = json.loads(raw_arguments)
        except Exception:
            return raw_arguments
        if not isinstance(payload, dict):
            return raw_arguments

        safe_payload = AgentConsoleBackend._sanitize_for_logs(payload)
        if tool_name == "vault.set" and isinstance(safe_payload, dict) and "value" in safe_payload:
            safe_payload["value"] = "[REDACTED]"
        return json.dumps(safe_payload, ensure_ascii=True)

    @staticmethod
    def _redact_tool_result_for_event(tool_name: str, result_text: str) -> str:
        if not tool_name.startswith("vault."):
            return result_text
        try:
            payload = json.loads(result_text)
        except Exception:
            return result_text
        if not isinstance(payload, dict):
            return result_text
        safe_payload = dict(payload)
        if "value" in safe_payload:
            safe_payload["value"] = "[REDACTED]"
        return json.dumps(safe_payload, ensure_ascii=True)
