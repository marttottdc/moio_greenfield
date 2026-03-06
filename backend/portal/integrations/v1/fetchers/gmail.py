from __future__ import annotations

import time
from typing import Tuple, List, Dict, Any

import requests
from datetime import timezone as dt_timezone
from django.utils import timezone

GMAIL_API = "https://www.googleapis.com/gmail/v1/users/me"


def _header(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _extract_headers(payload_headers: list[dict[str, Any]]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in payload_headers or []}


def _parse_timestamp_ms(ms: str | None) -> str | None:
    if not ms:
        return None
    try:
        dt = timezone.datetime.fromtimestamp(int(ms) / 1000, tz=dt_timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _parse_parts(parts: list[dict[str, Any]], attachments: list) -> tuple[str | None, str | None]:
    """Traverse MIME parts to gather text/plain and text/html bodies and attachment metadata."""
    text_body = None
    html_body = None
    for part in parts or []:
        mime_type = part.get("mimeType")
        body = part.get("body", {})
        data = body.get("data")
        filename = part.get("filename")
        if filename:
            attachments.append(
                {
                    "filename": filename,
                    "mime_type": mime_type,
                    "size": body.get("size"),
                    "attachment_id": body.get("attachmentId"),
                }
            )
        if mime_type == "text/plain" and data:
            text_body = _safe_decode(data)
        elif mime_type == "text/html" and data:
            html_body = _safe_decode(data)
        elif part.get("parts"):
            t, h = _parse_parts(part.get("parts"), attachments)
            text_body = text_body or t
            html_body = html_body or h
    return text_body, html_body


def _safe_decode(data_b64: str) -> str:
    import base64

    try:
        return base64.urlsafe_b64decode(data_b64.encode("utf-8")).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def fetch(state: dict | None = None) -> Tuple[List[Dict], dict]:
    """
    Incremental Gmail fetch using message listing.

    State keys:
      - last_message_id: str | None
    """
    from portal.integrations.v1.services.token_service import _require_setting  # lazy import to avoid cycles

    state = dict(state or {})
    last_seen = state.get("last_message_id")
    credentials = state.get("_credentials") or {}
    access_token = credentials.get("access_token")
    if not access_token:
        raise ValueError("Gmail fetch requires access_token in credentials (caller must refresh).")

    params = {"maxResults": 50, "labelIds": "INBOX"}
    items: list[dict[str, Any]] = []
    new_last = None

    # List latest messages
    resp = requests.get(f"{GMAIL_API}/messages", headers=_header(access_token), params=params, timeout=20)
    resp.raise_for_status()
    messages = resp.json().get("messages", [])

    for msg_meta in messages:
        msg_id = msg_meta.get("id")
        if not msg_id:
            continue
        if new_last is None:
            new_last = msg_id
        if last_seen and msg_id == last_seen:
            break  # stop at already processed boundary

        detail = requests.get(
            f"{GMAIL_API}/messages/{msg_id}",
            headers=_header(access_token),
            params={"format": "full"},
            timeout=20,
        )
        detail.raise_for_status()
        msg = detail.json()
        payload = msg.get("payload", {}) or {}
        headers = _extract_headers(payload.get("headers", []))
        attachments: list[dict[str, Any]] = []
        text_body, html_body = _parse_parts(payload.get("parts", []), attachments)

        items.append(
            {
                "message": {
                    "id": msg_id,
                    "thread_id": msg.get("threadId"),
                    "from": headers.get("from"),
                    "to": [addr.strip() for addr in headers.get("to", "").split(",") if addr.strip()],
                    "subject": headers.get("subject"),
                    "text": text_body,
                    "html": html_body,
                    "attachments": attachments,
                    "received_at": _parse_timestamp_ms(msg.get("internalDate")),
                }
            }
        )

    if new_last:
        state["last_message_id"] = new_last
    return items, state

