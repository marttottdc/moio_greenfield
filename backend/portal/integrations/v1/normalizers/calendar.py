from __future__ import annotations

from typing import Dict, Any


def normalize_event(provider: str, account_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    event = raw.get("event", raw)
    return {
        "provider": provider,
        "account_id": str(account_id),
        "event": {
            "id": event.get("id"),
            "title": event.get("title") or event.get("summary"),
            "start": event.get("start"),
            "end": event.get("end"),
            "attendees": event.get("attendees", []),
        },
    }

