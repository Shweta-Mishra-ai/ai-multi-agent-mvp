"""Tests for the real-listing freelance job search tool."""

from unittest.mock import MagicMock, patch

from agentos.tools.jobs import find_freelance_jobs

FEED = [
    {"legal": "https://remoteok.com/legal"},  # first element is not a job
    {"position": "React Developer", "company": "Acme Co",
     "tags": ["react", "javascript"], "url": "https://remoteok.com/l/1"},
    {"position": "Content Writer", "company": "Blog Inc",
     "tags": ["writing", "content"], "url": "https://remoteok.com/l/2"},
]


def _resp(json_body):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = json_body
    return r


def test_find_freelance_jobs_filters_by_query():
    with patch("agentos.tools.jobs.requests.get", return_value=_resp(FEED)):
        result = find_freelance_jobs(query="react")
    assert "React Developer @ Acme Co" in result
    assert "https://remoteok.com/l/1" in result
    assert "Content Writer" not in result


def test_find_freelance_jobs_skips_the_legal_notice_entry():
    with patch("agentos.tools.jobs.requests.get", return_value=_resp(FEED)):
        result = find_freelance_jobs(query="")
    assert "React Developer" in result and "Content Writer" in result
    assert "legal" not in result.lower()


def test_find_freelance_jobs_reports_no_matches():
    with patch("agentos.tools.jobs.requests.get", return_value=_resp(FEED)):
        result = find_freelance_jobs(query="nonexistent-skill-xyz")
    assert "No live listings matched" in result


def test_find_freelance_jobs_handles_provider_failure():
    with patch("agentos.tools.jobs.requests.get", side_effect=ConnectionError("boom")):
        result = find_freelance_jobs(query="react")
    assert "unavailable" in result
