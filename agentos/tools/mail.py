import os
import smtplib
import time
from email.mime.text import MIMEText
from email.utils import make_msgid

from agentos.tools import tool


def _smtp_send(to, subject, body, message_id=None, in_reply_to=None):
    """The actual SMTP send - shared by send_email and schedule_follow_up
    (both its immediate send and the later automatic follow-up send in
    agentos/followup.py) so there's exactly one send path to keep correct,
    not several that could drift out of sync."""
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    if not (host and user and password):
        return (
            "SMTP is not configured, so the email was NOT sent. "
            "Present the draft below to the user so they can send it manually.\n\n"
            f"To: {to}\nSubject: {subject}\n\n{body}"
        )

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = os.getenv("SMTP_FROM", user)
        msg["To"] = to
        msg["Message-ID"] = message_id or make_msgid()
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        # timeout=20: without it, a misconfigured/unreachable host that
        # black-holes packets (rather than refusing the connection) hangs
        # this call forever instead of failing - unlike every other network
        # call in this codebase, smtplib has no default timeout of its own.
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return f"Email sent to {to}."
    except Exception as e:
        return f"Sending failed ({e}). Draft:\n\nTo: {to}\nSubject: {subject}\n\n{body}"


@tool(
    "Send an email. Only works when SMTP is configured via environment "
    "variables (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD); "
    "otherwise returns the draft for the user to send manually.",
    {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
    requires_approval=True,
)
def send_email(to, subject, body):
    return _smtp_send(to, subject, body)


@tool(
    "Send an email now AND schedule an automatic follow-up if there's no "
    "reply by then. Approving this means the follow-up WILL send itself "
    "automatically later, without asking again. Only works when SMTP is "
    "configured (same as send_email); the follow-up still sends on "
    "schedule even without IMAP configured on this deployment - it just "
    "can't detect a reply and skip sending in that case.",
    {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "follow_up_body": {
                "type": "string",
                "description": "the follow-up message to send if there's no reply",
            },
            "send_after_days": {
                "type": "number",
                "description": "days to wait for a reply before following up",
            },
        },
        "required": ["to", "subject", "body", "follow_up_body", "send_after_days"],
    },
    requires_approval=True,
)
def schedule_follow_up(to, subject, body, follow_up_body, send_after_days):
    from agentos import identity
    from agentos.memory import default_memory

    message_id = make_msgid()
    result = _smtp_send(to, subject, body, message_id=message_id)
    if not result.startswith("Email sent"):
        return result

    scheduled_at = time.time() + max(send_after_days, 0) * 86400
    default_memory.schedule_followup(
        to, f"Re: {subject}", follow_up_body, message_id,
        scheduled_at, scope=identity.scope())
    return (f"{result} Follow-up scheduled in {send_after_days} day(s) "
            "if there's no reply by then.")
