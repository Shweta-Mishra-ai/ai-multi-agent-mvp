import json
from unittest.mock import patch

from tests.conftest import fake_response, make_plan_json

import agentos.planner as planner
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
        def __init__(self, host, port):
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
