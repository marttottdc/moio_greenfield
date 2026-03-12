from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SAFE_SESSION_KEY_RE = re.compile(r"[^a-zA-Z0-9._:-]+")


@dataclass(slots=True)
class SessionMessage:
    role: str
    content: list[dict[str, str]]
    timestamp: int
    author: dict[str, Any] | None = None
    context_scope: str = "shared"
    owner: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        author = normalize_session_author(self.author)
        if author is not None:
            payload["author"] = author
        payload["contextScope"] = normalize_session_context_scope(self.context_scope)
        owner = normalize_session_author(self.owner)
        if owner is not None:
            payload["owner"] = owner
        if self.meta:
            payload.update(self.meta)
        return payload


def normalize_session_author(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    payload: dict[str, Any] = {}

    raw_id = raw.get("id")
    try:
        user_id = int(raw_id or 0)
    except (TypeError, ValueError):
        user_id = 0
    if user_id > 0:
        payload["id"] = user_id

    email = str(raw.get("email", "") or "").strip().lower()
    if email:
        payload["email"] = email

    display_name = str(raw.get("displayName", "") or "").strip()
    if display_name:
        payload["displayName"] = display_name

    return payload or None


def normalize_queue_initiator(raw: Any) -> dict[str, Any] | None:
    author = normalize_session_author(raw)
    if author is None:
        return None
    payload = dict(author)

    tenant_id = str((raw or {}).get("tenantId", "") or "").strip()
    if tenant_id:
        payload["tenantId"] = tenant_id

    tenant_role = str((raw or {}).get("tenantRole", "") or "").strip().lower()
    if tenant_role:
        payload["tenantRole"] = tenant_role

    if bool((raw or {}).get("tenantAdmin")):
        payload["tenantAdmin"] = True

    return payload


def normalize_session_context_scope(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    return "personal" if text == "personal" else "shared"


def normalize_session_scope(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    return "private" if text == "private" else "shared"


def session_scope_visible_to_actor(scope: Any, owner: Any, actor: Any) -> bool:
    normalized_scope = normalize_session_scope(scope)
    if normalized_scope != "private":
        return True

    normalized_owner = normalize_session_author(owner)
    normalized_actor = normalize_session_author(actor)
    if normalized_owner is None or normalized_actor is None:
        return False

    owner_id = int(normalized_owner.get("id", 0) or 0)
    actor_id = int(normalized_actor.get("id", 0) or 0)
    if owner_id > 0 and actor_id == owner_id:
        return True

    owner_email = str(normalized_owner.get("email", "") or "").strip().lower()
    actor_email = str(normalized_actor.get("email", "") or "").strip().lower()
    return bool(owner_email and actor_email and owner_email == actor_email)


def normalize_session_message(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    payload = dict(raw)
    payload["role"] = str(payload.get("role", "")).strip().lower() or "system"
    content = payload.get("content")
    payload["content"] = [entry for entry in content if isinstance(entry, dict)] if isinstance(content, list) else []

    timestamp = payload.get("timestamp")
    try:
        payload["timestamp"] = int(timestamp or 0)
    except (TypeError, ValueError):
        payload["timestamp"] = 0
    if payload["timestamp"] <= 0:
        payload["timestamp"] = int(time.time() * 1000)

    author = normalize_session_author(payload.get("author"))
    if author is not None:
        payload["author"] = author
    else:
        payload.pop("author", None)

    payload["contextScope"] = normalize_session_context_scope(payload.get("contextScope"))

    owner = normalize_session_author(payload.get("owner"))
    if owner is not None:
        payload["owner"] = owner
    else:
        payload.pop("owner", None)

    return payload


def _normalize_queue_attachment(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    data = str(raw.get("data", "") or "").strip()
    payload: dict[str, Any] = {
        "name": str(raw.get("name", "") or "").strip() or "attachment",
        "type": str(raw.get("type", "") or "").strip() or "application/octet-stream",
        "size": max(0, int(raw.get("size", 0) or 0)),
        "data": data,
    }
    return payload if data else None


def normalize_queued_turn(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    turn_id = str(raw.get("id", "") or "").strip() or str(raw.get("queueItemId", "") or "").strip()
    if not turn_id:
        return None

    message = str(raw.get("message", "") or "").strip()

    created_at_ms_raw = raw.get("createdAtMs")
    try:
        created_at_ms = int(created_at_ms_raw or 0)
    except (TypeError, ValueError):
        created_at_ms = 0
    if created_at_ms <= 0:
        created_at_ms = int(time.time() * 1000)

    attachments: list[dict[str, Any]] = []
    raw_attachments = raw.get("attachments")
    if isinstance(raw_attachments, list):
        for item in raw_attachments:
            normalized = _normalize_queue_attachment(item)
            if normalized is not None:
                attachments.append(normalized)
    if not message and not attachments:
        return None

    model_overrides: dict[str, Any] = {}
    raw_model_overrides = raw.get("modelOverrides")
    if isinstance(raw_model_overrides, dict):
        for key in ("provider", "model", "temperature", "max_output_tokens", "base_url", "api_key"):
            value = raw_model_overrides.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
            model_overrides[str(key)] = value

    tool_allowlist: list[str] = []
    raw_allowlist = raw.get("toolAllowlist")
    if isinstance(raw_allowlist, list):
        tool_allowlist = [str(item).strip() for item in raw_allowlist if str(item).strip()]

    timeout_raw = raw.get("timeoutMs")
    timeout_ms = int(timeout_raw) if isinstance(timeout_raw, int) and timeout_raw > 0 else 0

    return {
        "id": turn_id,
        "message": message,
        "attachments": attachments,
        "attachmentsCount": len(attachments),
        "author": normalize_session_author(raw.get("author")),
        "initiator": normalize_queue_initiator(raw.get("initiator")),
        "createdAtMs": created_at_ms,
        "thinking": str(raw.get("thinking", "") or "").strip() or "default",
        "verbosity": str(raw.get("verbosity", "") or "").strip() or "minimal",
        "selectedProfile": str(raw.get("selectedProfile", "") or "").strip(),
        "modelOverrides": model_overrides,
        "toolAllowlist": tool_allowlist,
        "timeoutMs": timeout_ms,
    }


def build_event_log_from_messages(
    messages: list[dict[str, Any]],
    *,
    limit: int = 200,
) -> list[dict[str, Any]]:
    capped_messages = messages[-max(1, min(limit, 2000)) :]

    output: list[dict[str, Any]] = []
    base_sequence = len(messages) - len(capped_messages)
    for offset, item in enumerate(capped_messages, start=1):
        content = item.get("content")
        preview = ""
        if isinstance(content, list):
            preview = "\n".join(
                str(entry.get("text", "") or "")
                for entry in content
                if isinstance(entry, dict) and str(entry.get("text", "") or "").strip()
            ).strip()
        preview = preview[:280].strip()
        output.append(
            {
                "sequence": base_sequence + offset,
                "role": str(item.get("role", "") or "").strip().lower(),
                "runId": str(item.get("runId", "") or "").strip(),
                "contextScope": normalize_session_context_scope(item.get("contextScope")),
                "author": normalize_session_author(item.get("author")),
                "owner": normalize_session_author(item.get("owner")),
                "timestamp": int(item.get("timestamp", 0) or 0),
                "textPreview": preview,
            }
        )
    return output


def normalize_payload(payload: dict[str, Any], session_key: str) -> dict[str, Any]:
    """Normalize a loaded payload (from file or DB) to the canonical shape. Mutates and returns payload."""
    if not isinstance(payload, dict):
        payload = {}
    if not isinstance(payload.get("messages"), list):
        payload["messages"] = []
    if not isinstance(payload.get("summary"), str):
        payload["summary"] = ""
    if not isinstance(payload.get("title"), str):
        payload["title"] = ""
    payload["scope"] = normalize_session_scope(payload.get("scope"))
    owner = normalize_session_author(payload.get("owner"))
    if owner is not None:
        payload["owner"] = owner
    else:
        payload.pop("owner", None)
    queued_turns = payload.get("queuedTurns")
    if not isinstance(queued_turns, list):
        payload["queuedTurns"] = []
    else:
        payload["queuedTurns"] = [
            normalized for item in queued_turns if (normalized := normalize_queued_turn(item)) is not None
        ]
    summary_upto = payload.get("summaryUpTo")
    if not isinstance(summary_upto, int) or summary_upto < 0:
        payload["summaryUpTo"] = 0
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        payload["usage"] = {"input": 0, "output": 0, "total": 0}
    else:
        payload["usage"] = {
            "input": int(usage.get("input", 0) or 0),
            "output": int(usage.get("output", 0) or 0),
            "total": int(usage.get("total", 0) or 0),
        }
    payload["sessionKey"] = session_key
    payload["updatedAtMs"] = int(time.time() * 1000)
    return payload


class SessionStore:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _session_file(self, session_key: str) -> Path:
        normalized = SAFE_SESSION_KEY_RE.sub("_", session_key.strip() or "main")
        return self.root / f"{normalized}.json"

    def _load_payload(self, session_key: str) -> dict[str, Any]:
        session_file = self._session_file(session_key)
        if not session_file.exists():
            return normalize_payload({
                "sessionKey": session_key,
                "title": "",
                "updatedAtMs": int(time.time() * 1000),
                "messages": [],
                "summary": "",
                "summaryUpTo": 0,
                "usage": {"input": 0, "output": 0, "total": 0},
            }, session_key)
        try:
            payload = json.loads(session_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        return normalize_payload(payload if isinstance(payload, dict) else {}, session_key)

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
        input_total = 0
        output_total = 0
        total = 0
        for item in messages:
            if not isinstance(item, dict):
                continue
            input_tokens, output_tokens, total_tokens = cls._extract_usage(item)
            input_total += input_tokens
            output_total += output_tokens
            total += total_tokens
        if total <= 0:
            total = input_total + output_total
        return {"input": input_total, "output": output_total, "total": total}

    def _write_payload(self, session_key: str, payload: dict[str, Any]) -> None:
        session_file = self._session_file(session_key)
        payload["sessionKey"] = session_key
        payload["updatedAtMs"] = int(time.time() * 1000)
        session_file.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    def load_messages(self, session_key: str) -> list[dict[str, Any]]:
        payload = self._load_payload(session_key)
        messages = payload.get("messages")
        if not isinstance(messages, list):
            return []
        output: list[dict[str, Any]] = []
        for entry in messages:
            normalized = normalize_session_message(entry)
            if normalized is not None:
                output.append(normalized)
        return output

    def save_messages(self, session_key: str, messages: list[dict[str, Any]]) -> None:
        payload = self._load_payload(session_key)
        filtered: list[dict[str, Any]] = []
        for entry in messages:
            normalized = normalize_session_message(entry)
            if normalized is not None:
                filtered.append(normalized)
        payload["messages"] = filtered
        payload["usage"] = self._usage_totals_for_messages(filtered)
        self._write_payload(session_key, payload)

    def load_summary(self, session_key: str) -> tuple[str, int]:
        payload = self._load_payload(session_key)
        summary = payload.get("summary")
        summary_upto = payload.get("summaryUpTo")
        return (
            summary if isinstance(summary, str) else "",
            summary_upto if isinstance(summary_upto, int) and summary_upto >= 0 else 0,
        )

    def load_session_title(self, session_key: str) -> str:
        payload = self._load_payload(session_key)
        title = payload.get("title")
        return str(title).strip() if isinstance(title, str) else ""

    def load_session_meta(self, session_key: str) -> dict[str, Any]:
        payload = self._load_payload(session_key)
        return {
            "sessionKey": str(payload.get("sessionKey", "") or "").strip() or (session_key.strip() or "main"),
            "scope": normalize_session_scope(payload.get("scope")),
            "owner": normalize_session_author(payload.get("owner")),
        }

    def load_queue(self, session_key: str) -> list[dict[str, Any]]:
        payload = self._load_payload(session_key)
        queued_turns = payload.get("queuedTurns")
        if not isinstance(queued_turns, list):
            return []
        output: list[dict[str, Any]] = []
        for item in queued_turns:
            normalized = normalize_queued_turn(item)
            if normalized is not None:
                output.append(normalized)
        return output

    def save_queue(self, session_key: str, queued_turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload = self._load_payload(session_key)
        filtered: list[dict[str, Any]] = []
        for item in queued_turns:
            normalized = normalize_queued_turn(item)
            if normalized is not None:
                filtered.append(normalized)
        payload["queuedTurns"] = filtered
        self._write_payload(session_key, payload)
        return filtered

    def save_session_title(self, session_key: str, title: str) -> str:
        payload = self._load_payload(session_key)
        normalized = str(title or "").strip()
        payload["title"] = normalized
        self._write_payload(session_key, payload)
        return normalized

    def save_summary(self, session_key: str, summary: str, summary_upto: int) -> None:
        payload = self._load_payload(session_key)
        payload["summary"] = str(summary or "").strip()
        payload["summaryUpTo"] = max(0, int(summary_upto))
        self._write_payload(session_key, payload)

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
            input_total = int(usage.get("input", 0) or 0)
            output_total = int(usage.get("output", 0) or 0)
            total = int(usage.get("total", 0) or 0)
            if total <= 0:
                total = input_total + output_total
            return {"input": input_total, "output": output_total, "total": total}
        return self._usage_totals_for_messages(self.load_messages(session_key))

    def load_event_log(self, session_key: str, limit: int = 200) -> list[dict[str, Any]]:
        messages = self.load_messages(session_key)
        return build_event_log_from_messages(messages, limit=limit)

    def list_sessions(self, limit: int = 200, actor: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        normalized_actor = normalize_session_author(actor)
        for session_file in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(session_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            key = str(payload.get("sessionKey", "")).strip()
            if not key:
                key = session_file.stem
            scope = normalize_session_scope(payload.get("scope"))
            owner = normalize_session_author(payload.get("owner"))
            if not session_scope_visible_to_actor(scope, owner, normalized_actor):
                continue
            messages = payload.get("messages")
            count = len(messages) if isinstance(messages, list) else 0
            updated_at_ms = int(payload.get("updatedAtMs", 0) or 0)
            rows.append(
                {
                    "sessionKey": key,
                    "title": str(payload.get("title", "")).strip(),
                    "scope": scope,
                    "updatedAtMs": updated_at_ms,
                    "messageCount": count,
                }
            )
        rows.sort(key=lambda item: int(item.get("updatedAtMs", 0) or 0), reverse=True)
        return rows[: max(1, min(limit, 2000))]

    def create_session(
        self,
        session_key: str,
        scope: str = "shared",
        owner: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = session_key.strip() or "main"
        payload = self._load_payload(key)
        normalized_scope = normalize_session_scope(scope)
        if normalized_scope == "private":
            payload["scope"] = "private"
            normalized_owner = normalize_session_author(owner)
            if normalized_owner is not None:
                payload["owner"] = normalized_owner
        else:
            payload["scope"] = "shared"
            payload.pop("owner", None)
        self._write_payload(key, payload)
        messages = payload.get("messages")
        return {
            "sessionKey": key,
            "title": str(payload.get("title", "")).strip(),
            "scope": normalize_session_scope(payload.get("scope")),
            "updatedAtMs": int(payload.get("updatedAtMs", 0) or 0),
            "messageCount": len(messages) if isinstance(messages, list) else 0,
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
        messages = payload.get("messages")
        return {
            "sessionKey": session_key.strip() or "main",
            "title": normalized_title,
            "scope": normalize_session_scope(payload.get("scope")),
            "updatedAtMs": int(payload.get("updatedAtMs", 0) or 0),
            "messageCount": len(messages) if isinstance(messages, list) else 0,
        }


def make_text_content(text: str) -> list[dict[str, str]]:
    return [{"type": "text", "text": text}]
