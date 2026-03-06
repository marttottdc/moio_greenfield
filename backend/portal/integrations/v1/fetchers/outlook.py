from __future__ import annotations

from typing import Tuple, List, Dict, Any

import requests
from django.utils import timezone

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def fetch(state: dict | None = None) -> Tuple[List[Dict], dict]:
    """
    Incremental Outlook fetch using Graph.

    State keys:
      - last_received: ISO timestamp of most recent message processed
    """
    state = dict(state or {})
    last_received = state.get("last_received")
    credentials = state.get("_credentials") or {}
    access_token = credentials.get("access_token")
    if not access_token:
        raise ValueError("Outlook fetch requires access_token in credentials (caller must refresh).")

    params = {
        "$top": 50,
        "$orderby": "receivedDateTime desc",
        "$select": "id,conversationId,receivedDateTime,from,toRecipients,subject,bodyPreview,body",
    }
    if last_received:
        params["$filter"] = f"receivedDateTime gt {last_received}"

    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(f"{GRAPH_BASE}/me/mailFolders/Inbox/messages", headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    values = data.get("value", [])

    items: list[dict[str, Any]] = []
    new_last = None
    for msg in values:
        rid = msg.get("receivedDateTime")
        if new_last is None and rid:
            new_last = rid
        body = msg.get("body", {}) or {}
        content_type = body.get("contentType", "").lower()
        body_content = body.get("content")
        text = body_content if content_type == "text" else None
        html = body_content if content_type == "html" else None

        items.append(
            {
                "message": {
                    "id": msg.get("id"),
                    "thread_id": msg.get("conversationId"),
                    "from": (msg.get("from") or {}).get("emailAddress", {}).get("address"),
                    "to": [
                        (r or {}).get("emailAddress", {}).get("address")
                        for r in msg.get("toRecipients", []) if r
                    ],
                    "subject": msg.get("subject"),
                    "text": text,
                    "html": html,
                    "attachments": [],  # attachment metadata can be added via /messages/{id}/attachments if needed
                    "received_at": rid,
                }
            }
        )

    if new_last:
        state["last_received"] = new_last
    return items, state

