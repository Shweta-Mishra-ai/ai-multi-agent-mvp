"""Checks due email follow-ups and sends the ones that still need to go
out - called by /internal/check-followups, which a scheduled GitHub
Actions workflow hits on a timer (see .github/workflows/
email-followup-cron.yml). Not an in-process scheduler: Render's free tier
spins the web service down after 15 minutes of no HTTP traffic, so an
in-process ticker would simply stop running while idle - a request from
outside is what wakes it up and drives this instead."""

import imaplib
import os
import time

from agentos.log import get_logger
from agentos.memory import default_memory
from agentos.tools.mail import _smtp_send

log = get_logger("agentos.followup")


def _has_reply(message_id):
    """True/False if IMAP is configured and a reply to this Message-ID
    was found in INBOX (via HEADER search on In-Reply-To/References - the
    correct way to detect a threaded reply, not a subject/sender guess
    that could false-match an unrelated email). None if IMAP isn't
    configured, so the caller can tell "no reply" apart from "can't check"
    and default to sending rather than silently dropping a due follow-up.
    Only searches INBOX; a mail filter that files replies elsewhere would
    be missed - a known limitation for v1."""
    host = os.getenv("IMAP_HOST")
    user = os.getenv("IMAP_USER")
    password = os.getenv("IMAP_PASSWORD")
    if not (host and user and password):
        return None

    imap = imaplib.IMAP4_SSL(host)
    try:
        imap.login(user, password)
        imap.select("INBOX", readonly=True)
        for header in ("In-Reply-To", "References"):
            typ, data = imap.search(None, "HEADER", header, message_id)
            if typ == "OK" and data and data[0]:
                return True
        return False
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def check_due_followups():
    """For each follow-up whose scheduled time has arrived: skip it if a
    reply was found (IMAP configured) or send it (no reply found, or IMAP
    not configured so a reply can't be detected either way). Returns a
    summary dict for the caller (the cron endpoint) to report."""
    summary = {"checked": 0, "replied": 0, "sent": 0, "failed": 0}

    for followup in default_memory.due_followups(time.time()):
        summary["checked"] += 1
        try:
            replied = _has_reply(followup["message_id"])
        except Exception as e:
            log.warning("reply check failed for %s: %s", followup["id"], e)
            replied = None

        if replied:
            default_memory.mark_followup(followup["id"], "replied")
            summary["replied"] += 1
            continue

        result = _smtp_send(
            followup["to_addr"], followup["subject"], followup["body"],
            in_reply_to=followup["message_id"])
        if result.startswith("Email sent"):
            default_memory.mark_followup(followup["id"], "sent")
            summary["sent"] += 1
        else:
            log.warning("follow-up send failed for %s: %s", followup["id"], result)
            summary["failed"] += 1

    return summary
