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


def test_unconfigured_providers_are_skipped_not_reported_as_errors():
    """A provider returning None means 'no key set' - that isn't an error
    worth showing the user, unlike a provider that actually failed."""
    with patch.dict(web.__dict__, {"SEARCH_PROVIDERS": (
        ("Unconfigured", lambda q: None),
    )}):
        out = web_search("anything")

    assert out.startswith(SEARCH_FAILED_PREFIX)
    assert "no search provider is configured" in out
