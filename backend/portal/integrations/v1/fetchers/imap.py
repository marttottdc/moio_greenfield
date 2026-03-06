from __future__ import annotations

from typing import Tuple, List, Dict, Any

import email
import imapclient
from datetime import timezone as dt_timezone
from django.utils import timezone

from portal.integrations.v1.normalizers.email import normalize_email  # for types, not used here


def fetch(state: dict | None = None) -> Tuple[List[Dict], dict]:
    """
    Incremental IMAP fetch based on last_uid.

    Expected credentials in state["_credentials"]:
      - host, port, username, password, use_ssl
    """
    state = dict(state or {})
    last_uid = state.get("last_uid")
    creds = state.get("_credentials") or {}
    host = creds.get("host")
    port = creds.get("port")
    username = creds.get("username")
    password = creds.get("password")
    use_ssl = creds.get("use_ssl", True)
    if not all([host, port, username, password]):
        raise ValueError("IMAP credentials missing")

    client = imapclient.IMAPClient(host, port=port, ssl=use_ssl)
    client.login(username, password)
    client.select_folder("INBOX", readonly=True)

    search_query = ["UID", f"{(last_uid or 0) + 1}:*"]
    uids = client.search(search_query)
    items: list[dict[str, Any]] = []
    new_last = last_uid

    if uids:
        fetch_data = client.fetch(uids, ["RFC822", "UID"])
        for uid in sorted(fetch_data.keys()):
            msg_bytes = fetch_data[uid][b"RFC822"]
            msg = email.message_from_bytes(msg_bytes)
            new_last = max(new_last or 0, uid)

            # Extract bodies
            text_body, html_body, attachments = _parse_email(msg)
            received_at = _parse_date(msg.get("date"))
            to_list = msg.get_all("to", [])
            to_flat = []
            for addr in to_list:
                to_flat.extend([a.strip() for a in addr.split(",") if a.strip()])

            items.append(
                {
                    "message": {
                        "id": str(uid),
                        "thread_id": None,
                        "from": msg.get("from"),
                        "to": to_flat,
                        "subject": msg.get("subject"),
                        "text": text_body,
                        "html": html_body,
                        "attachments": attachments,
                        "received_at": received_at,
                    }
                }
            )

    client.logout()
    if new_last:
        state["last_uid"] = new_last
    return items, state


def _parse_email(msg: email.message.Message):
    text_body = None
    html_body = None
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            content_disposition = part.get("Content-Disposition", "")
            if part.get_content_maintype() == "multipart":
                continue
            if "attachment" in content_disposition.lower():
                attachments.append(
                    {
                        "filename": part.get_filename(),
                        "mime_type": part.get_content_type(),
                        "size": len(part.get_payload(decode=True) or b""),
                    }
                )
            elif part.get_content_type() == "text/plain":
                text_body = (part.get_payload(decode=True) or b"").decode(errors="ignore")
            elif part.get_content_type() == "text/html":
                html_body = (part.get_payload(decode=True) or b"").decode(errors="ignore")
    else:
        if msg.get_content_type() == "text/plain":
            text_body = (msg.get_payload(decode=True) or b"").decode(errors="ignore")
        elif msg.get_content_type() == "text/html":
            html_body = (msg.get_payload(decode=True) or b"").decode(errors="ignore")
    return text_body, html_body, attachments


def _parse_date(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt.isoformat()
    except Exception:
        return None

