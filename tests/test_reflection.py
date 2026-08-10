"""Tests for the self-improvement "lessons" loop: reflect_and_remember
(writes a lesson after an imperfect run) and relevant_lessons (agents read
them back on later runs)."""

import json

from tests.conftest import fake_response

from agentos import reflection
from agentos.memory import default_memory


def _steps(agent="research"):
    return [{"agent": agent, "instruction": "do the thing", "depends_on": []}]


def test_reflect_skips_a_clean_run(patch_llm):
    calls = {"n": 0}

    def fake_chat(messages, tools=None, response_format=None):
        calls["n"] += 1
        return fake_response(content="should not be called")

    patch_llm(fake_chat)

    reflection.reflect_and_remember(
        "do the thing", _steps(), {0: "ok"}, {0: "done"},
        verdict={"satisfied": True, "feedback": ""}, scope="test-clean")

    assert calls["n"] == 0
    assert reflection.relevant_lessons("do the thing", "test-clean") == []


def test_reflect_stores_a_lesson_on_failure(patch_llm):
    def fake_chat(messages, tools=None, response_format=None):
        return fake_response(content=json.dumps({
            "has_lesson": True,
            "topic": "js-heavy-pages",
            "lesson": "Use render_page instead of fetch_url for SPA sites.",
        }))

    patch_llm(fake_chat)

    reflection.reflect_and_remember(
        "research a JS site", _steps(), {0: "failed"},
        {0: "Step failed: empty content"}, verdict=None, scope="test-failure")

    lessons = reflection.relevant_lessons("JS site", "test-failure")
    assert lessons == ["Use render_page instead of fetch_url for SPA sites."]


def test_reflect_stores_nothing_when_model_finds_no_lesson(patch_llm):
    def fake_chat(messages, tools=None, response_format=None):
        return fake_response(content=json.dumps({
            "has_lesson": False, "topic": "", "lesson": "",
        }))

    patch_llm(fake_chat)

    reflection.reflect_and_remember(
        "do the thing", _steps(), {0: "failed"}, {0: "Step failed: transient timeout"},
        verdict=None, scope="test-no-lesson")

    assert reflection.relevant_lessons("do the thing", "test-no-lesson") == []


def test_reflect_never_raises_when_chat_fails(patch_llm):
    def fake_chat(messages, tools=None, response_format=None):
        raise RuntimeError("provider down")

    patch_llm(fake_chat)

    # must not raise
    reflection.reflect_and_remember(
        "do the thing", _steps(), {0: "failed"}, {0: "Step failed: boom"},
        verdict=None, scope="test-chat-error")


def test_reflect_fires_on_verifier_revision_even_without_a_failed_step(patch_llm):
    def fake_chat(messages, tools=None, response_format=None):
        return fake_response(content=json.dumps({
            "has_lesson": True,
            "topic": "leads",
            "lesson": "Report specific results, not a platform overview.",
        }))

    patch_llm(fake_chat)

    reflection.reflect_and_remember(
        "find leads", _steps(), {0: "ok"}, {0: "an article about platforms"},
        verdict={"satisfied": False, "feedback": "too generic"}, scope="test-revision")

    assert reflection.relevant_lessons("leads", "test-revision") == [
        "Report specific results, not a platform overview."]


def test_relevant_lessons_ignores_non_lesson_facts_and_respects_limit():
    default_memory.remember("not-a-lesson", "unrelated fact", scope="test-limit")
    for i in range(5):
        default_memory.remember(f"lesson:topic-{i}", f"lesson body {i}", scope="test-limit")

    lessons = reflection.relevant_lessons("", "test-limit", limit=3)
    assert len(lessons) == 3
    assert "unrelated fact" not in lessons


def test_agent_picks_up_a_stored_lesson(patch_llm):
    default_memory.remember(
        "lesson:calc", "Always double-check arithmetic with the calculate tool.",
        scope="test-agent-lesson")

    seen_system_prompt = {}

    def fake_chat(messages, tools=None, response_format=None):
        seen_system_prompt["content"] = messages[0]["content"]
        return fake_response(content="done")

    patch_llm(fake_chat)

    from agentos import identity
    from agentos.registry import get_agent
    import agentos.agents  # noqa: F401

    identity.set_caller("test-agent-lesson")
    try:
        get_agent("task").run("calculate something")
    finally:
        identity.set_caller(None)

    assert "double-check arithmetic" in seen_system_prompt["content"]


def test_agent_survives_a_broken_lesson_lookup(patch_llm, monkeypatch):
    """A memory-read failure while fetching lessons must never block a
    run, the same guarantee already given for a broken history read in
    Kernel.run() - this is what agents/base.py's try/except around
    relevant_lessons() exists for."""
    def broken_recall(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(default_memory, "recall", broken_recall)

    def fake_chat(messages, tools=None, response_format=None):
        return fake_response(content="done anyway")

    patch_llm(fake_chat)

    from agentos.registry import get_agent
    import agentos.agents  # noqa: F401

    assert get_agent("task").run("calculate something") == "done anyway"
