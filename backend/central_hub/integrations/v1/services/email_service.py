from __future__ import annotations

import base64
import json
import smtplib
from email.message import EmailMessage
from typing import Dict, Any, List, Tuple

import requests
from datetime import timezone as dt_timezone
from django.utils import timezone

from central_hub.integrations.v1.models import EmailAccount

GMAIL_API = "https://www.googleapis.com/gmail/v1/users/me"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class EmailServiceError(Exception):
    pass


# ------------------------
# Gmail
# ------------------------


def gmail_list(credentials: dict, cursor: str | None, page_size: int) -> Tuple[List[Dict[str, Any]], str | None]:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    params = {"maxResults": page_size, "labelIds": "INBOX"}
    if cursor:
        params["pageToken"] = cursor
    resp = requests.get(f"{GMAIL_API}/messages", headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for meta in data.get("messages", []):
        detail = requests.get(
            f"{GMAIL_API}/messages/{meta['id']}",
            headers=headers,
            params={"format": "full"},
            timeout=20,
        )
        detail.raise_for_status()
        msg = detail.json()
        items.append(_gmail_to_message(msg))
    return items, data.get("nextPageToken")


def gmail_get(credentials: dict, message_id: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    resp = requests.get(f"{GMAIL_API}/messages/{message_id}", headers=headers, params={"format": "full"}, timeout=20)
    resp.raise_for_status()
    return _gmail_to_message(resp.json())


def gmail_delete(credentials: dict, message_id: str) -> None:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    resp = requests.delete(f"{GMAIL_API}/messages/{message_id}", headers=headers, timeout=20)
    resp.raise_for_status()


def gmail_send(credentials: dict, payload: dict) -> str:
    headers = {"Authorization": f"Bearer {credentials['access_token']}", "Content-Type": "application/json"}
    raw_bytes = _build_rfc822(payload).as_bytes()
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode()
    resp = requests.post(f"{GMAIL_API}/messages/send", headers=headers, json={"raw": raw_b64}, timeout=20)
    resp.raise_for_status()
    return resp.json().get("id")


def _gmail_to_message(msg: dict) -> Dict[str, Any]:
    headers = _extract_headers(msg.get("payload", {}).get("headers", []))
    body_text, body_html, attachments = _parse_gmail_parts(msg.get("payload", {}).get("parts", []) or [])
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from": headers.get("from"),
        "to": _split_addresses(headers.get("to", "")),
        "subject": headers.get("subject"),
        "text": body_text,
        "html": body_html,
        "attachments": attachments,
        "received_at": _parse_timestamp_ms(msg.get("internalDate")),
    }


def _parse_timestamp_ms(ms: str | None) -> str | None:
    if not ms:
        return None
    try:
        dt = timezone.datetime.fromtimestamp(int(ms) / 1000, tz=dt_timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _extract_headers(payload_headers: list[dict[str, Any]]) -> dict[str, str]:
    return {h.get("name", "").lower(): h.get("value", "") for h in payload_headers or []}


def _parse_gmail_parts(parts: list[dict[str, Any]]) -> tuple[str | None, str | None, list]:
    text_body = None
    html_body = None
    attachments = []
    for part in parts:
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
        if part.get("parts"):
            t, h, att = _parse_gmail_parts(part.get("parts"))
            text_body = text_body or t
            html_body = html_body or h
            attachments.extend(att)
    return text_body, html_body, attachments


def _safe_decode(data_b64: str) -> str:
    try:
        return base64.urlsafe_b64decode(data_b64.encode("utf-8")).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _split_addresses(val: str) -> list[str]:
    return [a.strip() for a in val.split(",") if a.strip()]


def _build_rfc822(payload: dict) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = payload.get("subject", "")
    msg["From"] = payload.get("from") or ""
    msg["To"] = ", ".join(payload.get("to", []))
    if payload.get("cc"):
        msg["Cc"] = ", ".join(payload.get("cc", []))
    if payload.get("bcc"):
        msg["Bcc"] = ", ".join(payload.get("bcc", []))
    text = payload.get("text")
    html = payload.get("html")
    if text and html:
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
    elif html:
        msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(text or "")
    for att in payload.get("attachments", []) or []:
        data = base64.b64decode(att["content_base64"])
        msg.add_attachment(data, maintype=(att.get("mime_type") or "application").split("/")[0], subtype=(att.get("mime_type") or "octet-stream").split("/")[1], filename=att.get("filename"))
    return msg


# ------------------------
# Outlook (Microsoft Graph)
# ------------------------


def outlook_list(credentials: dict, cursor: str | None, page_size: int) -> Tuple[List[Dict[str, Any]], str | None]:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    params = {"$top": page_size, "$orderby": "receivedDateTime desc"}
    if cursor:
        params["$skiptoken"] = cursor
    resp = requests.get(f"{GRAPH_BASE}/me/mailFolders/Inbox/messages", headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = [_outlook_to_message(m) for m in data.get("value", [])]
    next_link = data.get("@odata.nextLink")
    next_cursor = None
    if next_link and "$skiptoken=" in next_link:
        next_cursor = next_link.split("$skiptoken=")[-1]
    return items, next_cursor


def outlook_get(credentials: dict, message_id: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    resp = requests.get(f"{GRAPH_BASE}/me/messages/{message_id}", headers=headers, timeout=20)
    resp.raise_for_status()
    return _outlook_to_message(resp.json())


def outlook_delete(credentials: dict, message_id: str) -> None:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    resp = requests.delete(f"{GRAPH_BASE}/me/messages/{message_id}", headers=headers, timeout=20)
    resp.raise_for_status()


def outlook_send(credentials: dict, payload: dict) -> str:
    headers = {"Authorization": f"Bearer {credentials['access_token']}", "Content-Type": "application/json"}
    message = {
        "subject": payload.get("subject", ""),
        "body": {
            "contentType": "HTML" if payload.get("html") else "Text",
            "content": payload.get("html") or payload.get("text") or "",
        },
        "toRecipients": [{"emailAddress": {"address": addr}} for addr in payload.get("to", [])],
        "ccRecipients": [{"emailAddress": {"address": addr}} for addr in payload.get("cc", [])] if payload.get("cc") else [],
        "bccRecipients": [{"emailAddress": {"address": addr}} for addr in payload.get("bcc", [])] if payload.get("bcc") else [],
    }
    # Attachments (optional)
    atts = []
    for att in payload.get("attachments", []) or []:
        atts.append(
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": att.get("filename"),
                "contentType": att.get("mime_type") or "application/octet-stream",
                "contentBytes": att.get("content_base64"),
            }
        )
    if atts:
        message["attachments"] = atts
    resp = requests.post(f"{GRAPH_BASE}/me/sendMail", headers=headers, json={"message": message}, timeout=20)
    resp.raise_for_status()
    # Graph sendMail doesn't return id; optionally fetch drafts; here we return empty
    return ""


def _outlook_to_message(msg: dict) -> Dict[str, Any]:
    body = msg.get("body", {}) or {}
    ctype = (body.get("contentType") or "").lower()
    text = body.get("content") if ctype == "text" else None
    html = body.get("content") if ctype == "html" else None
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("conversationId"),
        "from": ((msg.get("from") or {}).get("emailAddress") or {}).get("address"),
        "to": [((r.get("emailAddress") or {}).get("address")) for r in msg.get("toRecipients", []) if r.get("emailAddress")],
        "subject": msg.get("subject"),
        "text": text,
        "html": html,
        "attachments": [],  # could fetch /attachments if needed
        "received_at": msg.get("receivedDateTime"),
    }


# ------------------------
# IMAP (read) + SMTP (send)
# ------------------------


def imap_get(credentials: dict, uid: str) -> Dict[str, Any]:
    # Reuse fetch-by-uid by running a targeted IMAP fetch
    import imapclient
    import email
    from django.utils import timezone

    host = credentials["host"]
    port = credentials["port"]
    username = credentials["username"]
    password = credentials["password"]
    use_ssl = credentials.get("use_ssl", True)

    client = imapclient.IMAPClient(host, port=port, ssl=use_ssl)
    client.login(username, password)
    client.select_folder("INBOX", readonly=True)
    fetch_data = client.fetch([int(uid)], ["RFC822", "UID"])
    msg_bytes = fetch_data[int(uid)][b"RFC822"]
    msg = email.message_from_bytes(msg_bytes)
    text_body, html_body, attachments = _parse_email(msg)
    to_list = msg.get_all("to", [])
    to_flat = []
    for addr in to_list:
        to_flat.extend([a.strip() for a in addr.split(",") if a.strip()])
    client.logout()
    return {
        "id": str(uid),
        "thread_id": None,
        "from": msg.get("from"),
        "to": to_flat,
        "subject": msg.get("subject"),
        "text": text_body,
        "html": html_body,
        "attachments": attachments,
        "received_at": _parse_date(msg.get("date")),
    }


def imap_delete(credentials: dict, uid: str) -> None:
    import imapclient

    host = credentials["host"]
    port = credentials["port"]
    username = credentials["username"]
    password = credentials["password"]
    use_ssl = credentials.get("use_ssl", True)

    client = imapclient.IMAPClient(host, port=port, ssl=use_ssl)
    client.login(username, password)
    client.select_folder("INBOX", readonly=False)
    client.add_flags([int(uid)], [b"\\Deleted"])
    client.expunge()
    client.logout()


def imap_send_smtp(credentials: dict, payload: dict) -> str:
    smtp_cfg = credentials.get("smtp") or {}
    host = smtp_cfg.get("host")
    port = smtp_cfg.get("port")
    username = smtp_cfg.get("username")
    password = smtp_cfg.get("password")
    use_ssl = smtp_cfg.get("use_ssl", True)
    if not all([host, port, username, password]):
        raise EmailServiceError("SMTP credentials missing for IMAP send.")
    msg = _build_rfc822(payload)
    if use_ssl:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
    return ""  # SMTP send returns no id


def _parse_email(msg):
    import email
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
        import email.utils

        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


# ------------------------
# Dispatchers
# ------------------------


def list_messages(account: EmailAccount, cursor: str | None, page_size: int) -> tuple[list[dict], str | None]:
    creds = account.external_account.credentials
    provider = account.external_account.provider
    if provider == "google":
        return gmail_list(creds, cursor, page_size)
    if provider == "microsoft":
        return outlook_list(creds, cursor, page_size)
    if provider == "imap":
        # IMAP list uses fetcher logic; for simplicity, return empty or rely on ingestion; could implement UID window
        return [], None
    raise EmailServiceError(f"Unsupported provider: {provider}")


def get_message(account: EmailAccount, message_id: str) -> dict:
    creds = account.external_account.credentials
    provider = account.external_account.provider
    if provider == "google":
        return gmail_get(creds, message_id)
    if provider == "microsoft":
        return outlook_get(creds, message_id)
    if provider == "imap":
        return imap_get(creds, message_id)
    raise EmailServiceError(f"Unsupported provider: {provider}")


def delete_message(account: EmailAccount, message_id: str) -> None:
    creds = account.external_account.credentials
    provider = account.external_account.provider
    if provider == "google":
        return gmail_delete(creds, message_id)
    if provider == "microsoft":
        return outlook_delete(creds, message_id)
    if provider == "imap":
        return imap_delete(creds, message_id)
    raise EmailServiceError(f"Unsupported provider: {provider}")


def send_message(account: EmailAccount, payload: dict) -> str:
    creds = account.external_account.credentials
    provider = account.external_account.provider
    # Ensure From defaults to account email
    payload = dict(payload)
    payload.setdefault("from", account.external_account.email_address)
    if provider == "google":
        return gmail_send(creds, payload)
    if provider == "microsoft":
        return outlook_send(creds, payload)
    if provider == "imap":
        return imap_send_smtp(creds, payload)
    raise EmailServiceError(f"Unsupported provider: {provider}")

