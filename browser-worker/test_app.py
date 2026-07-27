"""Tests for the browser worker's auth and SSRF guards - the parts that
don't require actually launching a browser. The render path itself
(real Chromium navigation) is verified manually, not in this suite,
since it needs a real network + browser rather than something to mock."""

import os

os.environ["WORKER_API_KEY"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_render_requires_auth():
    r = client.post("/render", json={"url": "https://example.com"})
    assert r.status_code == 401


def test_render_rejects_wrong_token():
    r = client.post(
        "/render", json={"url": "https://example.com"},
        headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_render_blocks_unsafe_url():
    r = client.post(
        "/render", json={"url": "http://127.0.0.1/secret"},
        headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 422
    assert "not a safe" in r.json()["detail"]


def test_render_rejects_missing_url():
    r = client.post(
        "/render", json={},
        headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 422


def test_render_requires_worker_key_configured(monkeypatch):
    monkeypatch.delenv("WORKER_API_KEY", raising=False)
    r = client.post(
        "/render", json={"url": "https://example.com"},
        headers={"Authorization": "Bearer anything"})
    assert r.status_code == 500
