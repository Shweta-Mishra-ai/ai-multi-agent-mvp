import os
import smtplib
from email.mime.text import MIMEText

from agentos.tools import tool


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
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587"))) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return f"Email sent to {to}."
    except Exception as e:
        return f"Sending failed ({e}). Draft:\n\nTo: {to}\nSubject: {subject}\n\n{body}"
