# email_utils.py
import imaplib
import email
from email.header import decode_header
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.utils import timezone
from chatbot.models.email_data import EmailMessage


def sync_email_account(email_account):
    """
    Connects to the IMAP server and fetches emails for the given EmailAccount.
    New emails (by Message-ID) are saved to the database.
    """
    imap_host = email_account.imap_server
    imap_user = email_account.username
    imap_pass = email_account.password
    use_ssl = email_account.use_ssl

    try:
        if use_ssl:
            mail = imaplib.IMAP4_SSL(imap_host)
        else:
            mail = imaplib.IMAP4(imap_host)

        mail.login(imap_user, imap_pass)
        mail.select("INBOX")

        # Search for all emails in the INBOX
        status, messages = mail.search(None, 'ALL')
        email_ids = messages[0].split()

        for email_id in email_ids:
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            message_id = msg.get('Message-ID')
            if not message_id:
                continue

            # Skip if this email is already stored
            if EmailMessage.objects.filter(message_id=message_id).exists():
                continue

            # Decode subject
            subject_tuple = decode_header(msg.get('Subject'))[0]
            subject = subject_tuple[0]
            encoding = subject_tuple[1]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else 'utf-8')

            sender = msg.get('From')
            recipients = msg.get('To')
            date_str = msg.get('Date')
            try:
                date_received = email.utils.parsedate_to_datetime(date_str)
            except Exception:
                date_received = timezone.now()

            # Extract plain text body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    if content_type == "text/plain" and "attachment" not in content_disposition:
                        try:
                            body = part.get_payload(decode=True).decode()
                        except Exception:
                            body = ""
                        break
            else:
                try:
                    body = msg.get_payload(decode=True).decode()
                except Exception:
                    body = ""

            # Save the email message to the database
            email_message = EmailMessage(
                tenant=email_account.tenant,
                account=email_account,
                message_id=message_id,
                subject=subject,
                sender=sender,
                recipients=recipients,
                body=body,
                date_received=date_received,
                folder='Inbox'
            )
            email_message.save()

        email_account.last_synced = timezone.now()
        email_account.save()
    except Exception as e:
        # In production, log the error appropriately.
        print(f"Error syncing account {email_account.email_address}: {e}")
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def send_email(email_account, to_address, subject, body):
    """
    Sends an email using SMTP for the given EmailAccount.
    """
    smtp_server = email_account.smtp_server
    smtp_user = email_account.username
    smtp_pass = email_account.password
    from_address = email_account.email_address

    msg = MIMEMultipart()
    msg['From'] = from_address
    msg['To'] = to_address
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, 587)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_address, to_address, msg.as_string())
    except Exception as e:
        print(f"Error sending email from {from_address} to {to_address}: {e}")
    finally:
        try:
            server.quit()
        except Exception:
            pass


def search_emails(email_account, query):
    """
    Searches for emails in the given EmailAccount that match the query
    in the subject, sender, or body.
    """
    from django.db.models import Q
    return EmailMessage.objects.filter(
        account=email_account
    ).filter(
        Q(subject__icontains=query) | Q(sender__icontains=query) | Q(body__icontains=query)
    )
