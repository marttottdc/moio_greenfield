from __future__ import annotations

from typing import Tuple, List, Dict, Any

import requests
from django.utils import timezone

CAL_API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def fetch(state: dict | None = None) -> Tuple[List[Dict], dict]:
    """
    Incremental Google Calendar fetch using syncToken when available.

    State keys:
      - sync_token: str (from previous response)
    """
    state = dict(state or {})
    sync_token = state.get("sync_token")
    credentials = state.get("_credentials") or {}
    access_token = credentials.get("access_token")
    if not access_token:
        raise ValueError("Google Calendar fetch requires access_token in credentials.")

    headers = {"Authorization": f"Bearer {access_token}"}
    params: dict[str, Any] = {"maxResults": 50, "singleEvents": "true", "orderBy": "startTime"}
    if sync_token:
        params["syncToken"] = sync_token
    else:
        # pull last 30 days forward
        start = (timezone.now() - timezone.timedelta(days=30)).isoformat()
        params["timeMin"] = start

    resp = requests.get(CAL_API, headers=headers, params=params, timeout=20)
    if resp.status_code == 410:
        # sync token expired -> reset
        state.pop("sync_token", None)
        return [], state
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])

    normalized = []
    for ev in items:
        start = ev.get("start", {})
        end = ev.get("end", {})
        normalized.append(
            {
                "event": {
                    "id": ev.get("id"),
                    "title": ev.get("summary"),
                    "start": start.get("dateTime") or start.get("date"),
                    "end": end.get("dateTime") or end.get("date"),
                    "attendees": [a.get("email") for a in ev.get("attendees", []) if a.get("email")],
                }
            }
        )

    next_sync = data.get("nextSyncToken")
    if next_sync:
        state["sync_token"] = next_sync
    return normalized, state

