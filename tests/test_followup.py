"""Tests for check_due_followups(): the IMAP-optional reply-detection
logic that decides whether a due follow-up gets skipped (reply found) or
sent (no reply, or IMAP not configured so a reply can't be detected)."""

import time
from unittest.mock import MagicMock, patch

from agentos import followup
from agentos.memory import default_memory


def _fake_smtp_success(*a, **kw):
    return "Email sent to a@b.co."


def test_check_due_followups_returns_a_well_formed_summary():
    """Not asserting an exact zero baseline: tests in this file (and the
    memory lifecycle tests in test_planner_and_memory.py) share one DB for
    the whole session, so an exact global count would be order-dependent
    on what other tests have scheduled/left pending. What must hold
    regardless of that: the shape is always correct and counts add up."""
    summary = followup.check_due_followups()
    assert set(summary) == {"checked", "replied", "sent", "failed"}
    assert all(isinstance(v, int) and v >= 0 for v in summary.values())
    assert summary["replied"] + summary["sent"] + summary["failed"] <= summary["checked"]


def test_sends_when_imap_not_configured(monkeypatch):
    monkeypatch.delenv("IMAP_HOST", raising=False)
    default_memory.schedule_followup(
        "a@b.co", "Re: hi", "checking in", "<no-imap@test>",
        time.time() - 10, scope="test-followup-checks")

    with patch("agentos.followup._smtp_send", side_effect=_fake_smtp_success) as mock_send:
        summary = followup.check_due_followups()

    assert summary["sent"] >= 1
    assert summary["replied"] == 0
    mock_send.assert_called()


def test_skips_send_when_reply_found(monkeypatch):
    monkeypatch.setenv("IMAP_HOST", "imap.test")
    monkeypatch.setenv("IMAP_USER", "u@test")
    monkeypatch.setenv("IMAP_PASSWORD", "pw")
    default_memory.schedule_followup(
        "a@b.co", "Re: hi", "checking in", "<has-reply@test>",
        time.time() - 10, scope="test-followup-checks")

    fake_imap = MagicMock()
    fake_imap.search.return_value = ("OK", [b"1"])  # found a match

    with patch("agentos.followup.imaplib.IMAP4_SSL", return_value=fake_imap), \
         patch("agentos.followup._smtp_send") as mock_send:
        summary = followup.check_due_followups()

    assert summary["replied"] >= 1
    mock_send.assert_not_called()
    fake_imap.login.assert_called_once_with("u@test", "pw")
    fake_imap.logout.assert_called_once()


def test_sends_when_imap_configured_but_no_reply(monkeypatch):
    monkeypatch.setenv("IMAP_HOST", "imap.test")
    monkeypatch.setenv("IMAP_USER", "u@test")
    monkeypatch.setenv("IMAP_PASSWORD", "pw")
    default_memory.schedule_followup(
        "a@b.co", "Re: hi", "checking in", "<no-reply@test>",
        time.time() - 10, scope="test-followup-checks")

    fake_imap = MagicMock()
    fake_imap.search.return_value = ("OK", [b""])  # no match

    with patch("agentos.followup.imaplib.IMAP4_SSL", return_value=fake_imap), \
         patch("agentos.followup._smtp_send", side_effect=_fake_smtp_success) as mock_send:
        summary = followup.check_due_followups()

    assert summary["sent"] >= 1
    mock_send.assert_called()


def test_reply_check_failure_falls_back_to_sending(monkeypatch):
    monkeypatch.setenv("IMAP_HOST", "imap.test")
    monkeypatch.setenv("IMAP_USER", "u@test")
    monkeypatch.setenv("IMAP_PASSWORD", "pw")
    default_memory.schedule_followup(
        "a@b.co", "Re: hi", "checking in", "<imap-broken@test>",
        time.time() - 10, scope="test-followup-checks")

    with patch("agentos.followup.imaplib.IMAP4_SSL", side_effect=OSError("connection refused")), \
         patch("agentos.followup._smtp_send", side_effect=_fake_smtp_success) as mock_send:
        summary = followup.check_due_followups()

    # a broken reply check must not silently drop a due follow-up
    assert summary["failed"] == 0
    mock_send.assert_called()


def test_marks_failed_when_send_fails(monkeypatch):
    monkeypatch.delenv("IMAP_HOST", raising=False)
    default_memory.schedule_followup(
        "a@b.co", "Re: hi", "checking in", "<send-fails@test>",
        time.time() - 10, scope="test-followup-checks")

    with patch("agentos.followup._smtp_send", return_value="Sending failed (boom)."):
        summary = followup.check_due_followups()

    assert summary["failed"] >= 1
