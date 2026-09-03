"""web_search's provider chain and - most importantly - what it tells the
agent when every provider fails.

The failure message matters as much as the success path: the previous
version told the agent to "answer from your own knowledge", which made it
produce fluent, confident, entirely invented research that was
indistinguishable from a real answer. These tests pin the honest
behavior so it can't silently regress.
"""

from unittest.mock import MagicMock, patch

import pytest

from agentos.tools import web
from agentos.tools.web import SEARCH_FAILED_PREFIX, web_search


@pytest.fixture(autouse=True)
def _no_search_keys(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)


def _ok_response(payload):
    r = MagicMock()
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


def test_tavily_used_when_configured(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    payload = {"results": [
        {"title": "Result A", "url": "https://a.example", "content": "snippet a"},
    ]}
    with patch("agentos.tools.web.requests.post", return_value=_ok_response(payload)):
        out = web_search("anything")
    assert "Result A" in out
    assert "https://a.example" in out
    assert SEARCH_FAILED_PREFIX not in out


def test_falls_back_to_next_provider_when_tavily_errors(monkeypatch):
    """Regression: a failing Tavily call used to return immediately with
    'Tavily search failed', never trying any other provider."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-test")
    brave_payload = {"web": {"results": [
        {"title": "Brave hit", "url": "https://b.example", "description": "snippet b"},
    ]}}
    with patch("agentos.tools.web.requests.post", side_effect=Exception("tavily down")), \
         patch("agentos.tools.web.requests.get", return_value=_ok_response(brave_payload)):
        out = web_search("anything")
    assert "Brave hit" in out
    assert SEARCH_FAILED_PREFIX not in out


def test_brave_used_when_only_brave_configured(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "brave-test")
    payload = {"web": {"results": [
        {"title": "Only Brave", "url": "https://b.example", "description": "s"},
    ]}}
    with patch("agentos.tools.web.requests.get", return_value=_ok_response(payload)):
        out = web_search("anything")
    assert "Only Brave" in out


def test_total_failure_refuses_to_invent_an_answer():
    """The whole point: on total failure the agent must be told it has NO
    results and must not fall back to its own knowledge."""
    with patch.dict(web.__dict__, {"SEARCH_PROVIDERS": (
        ("Fake", lambda q: (_ for _ in ()).throw(Exception("blocked"))),
    )}):
        out = web_search("anything")

    assert out.startswith(SEARCH_FAILED_PREFIX)
    assert "blocked" in out
    lowered = out.lower()
    assert "do not write an answer from your own knowledge" in lowered
    assert "do not invent sources" in lowered
    assert "tavily_api_key" in lowered


def test_total_failure_names_each_provider_error():
    def boom(name):
        def _fail(q):
            raise RuntimeError(f"{name} exploded")
        return _fail

    with patch.dict(web.__dict__, {"SEARCH_PROVIDERS": (
        ("One", boom("one")), ("Two", boom("two")),
    )}):
        out = web_search("anything")

    assert "One: one exploded" in out
    assert "Two: two exploded" in out


def test_keyed_providers_return_none_when_unconfigured():
    """None means 'skip me', which is what lets the chain fall through to
    the next provider instead of reporting a phantom error."""
    assert web._search_tavily("q") is None
    assert web._search_brave("q") is None


def test_research_agent_is_told_search_failed_through_the_real_tool_loop(patch_llm):
    """End-to-end through the actual agent: the honest failure text must
    survive the tool loop and reach the model as the tool result. This is
    the contract that stops it inventing an answer."""
    from agentos.registry import get_agent
    from tests.conftest import fake_response, fake_tool_call

    seen_tool_messages = []
    calls = {"n": 0}

    def fake_chat(messages, tools=None, response_format=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return fake_response(
                tool_calls=[fake_tool_call("web_search", {"query": "anything"})])
        seen_tool_messages.extend(
            m["content"] for m in messages if isinstance(m, dict) and m.get("role") == "tool"
        )
        return fake_response(content="Web search is unavailable on this deployment.")

    patch_llm(fake_chat)

    with patch.dict(web.__dict__, {"SEARCH_PROVIDERS": (
        ("Fake", lambda q: (_ for _ in ()).throw(Exception("blocked by host"))),
    )}):
        out = get_agent("research").run("research anything")

    assert any(SEARCH_FAILED_PREFIX in m for m in seen_tool_messages)
    assert any("do not invent sources" in m.lower() for m in seen_tool_messages)
    assert out == "Web search is unavailable on this deployment."


def test_research_prompt_forbids_answering_from_memory():
    """Guards the prompt half of the contract: the tool can report failure
    honestly, but only the prompt stops the model papering over it."""
    from agentos.registry import get_agent

    prompt = get_agent("research").spec.system_prompt.lower()
    assert "search_failed" in prompt
    assert "never substitute your own knowledge" in prompt


def test_unconfigured_providers_are_skipped_not_reported_as_errors():
    """A provider returning None means 'no key set' - that isn't an error
    worth showing the user, unlike a provider that actually failed."""
    with patch.dict(web.__dict__, {"SEARCH_PROVIDERS": (
        ("Unconfigured", lambda q: None),
    )}):
        out = web_search("anything")

    assert out.startswith(SEARCH_FAILED_PREFIX)
    assert "no search provider is configured" in out
