from __future__ import annotations

from typing import Dict, Any


def normalize_email(provider: str, account_id: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a raw email item into the v1 contract.
    """
    message = raw.get("message", raw)
    return {
        "provider": provider,
        "account_id": str(account_id),
        "message": {
            "id": message.get("id"),
            "thread_id": message.get("thread_id") or message.get("threadId"),
            "from": message.get("from"),
            "to": message.get("to", []),
            "subject": message.get("subject"),
            "text": message.get("text"),
            "html": message.get("html"),
            "attachments": message.get("attachments", []),
            "received_at": message.get("received_at"),
        },
    }

