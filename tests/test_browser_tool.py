"""Tests for the render_page tool - the AgentOS-side client for the
separately deployed browser worker service."""

from unittest.mock import MagicMock, patch

from agentos.tools.browser import render_page


def _resp(status_code=200, json_body=None, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.json.return_value = json_body or {}
    if status_code >= 400:
        import requests
        r.raise_for_status.side_effect = requests.exceptions.HTTPError(response=r)
    else:
        r.raise_for_status.return_value = None
    return r


def test_render_page_not_configured(monkeypatch):
    monkeypatch.delenv("BROWSER_WORKER_URL", raising=False)
    monkeypatch.delenv("BROWSER_WORKER_TOKEN", raising=False)
    result = render_page(url="https://example.com")
    assert "not configured" in result


def test_render_page_success(monkeypatch):
    monkeypatch.setenv("BROWSER_WORKER_URL", "https://worker.example/")
    monkeypatch.setenv("BROWSER_WORKER_TOKEN", "secret-token")

    ok = _resp(json_body={"title": "Example Domain", "text": "This is an example page."})
    with patch("agentos.tools.browser.requests.post", return_value=ok) as mock_post:
        result = render_page(url="https://example.com")

    assert "Example Domain" in result
    assert "This is an example page." in result
    call = mock_post.call_args
    assert call.args[0] == "https://worker.example/render"
    assert call.kwargs["json"] == {"url": "https://example.com"}
    assert call.kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_render_page_reports_worker_error(monkeypatch):
    monkeypatch.setenv("BROWSER_WORKER_URL", "https://worker.example")
    monkeypatch.setenv("BROWSER_WORKER_TOKEN", "secret-token")

    failed = _resp(status_code=422, json_body={"detail": "not a safe public http(s) URL"})
    with patch("agentos.tools.browser.requests.post", return_value=failed):
        result = render_page(url="http://127.0.0.1/secret")

    assert "not a safe public" in result


def test_render_page_handles_connection_failure(monkeypatch):
    monkeypatch.setenv("BROWSER_WORKER_URL", "https://worker.example")
    monkeypatch.setenv("BROWSER_WORKER_TOKEN", "secret-token")

    with patch("agentos.tools.browser.requests.post", side_effect=ConnectionError("boom")):
        result = render_page(url="https://example.com")

    assert "unavailable" in result
