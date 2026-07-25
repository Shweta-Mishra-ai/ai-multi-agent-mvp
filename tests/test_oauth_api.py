"""API-level tests for /auth/google/login and /auth/google/callback,
using an isolated Memory instance (same pattern as test_api_auth.py) and
a mocked oauth module - the real Google round trip isn't testable here
(see tests/test_oauth.py's module docstring for why)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from agentos.memory import Memory


def _isolated_memory(tmp_path):
    return Memory(db_path=str(tmp_path / "oauth_api.db"))


def test_login_404s_when_not_configured(monkeypatch):
    import api

    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    client = TestClient(api.app)
    r = client.get("/auth/google/login", follow_redirects=False)
    assert r.status_code == 404


def test_login_redirects_when_configured(monkeypatch):
    import api

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(api.config, "GOOGLE_REDIRECT_URI",
                        "https://example.com/auth/google/callback")
    client = TestClient(api.app)
    r = client.get("/auth/google/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "accounts.google.com" in r.headers["location"]


def test_callback_rejects_missing_state(monkeypatch):
    import api

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    client = TestClient(api.app)
    r = client.get("/auth/google/callback", params={"code": "abc"})
    assert r.status_code == 400


def test_callback_rejects_error_param(monkeypatch):
    import api

    client = TestClient(api.app)
    r = client.get("/auth/google/callback", params={"error": "access_denied"})
    assert r.status_code == 400


def test_callback_rejects_replayed_or_unknown_state(monkeypatch):
    import api

    client = TestClient(api.app)
    r = client.get("/auth/google/callback",
                   params={"code": "abc", "state": "never-issued"})
    assert r.status_code == 400


def test_full_login_flow_issues_a_working_api_key(tmp_path, monkeypatch):
    import api

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(api.config, "GOOGLE_REDIRECT_URI",
                        "https://example.com/auth/google/callback")
    mem = _isolated_memory(tmp_path)
    monkeypatch.setattr(api, "default_memory", mem)

    client = TestClient(api.app)

    # Step 1: start login, capture the real state AgentOS generated.
    login_resp = client.get("/auth/google/login", follow_redirects=False)
    location = login_resp.headers["location"]
    state = location.split("state=")[1].split("&")[0]

    # Step 2: simulate Google's callback with a mocked token exchange.
    with patch("api.oauth.exchange_code_for_email",
              return_value="alice@example.com") as mock_exchange:
        cb_resp = client.get("/auth/google/callback",
                             params={"code": "fake-code", "state": state})
    assert cb_resp.status_code == 200
    assert "alice@example.com" in cb_resp.text
    mock_exchange.assert_called_once()

    # Step 3: the issued key must actually work against /run.
    import re

    issued_key = re.search(r"<pre[^>]*>(ak_[^<]+)</pre>", cb_resp.text).group(1)
    r = client.post("/run", json={"request": "hi"},
                    headers={"Authorization": f"Bearer {issued_key}"})
    assert r.status_code == 200


def test_login_twice_revokes_first_issued_key(tmp_path, monkeypatch):
    import api

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(api.config, "GOOGLE_REDIRECT_URI",
                        "https://example.com/auth/google/callback")
    mem = _isolated_memory(tmp_path)
    monkeypatch.setattr(api, "default_memory", mem)
    client = TestClient(api.app)

    def do_login():
        location = client.get("/auth/google/login",
                              follow_redirects=False).headers["location"]
        state = location.split("state=")[1].split("&")[0]
        with patch("api.oauth.exchange_code_for_email",
                  return_value="alice@example.com"):
            resp = client.get("/auth/google/callback",
                              params={"code": "fake-code", "state": state})
        import re
        return re.search(r"<pre[^>]*>(ak_[^<]+)</pre>", resp.text).group(1)

    first_key = do_login()
    second_key = do_login()

    r1 = client.post("/run", json={"request": "hi"},
                     headers={"Authorization": f"Bearer {first_key}"})
    assert r1.status_code == 401  # first key revoked by the second login

    r2 = client.post("/run", json={"request": "hi"},
                     headers={"Authorization": f"Bearer {second_key}"})
    assert r2.status_code == 200
