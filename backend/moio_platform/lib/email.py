import email
import imaplib
import os
import re
import json
from email.header import decode_header
from celery import shared_task, current_task
from django.conf import settings
import base64
import requests
from typing import Dict, Any
from django.core.mail import EmailMessage, get_connection

import logging

logger = logging.getLogger(__name__)

from central_hub.models import TenantConfiguration


def connect_to_imap(server, port, user, password):
    mail = imaplib.IMAP4_SSL(host=server, port=port)
    mail.login(user, password)
    return mail


def fetch_all_emails(mail):
    mail.select("inbox")
    status, messages = mail.search(None, 'ALL')
    email_ids = messages[0].split()

    emails = []
    for email_id in email_ids:
        status, msg_data = mail.fetch(email_id, '(RFC822)')
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                emails.append(msg)
    return emails


def process_emails(emails):
    for msg in emails:
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding if encoding else 'utf-8')

        from_email = msg.get("From")
        to_email = msg.get("To")
        date = msg.get("Date")

        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode()
                    break
        else:
            body = msg.get_payload(decode=True).decode()

        print(f"Subject: {subject}")
        print(f"From: {from_email}")
        print(f"To: {to_email}")
        print(f"Date: {date}")
        print(f"Body: {body}")
        print("-" * 50)


@shared_task
def fetch_and_process_emails():
    server = "imap.titan.email"
    email = "crm@andressa.com.uy"
    password = "S'wfreL(N=07!rP"
    port = 993

    mail = connect_to_imap(server, port, email, password)

    emails = fetch_all_emails(mail)
    process_emails(emails)
    mail.logout()


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def send_email(self, html_content, subject, to, tenant_id):

    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Email task ---> {task_id} from {q_name}')

    config = TenantConfiguration.objects.get(tenant_id=tenant_id)

    if not config.smtp_integration_enabled:
        raise Exception("SMTP integration disabled")

    connection = get_connection(
        host=config.smtp_host,
        port=config.smtp_port,
        username=config.smtp_user,
        password=config.smtp_password,
        use_tls=config.smtp_use_tls,
        from_email=config.smtp_from,
        timeout=30,
    )

    #filename =
    #excel_file = create_order_details_excel(order)

    # Create email message with attachment
    email_msg = EmailMessage(
        subject=subject,
        body=html_content,
        to=to,
        connection=connection
    )

    #email.attach(filename, excel_file.read(), 'application/vnd.ms-excel')
    email_msg.content_subtype = "html"

    # Send the email
    try:
        if email_msg.send() == 1:
            logger.info("Email sent successfully")
            return {"msg": f"Email sent successfully: task {task_id}"}
        else:
            logger.error("Email send returned non-1 status")
            return {"msg": f"Email send returned non-1 status: task {task_id}"}
    except Exception as exc:

        logger.error("SMTP send error: %s", exc)

        return {"msg": "SMTP send error"}


def extract_form_from_payload(payload: Any, media_type: str) -> Dict[str, Any]:
    """
    • From multipart payloads we only care about payload["form"].
    • From JSON (or any plain dict) we return it as-is.
    • Anything else → empty dict (handler will bail if email is missing anyway).
    """
    if media_type == "multipart/form-data":
        return payload.get("form", {})
    return payload if isinstance(payload, dict) else {}


def attach_files(email_msg: EmailMessage, files_block: Dict[str, Any]) -> None:
    """
    Attach each entry in payload["files"] to **email_msg**.
    Supports two formats:
        1. {"url": "..."}  → downloads first, then attaches
        2. {"content_base64": "..."} → decodes in-memory, then attaches
    """
    for info in files_block.values():
        filename = info.get("filename") or "attachment"
        mime     = info.get("content_type") or "application/octet-stream"
        url      = info.get("url")
        b64data  = info.get("content_base64")

        try:
            if url:
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                payload = resp.content
            elif b64data:
                payload = base64.b64decode(b64data)
            else:
                logger.debug("File entry has neither url nor base64 → skipped")
                continue

            email_msg.attach(filename, payload, mime)

        except Exception as exc:
            logger.warning("File '%s' could not be attached: %s", filename, exc)


def json_to_email_html(payload: str | dict, title: str | None = None) -> str:
    """
    Convert JSON (str or dict) to syntax-highlighted HTML for e-mail.
    No <script>, only inline <span style=""> tags.
    """
    # 1) load
    if isinstance(payload, str):
        data = json.loads(payload)
    else:
        data = payload

    # 2) pretty-print
    pretty = json.dumps(data, indent=2, ensure_ascii=False)

    # 3) escape HTML
    escaped = (
        pretty
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

    # 4) syntax-highlight
    def span(cls, text):
        styles = {
            "k": "color:#2a7ae2;font-weight:bold;",   # keys
            "s": "color:#22863a;",                    # strings
            "n": "color:#b13d00;",                    # numbers
            "b": "color:#8250df;font-style:italic;",  # booleans/null
        }
        return f'<span style="{styles[cls]}">{text}</span>'

    # keys: "key":
    escaped = re.sub(
        r'&quot;([^&]+?)&quot;(?=\s*:)',
        lambda m: span("k", m.group(0)),
        escaped
    )

    # strings: : "value"
    escaped = re.sub(
        r'(:\s*)&quot;([^&]*?)&quot;',
        lambda m: m.group(1) + span("s", f'&quot;{m.group(2)}&quot;'),
        escaped
    )

    # numbers: : 123 or 123.45
    escaped = re.sub(
        r'(:\s*)(-?\d+(\.\d+)?)',
        lambda m: m.group(1) + span("n", m.group(2)),
        escaped
    )

    # booleans/null: : true / false / null
    escaped = re.sub(
        r'(:\s*)(true|false|null)',
        lambda m: m.group(1) + span("b", m.group(2)),
        escaped,
        flags=re.IGNORECASE
    )

    # 5) wrap in styled <div>
    html_body = f'''
<div style="
     font-family: Consolas, Menlo, monospace;
     font-size: 13px;
     background: #f6f8fa;
     border: 1px solid #d0d7de;
     border-radius: 6px;
     padding: 16px;
     white-space: pre;
">
{escaped}
</div>
'''

    # optional title
    if title:
        html_body = f'<h2>{title}</h2>' + html_body

    return f'''<html><body>{html_body}</body></html>'''