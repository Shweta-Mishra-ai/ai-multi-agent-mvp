"""Regression tests for the SSRF redirect-bypass fix and the response
size cap in fetch_url (found during the production audit)."""

from unittest.mock import MagicMock, patch

from agentos.tools.web import MAX_FETCH_BYTES, fetch_url


def _resp(status_redirect=False, permanent_redirect=False, location=None,
         chunks=None, encoding="utf-8"):
    r = MagicMock()
    r.is_redirect = status_redirect
    r.is_permanent_redirect = permanent_redirect
    r.headers = {"location": location} if location else {}
    r.encoding = encoding
    r.iter_content.return_value = iter(chunks or [b"hello world"])
    r.raise_for_status.return_value = None
    return r


def test_redirect_to_internal_address_is_blocked_not_followed():
    """The core SSRF fix: a redirect target must be re-validated - it must
    NOT be followed blindly the way requests' allow_redirects=True would."""
    first = _resp(status_redirect=True, location="http://127.0.0.1/secret")
    # is_safe_url does a real DNS lookup; fake the per-hop verdicts instead
    # of depending on network/DNS being reachable from the test sandbox.
    with patch("agentos.security.is_safe_url",
              side_effect=lambda u: "127.0.0.1" not in u) as mock_safe, \
         patch("agentos.tools.web.requests.get", return_value=first) as mock_get:
        result = fetch_url(url="https://public-site.example/redirector")
    assert "Blocked" in result
    assert "127.0.0.1" in result
    assert mock_safe.call_count == 2  # original hop, then the redirect target
    # only the first (safe) hop should have actually been requested
    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["allow_redirects"] is False


def test_redirect_chain_to_safe_url_is_followed_and_fetched():
    first = _resp(status_redirect=True, location="https://public-site.example/final")
    second = _resp(chunks=[b"<html><body>Hello</body></html>"])
    with patch("agentos.security.is_safe_url", return_value=True), \
         patch("agentos.tools.web.requests.get", side_effect=[first, second]):
        result = fetch_url(url="https://public-site.example/redirector")
    assert "Hello" in result


def test_too_many_redirects_gives_up():
    hop = _resp(status_redirect=True, location="https://public-site.example/next")
    with patch("agentos.security.is_safe_url", return_value=True), \
         patch("agentos.tools.web.requests.get", return_value=hop):
        result = fetch_url(url="https://public-site.example/start")
    assert "too many redirects" in result


def test_response_body_is_capped_to_bound_memory():
    big_chunk = b"x" * (MAX_FETCH_BYTES // 2 + 1)
    resp = _resp(chunks=[big_chunk, big_chunk, big_chunk])
    with patch("agentos.security.is_safe_url", return_value=True), \
         patch("agentos.tools.web.requests.get", return_value=resp):
        result = fetch_url(url="https://public-site.example/huge")
    # should not raise / hang, and returns a bounded, truncated result
    assert isinstance(result, str)
    assert len(result) <= 6000
