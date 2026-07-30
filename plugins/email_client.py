"""
J.A.R.V.I.S. Email Client Plugin
Read and send emails via IMAP/SMTP.
Supports Gmail, Outlook, and custom IMAP/SMTP servers.

Setup: Set environment variables:
  JARVIS_EMAIL_ADDRESS   = your_email@gmail.com
  JARVIS_EMAIL_PASSWORD  = your_app_password
  JARVIS_EMAIL_IMAP      = imap.gmail.com  (optional, auto-detected)
  JARVIS_EMAIL_SMTP      = smtp.gmail.com  (optional, auto-detected)
"""

import os
import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from datetime import datetime
from core.tool_manager import tool

# ─── Configuration ───────────────────────────────────────────────

EMAIL_ADDRESS = os.environ.get("JARVIS_EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.environ.get("JARVIS_EMAIL_PASSWORD", "")

# Auto-detect IMAP/SMTP from email domain
def _detect_servers(email_addr: str) -> tuple:
    """Detect IMAP and SMTP servers from email domain."""
    domain = email_addr.split("@")[-1].lower() if "@" in email_addr else ""
    servers = {
        "gmail.com": ("imap.gmail.com", "smtp.gmail.com"),
        "outlook.com": ("outlook.office365.com", "smtp.office365.com"),
        "hotmail.com": ("outlook.office365.com", "smtp.office365.com"),
        "yahoo.com": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com"),
    }
    return servers.get(domain, (f"imap.{domain}", f"smtp.{domain}"))

_default_imap, _default_smtp = _detect_servers(EMAIL_ADDRESS) if EMAIL_ADDRESS else ("", "")
IMAP_SERVER = os.environ.get("JARVIS_EMAIL_IMAP", _default_imap)
SMTP_SERVER = os.environ.get("JARVIS_EMAIL_SMTP", _default_smtp)


def _check_config() -> str | None:
    """Check if email is configured. Returns error string or None."""
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        return ("Email not configured. Set environment variables:\n"
                "  JARVIS_EMAIL_ADDRESS=your_email@gmail.com\n"
                "  JARVIS_EMAIL_PASSWORD=your_app_password")
    return None


def _decode_subject(raw_subject) -> str:
    """Decode email subject from encoded bytes."""
    if raw_subject is None:
        return "(No Subject)"
    decoded_parts = decode_header(raw_subject)
    parts = []
    for data, charset in decoded_parts:
        if isinstance(data, bytes):
            parts.append(data.decode(charset or "utf-8", errors="ignore"))
        else:
            parts.append(str(data))
    return " ".join(parts)


def _get_email_body(msg) -> str:
    """Extract text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    return part.get_payload(decode=True).decode("utf-8", errors="ignore")
                except Exception:
                    continue
    else:
        try:
            return msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        except Exception:
            pass
    return "(Could not extract body)"


# ─── Tools ───────────────────────────────────────────────────────

@tool(
    name="read_emails",
    description="Reads recent emails from the inbox. Returns the latest N emails with subject, sender, and snippet.",
    parameters={
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "Number of recent emails to fetch.",
                "default": 5
            },
            "folder": {
                "type": "string",
                "description": "Email folder to read from (e.g., 'INBOX', 'Sent').",
                "default": "INBOX"
            }
        }
    }
)
def read_emails(count: int = 5, folder: str = "INBOX") -> str:
    err = _check_config()
    if err:
        return err

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select(folder)

        _, message_numbers = mail.search(None, "ALL")
        msg_ids = message_numbers[0].split()

        if not msg_ids:
            mail.logout()
            return f"No emails in {folder}."

        # Get latest N
        latest_ids = msg_ids[-count:]
        latest_ids.reverse()

        emails = []
        for msg_id in latest_ids:
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = _decode_subject(msg.get("Subject"))
            sender = msg.get("From", "Unknown")
            date = msg.get("Date", "Unknown")
            body = _get_email_body(msg)[:200]

            emails.append(f"From: {sender}\nDate: {date}\nSubject: {subject}\n{body}\n")

        mail.logout()

        return f"Latest {len(emails)} email(s) from {folder}:\n\n" + "\n---\n".join(emails)

    except imaplib.IMAP4.error as e:
        return f"IMAP login failed: {e}. Check your email credentials and enable IMAP access."
    except Exception as e:
        return f"Failed to read emails: {e}"


@tool(
    name="send_email",
    description="Sends an email to a recipient.",
    parameters={
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address."
            },
            "subject": {
                "type": "string",
                "description": "Email subject line."
            },
            "body": {
                "type": "string",
                "description": "Email body text."
            }
        },
        "required": ["to", "subject", "body"]
    }
)
def send_email(to: str, subject: str, body: str) -> str:
    err = _check_config()
    if err:
        return err

    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        return f"Email sent to {to} with subject '{subject}'."

    except smtplib.SMTPAuthenticationError:
        return "SMTP auth failed. For Gmail, use an App Password (not your regular password)."
    except Exception as e:
        return f"Failed to send email: {e}"


@tool(
    name="search_emails",
    description="Searches emails by subject or sender keyword.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keyword to find in subject or sender."
            },
            "count": {
                "type": "integer",
                "description": "Max number of results to return.",
                "default": 5
            }
        },
        "required": ["query"]
    }
)
def search_emails(query: str, count: int = 5) -> str:
    err = _check_config()
    if err:
        return err

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("INBOX")

        # Search by subject
        _, subject_results = mail.search(None, f'(SUBJECT "{query}")')
        # Search by sender
        _, from_results = mail.search(None, f'(FROM "{query}")')

        # Combine and deduplicate
        all_ids = set(subject_results[0].split() + from_results[0].split())
        all_ids = sorted(all_ids, key=lambda x: int(x), reverse=True)[:count]

        if not all_ids:
            mail.logout()
            return f"No emails matching '{query}'."

        emails = []
        for msg_id in all_ids:
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = _decode_subject(msg.get("Subject"))
            sender = msg.get("From", "Unknown")
            date = msg.get("Date", "Unknown")

            emails.append(f"From: {sender} | {date}\nSubject: {subject}")

        mail.logout()
        return f"Found {len(emails)} email(s) matching '{query}':\n\n" + "\n---\n".join(emails)

    except Exception as e:
        return f"Email search failed: {e}"
