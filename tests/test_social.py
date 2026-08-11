"""Instagram/LinkedIn posting: OAuth state, token exchange, and posting
logic (agentos/oauth_state.py, agentos/social_instagram.py,
agentos/social_linkedin.py), plus the social_accounts storage in
agentos/memory.py and the post_to_instagram/post_to_linkedin tools.

IMPORTANT: these tests verify AgentOS's own logic using mocked HTTP
responses. They do NOT exercise a real round trip against Meta's or
LinkedIn's servers - that requires a real Meta/LinkedIn Developer app and
a public HTTPS callback URL, neither available in this environment. See
the README's social posting section for what the deployment operator
must set up before this feature works for real.
"""

from unittest.mock import MagicMock, patch

import pytest

from agentos import social_instagram, social_linkedin
from agentos.memory import Memory
from agentos.oauth_state import OAuthStates


# --- oauth_state.py: shared CSRF helper ---

def test_state_is_single_use():
    states = OAuthStates()
    state = states.issue()
    assert states.consume(state) is True
    assert states.consume(state) is False
    assert states.consume("never-issued") is False


def test_expired_state_is_rejected(monkeypatch):
    import time as time_module

    states = OAuthStates()
    real_now = time_module.time()
    state = states.issue()
    monkeypatch.setattr(time_module, "time", lambda: real_now + 9999)
    assert states.consume(state) is False


def test_states_from_different_instances_are_independent():
    a, b = OAuthStates(), OAuthStates()
    state = a.issue()
    assert b.consume(state) is False  # not issued by b
    assert a.consume(state) is True


# --- agentos/social_instagram.py ---

@pytest.fixture(autouse=True)
def _social_env(monkeypatch):
    monkeypatch.setenv("META_APP_ID", "test-app-id")
    monkeypatch.setenv("META_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "test-client-secret")
    yield


def _fake_response(json_data, ok=True, headers=None):
    r = MagicMock()
    r.json.return_value = json_data
    r.headers = headers or {}
    if ok:
        r.raise_for_status.return_value = None
    else:
        r.raise_for_status.side_effect = Exception("HTTP error")
    return r


def test_instagram_is_configured_reflects_env_vars(monkeypatch):
    assert social_instagram.is_configured() is True
    monkeypatch.delenv("META_APP_ID", raising=False)
    assert social_instagram.is_configured() is False


def test_instagram_build_authorize_url_contains_required_params():
    url = social_instagram.build_authorize_url("https://example.com/callback")
    assert url.startswith(social_instagram.AUTHORIZE_URL)
    assert "client_id=test-app-id" in url
    assert "redirect_uri=" in url
    assert "state=" in url
    assert "scope=" in url


def test_instagram_exchange_code_for_account_success():
    short_lived = _fake_response({"access_token": "short-token"})
    long_lived = _fake_response({"access_token": "long-token", "expires_in": 5184000})
    pages = _fake_response({"data": [{"id": "page-1"}]})
    page_ig = _fake_response({"instagram_business_account": {"id": "ig-123"}})

    with patch("agentos.social_instagram.requests.get",
              side_effect=[short_lived, long_lived, pages, page_ig]):
        token, ig_id, expires_at = social_instagram.exchange_code_for_account(
            "fake-code", "https://x/callback")
    assert token == "long-token"
    assert ig_id == "ig-123"
    assert expires_at > 0


def test_instagram_exchange_raises_when_no_pages():
    short_lived = _fake_response({"access_token": "short-token"})
    long_lived = _fake_response({"access_token": "long-token"})
    pages = _fake_response({"data": []})

    with patch("agentos.social_instagram.requests.get",
              side_effect=[short_lived, long_lived, pages]):
        with pytest.raises(ValueError):
            social_instagram.exchange_code_for_account("fake-code", "https://x/callback")


def test_instagram_exchange_raises_when_no_linked_ig_account():
    short_lived = _fake_response({"access_token": "short-token"})
    long_lived = _fake_response({"access_token": "long-token"})
    pages = _fake_response({"data": [{"id": "page-1"}]})
    page_ig = _fake_response({})  # no instagram_business_account field

    with patch("agentos.social_instagram.requests.get",
              side_effect=[short_lived, long_lived, pages, page_ig]):
        with pytest.raises(ValueError):
            social_instagram.exchange_code_for_account("fake-code", "https://x/callback")


def test_instagram_exchange_propagates_http_errors():
    bad = _fake_response({}, ok=False)
    with patch("agentos.social_instagram.requests.get", return_value=bad):
        with pytest.raises(Exception):
            social_instagram.exchange_code_for_account("bad-code", "https://x/callback")


def test_instagram_publish_photo_two_step():
    container = _fake_response({"id": "container-1"})
    published = _fake_response({"id": "media-999"})
    with patch("agentos.social_instagram.requests.post",
              side_effect=[container, published]) as mock_post:
        post_id = social_instagram.publish_photo(
            "token", "ig-123", "https://img.example/x.jpg", "hello world")
    assert post_id == "media-999"
    assert mock_post.call_count == 2


# --- agentos/social_linkedin.py ---

def test_linkedin_is_configured_reflects_env_vars(monkeypatch):
    assert social_linkedin.is_configured() is True
    monkeypatch.delenv("LINKEDIN_CLIENT_ID", raising=False)
    assert social_linkedin.is_configured() is False


def test_linkedin_build_authorize_url_contains_required_params():
    url = social_linkedin.build_authorize_url("https://example.com/callback")
    assert url.startswith(social_linkedin.AUTHORIZE_URL)
    assert "client_id=test-client-id" in url
    assert "redirect_uri=" in url
    assert "state=" in url
    assert "scope=" in url


def test_linkedin_exchange_code_for_member_success():
    token_resp = _fake_response({"access_token": "fake-token", "expires_in": 5184000})
    userinfo_resp = _fake_response({"sub": "abc123"})
    with patch("agentos.social_linkedin.requests.post", return_value=token_resp), \
         patch("agentos.social_linkedin.requests.get", return_value=userinfo_resp):
        token, urn, expires_at = social_linkedin.exchange_code_for_member(
            "fake-code", "https://x/callback")
    assert token == "fake-token"
    assert urn == "urn:li:person:abc123"
    assert expires_at > 0


def test_linkedin_exchange_propagates_http_errors():
    bad = _fake_response({}, ok=False)
    with patch("agentos.social_linkedin.requests.post", return_value=bad):
        with pytest.raises(Exception):
            social_linkedin.exchange_code_for_member("bad-code", "https://x/callback")


def test_linkedin_publish_text_post_returns_urn_from_header():
    resp = _fake_response({}, headers={"x-restli-id": "urn:li:share:12345"})
    with patch("agentos.social_linkedin.requests.post", return_value=resp) as mock_post:
        urn = social_linkedin.publish_text_post(
            "token", "urn:li:person:abc123", "hello world")
    assert urn == "urn:li:share:12345"
    mock_post.assert_called_once()


# --- agentos/memory.py: social_accounts storage ---

def test_save_and_get_social_token(tmp_path):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    assert mem.get_social_token("default", "instagram") is None

    mem.save_social_token("default", "instagram", "tok-1", "ig-1", 9999999999)
    token = mem.get_social_token("default", "instagram")
    assert token == {"access_token": "tok-1", "account_id": "ig-1",
                     "expires_at": 9999999999}

    # a different platform/scope must stay independent
    assert mem.get_social_token("default", "linkedin") is None
    assert mem.get_social_token("other-scope", "instagram") is None


def test_save_social_token_upserts_on_reconnect(tmp_path):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    mem.save_social_token("default", "instagram", "tok-1", "ig-1", 9999999999)
    mem.save_social_token("default", "instagram", "tok-2", "ig-2", 9999999999)
    token = mem.get_social_token("default", "instagram")
    assert token["access_token"] == "tok-2"
    assert token["account_id"] == "ig-2"


def test_get_social_token_returns_none_when_expired(tmp_path):
    import time

    mem = Memory(db_path=str(tmp_path / "t.db"))
    mem.save_social_token("default", "instagram", "tok-1", "ig-1", time.time() - 10)
    assert mem.get_social_token("default", "instagram") is None


def test_disconnect_social(tmp_path):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    mem.save_social_token("default", "instagram", "tok-1", "ig-1", 9999999999)
    mem.disconnect_social("default", "instagram")
    assert mem.get_social_token("default", "instagram") is None


# --- agentos/tools/social.py ---

def test_post_to_instagram_returns_connect_instructions_when_not_connected(monkeypatch):
    from agentos.tools import social

    monkeypatch.setattr(social.default_memory, "get_social_token", lambda *a: None)
    result = social.post_to_instagram("https://img.example/x.jpg", "caption")
    assert "not connected" in result.lower()
    assert "/auth/instagram/login" in result


def test_post_to_instagram_publishes_when_connected(monkeypatch):
    from agentos.tools import social

    monkeypatch.setattr(
        social.default_memory, "get_social_token",
        lambda scope, platform: {"access_token": "tok", "account_id": "ig-1"})
    with patch("agentos.social_instagram.publish_photo", return_value="media-1") as mock_pub:
        result = social.post_to_instagram("https://img.example/x.jpg", "caption")
    assert "media-1" in result
    mock_pub.assert_called_once_with("tok", "ig-1", "https://img.example/x.jpg", "caption")


def test_post_to_instagram_reports_failure_without_raising(monkeypatch):
    from agentos.tools import social

    monkeypatch.setattr(
        social.default_memory, "get_social_token",
        lambda scope, platform: {"access_token": "tok", "account_id": "ig-1"})
    with patch("agentos.social_instagram.publish_photo", side_effect=Exception("boom")):
        result = social.post_to_instagram("https://img.example/x.jpg", "caption")
    assert "failed" in result.lower()


def test_post_to_linkedin_returns_connect_instructions_when_not_connected(monkeypatch):
    from agentos.tools import social

    monkeypatch.setattr(social.default_memory, "get_social_token", lambda *a: None)
    result = social.post_to_linkedin("hello world")
    assert "not connected" in result.lower()
    assert "/auth/linkedin/login" in result


def test_post_to_linkedin_publishes_when_connected(monkeypatch):
    from agentos.tools import social

    monkeypatch.setattr(
        social.default_memory, "get_social_token",
        lambda scope, platform: {"access_token": "tok", "account_id": "urn:li:person:1"})
    with patch("agentos.social_linkedin.publish_text_post",
              return_value="urn:li:share:1") as mock_pub:
        result = social.post_to_linkedin("hello world")
    assert "urn:li:share:1" in result
    mock_pub.assert_called_once_with("tok", "urn:li:person:1", "hello world")
