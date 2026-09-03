"""The /diagnostics self-check: it must report the TRUE state of each
dependency, never crash, and never leak secrets."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from agentos import diagnostics


def test_llm_check_reports_the_real_error():
    with patch("agentos.llm.chat", side_effect=Exception("401 invalid api key")):
        result = diagnostics._check_llm()
    assert result["ok"] is False
    assert "401 invalid api key" in result["detail"]


def test_llm_check_passes_when_a_call_succeeds():
    with patch("agentos.llm.chat", return_value=object()):
        result = diagnostics._check_llm()
    assert result["ok"] is True


def test_llm_check_flags_a_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = diagnostics._check_llm()
    assert result["ok"] is False
    assert "OPENAI_API_KEY" in result["detail"]


def test_search_check_fails_when_search_is_unavailable():
    from agentos.tools.web import SEARCH_FAILED_PREFIX

    with patch("agentos.tools.web.web_search",
              return_value=f"{SEARCH_FAILED_PREFIX}: nothing worked"):
        result = diagnostics._check_search()
    assert result["ok"] is False
    assert "TAVILY_API_KEY" in result["detail"]


def test_search_check_passes_on_real_results():
    with patch("agentos.tools.web.web_search", return_value="Title\nhttps://x\nsnippet"):
        result = diagnostics._check_search()
    assert result["ok"] is True


def test_a_crashing_check_is_reported_not_raised():
    """A diagnostics tool that 500s is worse than useless - it fails
    exactly when you need it."""
    with patch.object(diagnostics, "CHECKS", (("boom", lambda: 1 / 0),)):
        report = diagnostics.run_diagnostics()
    assert report["healthy"] is False
    assert "check crashed" in report["checks"]["boom"]["detail"]


def test_endpoint_returns_200_even_when_everything_is_broken():
    import api

    with patch("agentos.diagnostics.run_diagnostics",
              return_value={"healthy": False, "checks": {}, "optional": {}}):
        r = TestClient(api.app).get("/diagnostics")
    assert r.status_code == 200
    assert r.json()["healthy"] is False


def test_report_never_contains_secret_values(monkeypatch):
    """Keys must be reported as present/absent only - this endpoint is
    unauthenticated by design."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-supersecret-value")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-supersecret-value")
    monkeypatch.setenv("META_APP_SECRET", "meta-supersecret-value")

    with patch("agentos.llm.chat", side_effect=Exception("nope")), \
         patch("agentos.tools.web.web_search", return_value="ok\nhttps://x\ns"):
        report = diagnostics.run_diagnostics()

    assert "supersecret" not in str(report)
