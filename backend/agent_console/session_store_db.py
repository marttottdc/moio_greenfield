"""
Database-backed session store for Agent Console. Uses AgentConsoleSession model;
run inside tenant schema (e.g. via public_schema_context) when calling from runtime.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from django.db.utils import OperationalError, ProgrammingError

from agent_console.models import AgentConsoleSession
from agent_console.runtime.session_store import (
    SessionMessage,
    build_event_log_from_messages,
    normalize_payload,
    normalize_session_author,
    normalize_session_message,
    normalize_session_scope,
    normalize_queued_turn,
    session_scope_visible_to_actor,
)

logger = logging.getLogger(__name__)


def _default_payload(session_key: str) -> dict[str, Any]:
    return {
        "sessionKey": session_key,
        "title": "",
        "updatedAtMs": int(time.time() * 1000),
        "messages": [],
        "summary": "",
        "summaryUpTo": 0,
        "usage": {"input": 0, "output": 0, "total": 0},
        "queuedTurns": [],
    }


class DatabaseSessionStore:
    """
    Session store that persists to the database (AgentConsoleSession).
    Use tenancy.tenant_support.public_schema_context(tenant_schema) when querying if needed (no-op for single schema).
    """

    _database_store = True  # marker so backend skips sessions_dir.mkdir

    def __init__(self, tenant_schema: str, workspace_slug: str):
        self.tenant_schema = (tenant_schema or "public").strip() or "public"
        self.workspace_slug = (workspace_slug or "main").strip() or "main"

    def _public_schema_context(self):
        from tenancy.tenant_support import public_schema_context
        return public_schema_context(self.tenant_schema)

    def _is_missing_table_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "agent_console_session" in text and (
            "does not exist" in text or "undefined table" in text or "no such table" in text
        )

    def _get_or_create_payload(self, session_key: str) -> dict[str, Any]:
        key = (session_key or "main").strip() or "main"
        try:
            with self._public_schema_context():
                row, _ = AgentConsoleSession.objects.get_or_create(
                    workspace_slug=self.workspace_slug,
                    session_key=key,
                    defaults={
                        "title": "",
                        "scope": "shared",
                        "owner": {},
                        "payload": _default_payload(key),
                    },
                )
                payload = dict(row.payload) if isinstance(row.payload, dict) else {}
                payload["sessionKey"] = key
                payload["title"] = getattr(row, "title", "") or ""
                payload["scope"] = getattr(row, "scope", "shared") or "shared"
                payload["owner"] = getattr(row, "owner", None) or {}
                payload["updatedAtMs"] = int((row.updated_at.timestamp() * 1000) if row.updated_at else time.time() * 1000)
                if "messages" not in payload or not isinstance(payload["messages"], list):
                    payload["messages"] = []
                if "queuedTurns" not in payload or not isinstance(payload["queuedTurns"], list):
                    payload["queuedTurns"] = []
                return normalize_payload(payload, key)
        except (ProgrammingError, OperationalError) as exc:
            if self._is_missing_table_error(exc):
                logger.warning(
                    "agent_console_session table missing in schema=%s workspace=%s; using ephemeral payload",
                    self.tenant_schema,
                    self.workspace_slug,
                )
                return normalize_payload(_default_payload(key), key)
            raise

    def _load_payload(self, session_key: str) -> dict[str, Any]:
        return self._get_or_create_payload(session_key)

    def _write_payload(self, session_key: str, payload: dict[str, Any]) -> None:
        key = (session_key or "main").strip() or "main"
        payload["sessionKey"] = key
        payload["updatedAtMs"] = int(time.time() * 1000)
        try:
            with self._public_schema_context():
                row, _ = AgentConsoleSession.objects.get_or_create(
                    workspace_slug=self.workspace_slug,
                    session_key=key,
                    defaults={
                        "title": str(payload.get("title", "") or "").strip(),
                        "scope": normalize_session_scope(payload.get("scope")),
                        "owner": payload.get("owner") if isinstance(payload.get("owner"), dict) else {},
                        "payload": payload,
                    },
                )
                row.title = str(payload.get("title", "") or "").strip()
                row.scope = normalize_session_scope(payload.get("scope"))
                row.owner = payload.get("owner") if isinstance(payload.get("owner"), dict) else {}
                row.payload = payload
                row.save(update_fields=["title", "scope", "owner", "payload", "updated_at"])
        except (ProgrammingError, OperationalError) as exc:
            if self._is_missing_table_error(exc):
                logger.warning(
                    "agent_console_session table missing in schema=%s workspace=%s; skipping payload persist",
                    self.tenant_schema,
                    self.workspace_slug,
                )
                return
            raise

    @staticmethod
    def _extract_usage(message: dict[str, Any]) -> tuple[int, int, int]:
        usage = message.get("usage")
        if not isinstance(usage, dict):
            return 0, 0, 0
        input_tokens = int(usage.get("input", usage.get("prompt_tokens", 0)) or 0)
        output_tokens = int(usage.get("output", usage.get("completion_tokens", 0)) or 0)
        total_tokens = int(usage.get("totalTokens", usage.get("total", usage.get("total_tokens", 0))) or 0)
        if total_tokens <= 0:
            total_tokens = input_tokens + output_tokens
        return input_tokens, output_tokens, total_tokens

    @classmethod
    def _usage_totals_for_messages(cls, messages: list[dict[str, Any]]) -> dict[str, int]:
        input_total = output_total = total = 0
        for item in messages:
            if not isinstance(item, dict):
                continue
            it, ot, tt = cls._extract_usage(item)
            input_total += it
            output_total += ot
            total += tt
        if total <= 0:
            total = input_total + output_total
        return {"input": input_total, "output": output_total, "total": total}

    def load_messages(self, session_key: str) -> list[dict[str, Any]]:
        payload = self._load_payload(session_key)
        messages = payload.get("messages") or []
        out = []
        for entry in messages:
            n = normalize_session_message(entry)
            if n is not None:
                out.append(n)
        return out

    def save_messages(self, session_key: str, messages: list[dict[str, Any]]) -> None:
        payload = self._load_payload(session_key)
        filtered = [normalize_session_message(e) for e in messages if normalize_session_message(e) is not None]
        payload["messages"] = filtered
        payload["usage"] = self._usage_totals_for_messages(filtered)
        self._write_payload(session_key, payload)

    def load_summary(self, session_key: str) -> tuple[str, int]:
        payload = self._load_payload(session_key)
        s = payload.get("summary")
        u = payload.get("summaryUpTo")
        return (s if isinstance(s, str) else ""), (u if isinstance(u, int) and u >= 0 else 0)

    def save_summary(self, session_key: str, summary: str, summary_upto: int) -> None:
        payload = self._load_payload(session_key)
        payload["summary"] = str(summary or "").strip()
        payload["summaryUpTo"] = max(0, int(summary_upto))
        self._write_payload(session_key, payload)

    def load_session_title(self, session_key: str) -> str:
        payload = self._load_payload(session_key)
        t = payload.get("title")
        return str(t).strip() if isinstance(t, str) else ""

    def load_session_meta(self, session_key: str) -> dict[str, Any]:
        payload = self._load_payload(session_key)
        return {
            "sessionKey": str(payload.get("sessionKey", "") or "").strip() or (session_key.strip() or "main"),
            "scope": normalize_session_scope(payload.get("scope")),
            "owner": normalize_session_author(payload.get("owner")),
        }

    def load_queue(self, session_key: str) -> list[dict[str, Any]]:
        payload = self._load_payload(session_key)
        qt = payload.get("queuedTurns")
        if not isinstance(qt, list):
            return []
        return [n for item in qt if (n := normalize_queued_turn(item)) is not None]

    def save_queue(self, session_key: str, queued_turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload = self._load_payload(session_key)
        filtered = [normalize_queued_turn(item) for item in queued_turns if normalize_queued_turn(item) is not None]
        payload["queuedTurns"] = filtered
        self._write_payload(session_key, payload)
        return filtered

    def save_session_title(self, session_key: str, title: str) -> str:
        normalized = str(title or "").strip()
        payload = self._load_payload(session_key)
        payload["title"] = normalized
        self._write_payload(session_key, payload)
        return normalized

    def append(self, session_key: str, message: SessionMessage) -> list[dict[str, Any]]:
        messages = self.load_messages(session_key)
        payload = normalize_session_message(message.to_dict())
        if payload is None:
            return messages
        messages.append(payload)
        self.save_messages(session_key, messages)
        return messages

    def load_usage(self, session_key: str) -> dict[str, int]:
        payload = self._load_payload(session_key)
        usage = payload.get("usage")
        if isinstance(usage, dict):
            i = int(usage.get("input", 0) or 0)
            o = int(usage.get("output", 0) or 0)
            t = int(usage.get("total", 0) or 0)
            if t <= 0:
                t = i + o
            return {"input": i, "output": o, "total": t}
        return self._usage_totals_for_messages(self.load_messages(session_key))

    def load_event_log(self, session_key: str, limit: int = 200) -> list[dict[str, Any]]:
        return build_event_log_from_messages(self.load_messages(session_key), limit=limit)

    def list_sessions(self, limit: int = 200, actor: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        normalized_actor = normalize_session_author(actor)
        try:
            with self._public_schema_context():
                qs = AgentConsoleSession.objects.filter(workspace_slug=self.workspace_slug).order_by("-updated_at")
                rows = []
                for row in qs[: max(1, min(limit, 2000))]:
                    scope = normalize_session_scope(getattr(row, "scope", "shared"))
                    owner = normalize_session_author(getattr(row, "owner", None))
                    if not session_scope_visible_to_actor(scope, owner, normalized_actor):
                        continue
                    messages = (row.payload or {}).get("messages") if isinstance(row.payload, dict) else []
                    count = len(messages) if isinstance(messages, list) else 0
                    updated_at_ms = int(row.updated_at.timestamp() * 1000) if row.updated_at else 0
                    rows.append({
                        "sessionKey": row.session_key,
                        "title": str(getattr(row, "title", "") or "").strip(),
                        "scope": scope,
                        "updatedAtMs": updated_at_ms,
                        "messageCount": count,
                    })
                return rows
        except (ProgrammingError, OperationalError) as exc:
            if self._is_missing_table_error(exc):
                logger.warning(
                    "agent_console_session table missing in schema=%s workspace=%s; returning default session list",
                    self.tenant_schema,
                    self.workspace_slug,
                )
                return [{"sessionKey": "main", "title": "", "scope": "shared", "updatedAtMs": 0, "messageCount": 0}]
            raise

    def create_session(
        self,
        session_key: str,
        scope: str = "shared",
        owner: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = (session_key or "main").strip() or "main"
        payload = self._load_payload(key)
        scope_n = normalize_session_scope(scope)
        if scope_n == "private":
            payload["scope"] = "private"
            if owner is not None:
                payload["owner"] = normalize_session_author(owner) or {}
        else:
            payload["scope"] = "shared"
            payload.pop("owner", None)
        self._write_payload(key, payload)
        messages = payload.get("messages") or []
        return {
            "sessionKey": key,
            "title": str(payload.get("title", "") or "").strip(),
            "scope": normalize_session_scope(payload.get("scope")),
            "updatedAtMs": int(payload.get("updatedAtMs", 0) or 0),
            "messageCount": len(messages),
        }

    def set_session_scope(
        self,
        session_key: str,
        scope: str = "shared",
        owner: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.create_session(session_key=session_key, scope=scope, owner=owner)

    def rename_session(self, session_key: str, title: str) -> dict[str, Any]:
        normalized_title = self.save_session_title(session_key, title)
        payload = self._load_payload(session_key)
        messages = payload.get("messages") or []
        return {
            "sessionKey": (session_key or "main").strip() or "main",
            "title": normalized_title,
            "scope": normalize_session_scope(payload.get("scope")),
            "updatedAtMs": int(payload.get("updatedAtMs", 0) or 0),
            "messageCount": len(messages),
        }
