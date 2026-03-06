from __future__ import annotations

from typing import Tuple, List, Dict, Any

import requests
from django.utils import timezone

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def fetch(state: dict | None = None) -> Tuple[List[Dict], dict]:
    """
    Incremental Outlook Calendar fetch using modified time anchor.

    State keys:
      - last_modified: ISO datetime of last event seen
    """
    state = dict(state or {})
    last_modified = state.get("last_modified")
    credentials = state.get("_credentials") or {}
    access_token = credentials.get("access_token")
    if not access_token:
        raise ValueError("Outlook Calendar fetch requires access_token in credentials.")

    params = {"$top": 50, "$orderby": "lastModifiedDateTime desc"}
    if last_modified:
        params["$filter"] = f"lastModifiedDateTime gt {last_modified}"
    else:
        start = (timezone.now() - timezone.timedelta(days=30)).isoformat()
        params["$filter"] = f"start/dateTime ge {start}"

    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(f"{GRAPH_BASE}/me/events", headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    values = data.get("value", [])

    items: list[dict[str, Any]] = []
    new_anchor = None
    for ev in values:
        lm = ev.get("lastModifiedDateTime")
        if new_anchor is None and lm:
            new_anchor = lm
        start = ev.get("start", {}) or {}
        end = ev.get("end", {}) or {}
        items.append(
            {
                "event": {
                    "id": ev.get("id"),
                    "title": ev.get("subject"),
                    "start": start.get("dateTime"),
                    "end": end.get("dateTime"),
                    "attendees": [
                        (a.get("emailAddress") or {}).get("address")
                        for a in ev.get("attendees", [])
                        if a.get("emailAddress")
                    ],
                }
            }
        )

    if new_anchor:
        state["last_modified"] = new_anchor
    return items, state

