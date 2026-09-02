import json
import time
from unittest.mock import MagicMock, patch

from tests.conftest import fake_response, make_plan_json

import agentos.planner as planner
from agentos.memory import default_memory
from agentos.tools import TOOLS


def test_planner_returns_valid_structured_plan(patch_llm):
    plan = make_plan_json([
        {"agent": "research", "instruction": "look it up", "depends_on": []},
        {"agent": "writer", "instruction": "write it", "depends_on": [0]},
    ])
    patch_llm(lambda *a, **k: fake_response(content=plan))
    steps = planner.make_plan("research and write", "High")
    assert [s["agent"] for s in steps] == ["research", "writer"]
    assert steps[1]["depends_on"] == [0]


def test_planner_falls_back_to_task_step_on_failure(patch_llm):
    def broken(*a, **k):
        raise RuntimeError("API down")

    patch_llm(broken)
    steps = planner.make_plan("do something", "Low")
    assert steps == [{"agent": "task", "instruction": "do something",
                      "depends_on": []}]


def test_planner_filters_unknown_agents_and_caps_steps(patch_llm):
    bogus = [{"agent": "hacker", "instruction": "x", "depends_on": []}]
    real = [{"agent": "writer", "instruction": f"part {i}", "depends_on": []}
            for i in range(8)]
    patch_llm(lambda *a, **k: fake_response(
        content=make_plan_json(bogus + real)))
    steps = planner.make_plan("write a lot", "High")
    assert all(s["agent"] == "writer" for s in steps)
    assert len(steps) <= 5


def test_planner_includes_conversation_history(patch_llm):
    seen = {}

    def fake_chat(messages, tools=None, response_format=None):
        seen["user"] = messages[-1]["content"]
        return fake_response(content=make_plan_json(
            [{"agent": "task", "instruction": "follow up", "depends_on": []}]))

    patch_llm(fake_chat)
    planner.make_plan("make it shorter", "Medium",
                      history=[{"role": "user", "content": "write an essay"}])
    assert "Conversation history" in seen["user"]
    assert "write an essay" in seen["user"]


def test_remember_and_recall_roundtrip():
    assert "Remembered" in TOOLS["remember"]["fn"](
        key="favorite_color", value="teal")
    assert "teal" in TOOLS["recall"]["fn"](query="favorite")
    assert "No matching facts" in TOOLS["recall"]["fn"](query="zzz-nothing")


def test_send_email_uses_smtp_when_configured(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_USER", "u@test")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"], sent["port"] = host, port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, msg):
            sent["to"] = msg["To"]

    with patch("smtplib.SMTP", FakeSMTP):
        out = TOOLS["send_email"]["fn"](to="a@b.co", subject="hi", body="test")
    assert out == "Email sent to a@b.co."
    assert sent == {"host": "smtp.test", "port": 587, "tls": True,
                    "login": ("u@test", "pw"), "to": "a@b.co"}


def test_send_email_connects_with_a_socket_timeout(monkeypatch):
    """Regression guard: smtplib has no default timeout of its own, so an
    unreachable host would otherwise hang this call forever (see
    agentos/tools/mail.py's _smtp_send)."""
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_USER", "u@test")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__.return_value = MagicMock()
        TOOLS["send_email"]["fn"](to="a@b.co", subject="hi", body="test")

    _, kwargs = mock_smtp_cls.call_args
    assert kwargs.get("timeout") == 20


def test_memory_followup_lifecycle():
    followup_id = default_memory.schedule_followup(
        "a@b.co", "Re: hi", "just checking in", "<msg1@test>",
        time.time() - 10, scope="test-followups")

    due = default_memory.due_followups(time.time())
    assert any(f["id"] == followup_id for f in due)
    matched = next(f for f in due if f["id"] == followup_id)
    assert matched["to_addr"] == "a@b.co"
    assert matched["message_id"] == "<msg1@test>"

    default_memory.mark_followup(followup_id, "sent")
    due_after = default_memory.due_followups(time.time())
    assert not any(f["id"] == followup_id for f in due_after)


def test_due_followups_excludes_future_ones():
    default_memory.schedule_followup(
        "a@b.co", "Re: hi", "body", "<msg2@test>",
        time.time() + 999999, scope="test-followups")

    due = default_memory.due_followups(time.time())
    assert not any(f["message_id"] == "<msg2@test>" for f in due)


def test_schedule_follow_up_sends_and_schedules(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_USER", "u@test")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, msg):
            pass

    with patch("smtplib.SMTP", FakeSMTP):
        out = TOOLS["schedule_follow_up"]["fn"](
            to="a@b.co", subject="hi", body="initial",
            follow_up_body="checking in", send_after_days=2)

    assert "Email sent to a@b.co." in out
    assert "Follow-up scheduled in 2 day(s)" in out


def test_schedule_follow_up_does_not_schedule_when_smtp_unconfigured(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    out = TOOLS["schedule_follow_up"]["fn"](
        to="a@b.co", subject="hi", body="initial",
        follow_up_body="checking in", send_after_days=2)
    assert "NOT sent" in out
    assert "scheduled" not in out.lower()
