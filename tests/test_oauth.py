"""Google OAuth login flow.

IMPORTANT: these tests verify AgentOS's own logic (state/CSRF handling,
token exchange, error handling, key issuance) using mocked HTTP
responses. They do NOT exercise a real round trip against Google's
servers - that requires a real Google Cloud OAuth Client ID/secret and a
public HTTPS callback URL, neither available in this environment. See
the README's OAuth section for what the deployment operator must set up
before this feature works for real.
"""

from unittest.mock import MagicMock, patch

import pytest

from agentos import oauth
from agentos.memory import Memory


@pytest.fixture(autouse=True)
def _oauth_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    oauth._pending_states.clear()
    yield
    oauth._pending_states.clear()


def test_is_configured_reflects_env_vars(monkeypatch):
    assert oauth.is_configured() is True
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert oauth.is_configured() is False


def test_build_authorize_url_contains_required_params():
    url = oauth.build_authorize_url("https://example.com/callback")
    assert url.startswith(oauth.GOOGLE_AUTH_URL)
    assert "client_id=test-client-id" in url
    assert "redirect_uri=" in url
    assert "state=" in url
    assert "scope=" in url


def test_state_is_single_use():
    url = oauth.build_authorize_url("https://example.com/callback")
    state = url.split("state=")[1].split("&")[0]

    assert oauth.consume_state(state) is True   # valid the first time
    assert oauth.consume_state(state) is False  # replay rejected
    assert oauth.consume_state("never-issued") is False


def test_expired_state_is_rejected(monkeypatch):
    import time as time_module

    real_now = time_module.time()
    url = oauth.build_authorize_url("https://example.com/callback")
    state = url.split("state=")[1].split("&")[0]

    monkeypatch.setattr(time_module, "time", lambda: real_now + 9999)
    assert oauth.consume_state(state) is False


def _fake_response(json_data, ok=True):
    r = MagicMock()
    r.json.return_value = json_data
    if ok:
        r.raise_for_status.return_value = None
    else:
        r.raise_for_status.side_effect = Exception("HTTP error")
    return r


def test_exchange_code_for_email_success():
    token_resp = _fake_response({"access_token": "fake-token"})
    userinfo_resp = _fake_response({"email": "alice@example.com",
                                    "email_verified": True})
    with patch("agentos.oauth.requests.post", return_value=token_resp), \
         patch("agentos.oauth.requests.get", return_value=userinfo_resp):
        email = oauth.exchange_code_for_email("fake-code", "https://x/callback")
    assert email == "alice@example.com"


def test_exchange_code_rejects_unverified_email():
    token_resp = _fake_response({"access_token": "fake-token"})
    userinfo_resp = _fake_response({"email": "alice@example.com",
                                    "email_verified": False})
    with patch("agentos.oauth.requests.post", return_value=token_resp), \
         patch("agentos.oauth.requests.get", return_value=userinfo_resp):
        with pytest.raises(ValueError):
            oauth.exchange_code_for_email("fake-code", "https://x/callback")


def test_exchange_code_propagates_http_errors():
    token_resp = _fake_response({}, ok=False)
    with patch("agentos.oauth.requests.post", return_value=token_resp):
        with pytest.raises(Exception):
            oauth.exchange_code_for_email("bad-code", "https://x/callback")


def test_upsert_google_key_revokes_previous_key_for_same_email(tmp_path):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    key_id_1, plaintext_1 = mem.upsert_google_key("alice@example.com")
    assert mem.verify_api_key(plaintext_1) is not None

    key_id_2, plaintext_2 = mem.upsert_google_key("alice@example.com")
    assert key_id_2 != key_id_1
    assert mem.verify_api_key(plaintext_1) is None   # old key now revoked
    assert mem.verify_api_key(plaintext_2) is not None


def test_upsert_google_key_different_emails_get_independent_keys(tmp_path):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    _, alice_key = mem.upsert_google_key("alice@example.com")
    _, bob_key = mem.upsert_google_key("bob@example.com")

    assert mem.verify_api_key(alice_key) is not None
    assert mem.verify_api_key(bob_key) is not None  # bob's login didn't touch alice's key
