"""API-level tests for /auth/instagram/* and /auth/linkedin/*, using an
isolated Memory instance (same pattern as test_oauth_api.py) and mocked
social_instagram/social_linkedin modules - the real Meta/LinkedIn round
trip isn't testable here (see tests/test_social.py's module docstring)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from agentos.memory import Memory


def _isolated_memory(tmp_path):
    return Memory(db_path=str(tmp_path / "social_api.db"))


# --- Instagram ---

def test_instagram_login_404s_when_not_configured(monkeypatch):
    import api

    monkeypatch.delenv("META_APP_ID", raising=False)
    client = TestClient(api.app)
    r = client.get("/auth/instagram/login", follow_redirects=False)
    assert r.status_code == 404


def test_instagram_login_redirects_when_configured(monkeypatch):
    import api

    monkeypatch.setenv("META_APP_ID", "id")
    monkeypatch.setenv("META_APP_SECRET", "secret")
    monkeypatch.setattr(api.config, "META_REDIRECT_URI",
                        "https://example.com/auth/instagram/callback")
    client = TestClient(api.app)
    r = client.get("/auth/instagram/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "facebook.com" in r.headers["location"]


def test_instagram_callback_rejects_missing_state(monkeypatch):
    import api

    monkeypatch.setenv("META_APP_ID", "id")
    monkeypatch.setenv("META_APP_SECRET", "secret")
    client = TestClient(api.app)
    r = client.get("/auth/instagram/callback", params={"code": "abc"})
    assert r.status_code == 400


def test_instagram_callback_rejects_error_param():
    import api

    client = TestClient(api.app)
    r = client.get("/auth/instagram/callback", params={"error": "access_denied"})
    assert r.status_code == 400


def test_instagram_callback_rejects_replayed_or_unknown_state():
    import api

    client = TestClient(api.app)
    r = client.get("/auth/instagram/callback",
                   params={"code": "abc", "state": "never-issued"})
    assert r.status_code == 400


def test_instagram_full_connect_flow_saves_token(tmp_path, monkeypatch):
    import api

    monkeypatch.setenv("META_APP_ID", "id")
    monkeypatch.setenv("META_APP_SECRET", "secret")
    monkeypatch.setattr(api.config, "META_REDIRECT_URI",
                        "https://example.com/auth/instagram/callback")
    mem = _isolated_memory(tmp_path)
    monkeypatch.setattr(api, "default_memory", mem)
    client = TestClient(api.app)

    login_resp = client.get("/auth/instagram/login", follow_redirects=False)
    state = login_resp.headers["location"].split("state=")[1].split("&")[0]

    with patch("api.social_instagram.exchange_code_for_account",
              return_value=("tok", "ig-123", 9999999999)) as mock_exchange:
        cb_resp = client.get("/auth/instagram/callback",
                             params={"code": "fake-code", "state": state})
    assert cb_resp.status_code == 200
    mock_exchange.assert_called_once()
    assert mem.get_social_token("default", "instagram") == {
        "access_token": "tok", "account_id": "ig-123", "expires_at": 9999999999}


def test_instagram_callback_502s_on_exchange_failure(tmp_path, monkeypatch):
    import api

    monkeypatch.setenv("META_APP_ID", "id")
    monkeypatch.setenv("META_APP_SECRET", "secret")
    monkeypatch.setattr(api.config, "META_REDIRECT_URI",
                        "https://example.com/auth/instagram/callback")
    mem = _isolated_memory(tmp_path)
    monkeypatch.setattr(api, "default_memory", mem)
    client = TestClient(api.app)

    login_resp = client.get("/auth/instagram/login", follow_redirects=False)
    state = login_resp.headers["location"].split("state=")[1].split("&")[0]

    with patch("api.social_instagram.exchange_code_for_account",
              side_effect=Exception("boom")):
        cb_resp = client.get("/auth/instagram/callback",
                             params={"code": "fake-code", "state": state})
    assert cb_resp.status_code == 502


# --- LinkedIn ---

def test_linkedin_login_404s_when_not_configured(monkeypatch):
    import api

    monkeypatch.delenv("LINKEDIN_CLIENT_ID", raising=False)
    client = TestClient(api.app)
    r = client.get("/auth/linkedin/login", follow_redirects=False)
    assert r.status_code == 404


def test_linkedin_login_redirects_when_configured(monkeypatch):
    import api

    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "id")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "secret")
    monkeypatch.setattr(api.config, "LINKEDIN_REDIRECT_URI",
                        "https://example.com/auth/linkedin/callback")
    client = TestClient(api.app)
    r = client.get("/auth/linkedin/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "linkedin.com" in r.headers["location"]


def test_linkedin_callback_rejects_missing_state(monkeypatch):
    import api

    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "id")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "secret")
    client = TestClient(api.app)
    r = client.get("/auth/linkedin/callback", params={"code": "abc"})
    assert r.status_code == 400


def test_linkedin_callback_rejects_error_param():
    import api

    client = TestClient(api.app)
    r = client.get("/auth/linkedin/callback", params={"error": "access_denied"})
    assert r.status_code == 400


def test_linkedin_callback_rejects_replayed_or_unknown_state():
    import api

    client = TestClient(api.app)
    r = client.get("/auth/linkedin/callback",
                   params={"code": "abc", "state": "never-issued"})
    assert r.status_code == 400


def test_linkedin_full_connect_flow_saves_token(tmp_path, monkeypatch):
    import api

    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "id")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "secret")
    monkeypatch.setattr(api.config, "LINKEDIN_REDIRECT_URI",
                        "https://example.com/auth/linkedin/callback")
    mem = _isolated_memory(tmp_path)
    monkeypatch.setattr(api, "default_memory", mem)
    client = TestClient(api.app)

    login_resp = client.get("/auth/linkedin/login", follow_redirects=False)
    state = login_resp.headers["location"].split("state=")[1].split("&")[0]

    with patch("api.social_linkedin.exchange_code_for_member",
              return_value=("tok", "urn:li:person:1", 9999999999)) as mock_exchange:
        cb_resp = client.get("/auth/linkedin/callback",
                             params={"code": "fake-code", "state": state})
    assert cb_resp.status_code == 200
    mock_exchange.assert_called_once()
    assert mem.get_social_token("default", "linkedin") == {
        "access_token": "tok", "account_id": "urn:li:person:1", "expires_at": 9999999999}


def test_linkedin_callback_502s_on_exchange_failure(tmp_path, monkeypatch):
    import api

    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "id")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "secret")
    monkeypatch.setattr(api.config, "LINKEDIN_REDIRECT_URI",
                        "https://example.com/auth/linkedin/callback")
    mem = _isolated_memory(tmp_path)
    monkeypatch.setattr(api, "default_memory", mem)
    client = TestClient(api.app)

    login_resp = client.get("/auth/linkedin/login", follow_redirects=False)
    state = login_resp.headers["location"].split("state=")[1].split("&")[0]

    with patch("api.social_linkedin.exchange_code_for_member",
              side_effect=Exception("boom")):
        cb_resp = client.get("/auth/linkedin/callback",
                             params={"code": "fake-code", "state": state})
    assert cb_resp.status_code == 502
