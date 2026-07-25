"""API-level auth enforcement tests. Uses an isolated Memory instance
patched onto api.default_memory so these tests don't taint the shared
conftest database used by every other API test (which assumes open mode)."""

import json

from fastapi.testclient import TestClient

from agentos.memory import Memory
from tests.conftest import fake_response, make_plan_json


def _isolated_memory(tmp_path):
    return Memory(db_path=str(tmp_path / "auth_test.db"))


def test_open_mode_when_no_keys_exist(tmp_path, monkeypatch):
    import api

    monkeypatch.setattr(api, "default_memory", _isolated_memory(tmp_path))
    client = TestClient(api.app)

    r = client.post("/run", json={"request": "hi"})
    assert r.status_code == 200  # no Authorization header needed


def test_run_requires_key_once_one_exists(tmp_path, monkeypatch):
    import api

    mem = _isolated_memory(tmp_path)
    mem.create_api_key("someone")
    monkeypatch.setattr(api, "default_memory", mem)
    client = TestClient(api.app)

    r = client.post("/run", json={"request": "hi"})
    assert r.status_code == 401

    r = client.post("/run", json={"request": "hi"},
                    headers={"Authorization": "Bearer not-a-real-key"})
    assert r.status_code == 401


def test_run_succeeds_with_valid_key(tmp_path, monkeypatch, patch_llm):
    import api

    mem = _isolated_memory(tmp_path)
    _, plaintext = mem.create_api_key("someone")
    monkeypatch.setattr(api, "default_memory", mem)

    plan = make_plan_json(
        [{"agent": "task", "instruction": "plan it", "depends_on": []}])

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            if response_format["json_schema"]["name"] == "plan":
                return fake_response(content=plan)
            return fake_response(content=json.dumps(
                {"satisfied": True, "feedback": ""}))
        return fake_response(content="OK")

    patch_llm(fake_chat)
    client = TestClient(api.app)
    r = client.post("/run", json={"request": "plan my day"},
                    headers={"Authorization": f"Bearer {plaintext}"})
    assert r.status_code == 200
    events = [json.loads(line) for line in r.text.strip().splitlines()]
    assert [e for e in events if e["type"] == "done"]


def test_revoked_key_is_rejected(tmp_path, monkeypatch):
    import api

    mem = _isolated_memory(tmp_path)
    key_id, plaintext = mem.create_api_key("someone")
    mem.revoke_api_key(key_id)
    monkeypatch.setattr(api, "default_memory", mem)

    client = TestClient(api.app)
    r = client.post("/run", json={"request": "hi"},
                    headers={"Authorization": f"Bearer {plaintext}"})
    assert r.status_code == 401


def test_execute_also_requires_key_once_one_exists(tmp_path, monkeypatch):
    import api

    mem = _isolated_memory(tmp_path)
    mem.create_api_key("someone")
    monkeypatch.setattr(api, "default_memory", mem)

    client = TestClient(api.app)
    r = client.post("/execute", json={
        "actions": [{"tool": "calculate", "args": {"expression": "1+1"}}]})
    assert r.status_code == 401


def test_health_and_agents_never_require_auth(tmp_path, monkeypatch):
    import api

    mem = _isolated_memory(tmp_path)
    mem.create_api_key("someone")
    monkeypatch.setattr(api, "default_memory", mem)

    client = TestClient(api.app)
    assert client.get("/health").status_code == 200
    assert client.get("/agents").status_code == 200


def test_two_keys_get_independent_rate_limits(tmp_path, monkeypatch, patch_llm):
    """End-to-end version of the per-key isolation fix: key A hitting its
    budget must not affect key B's ability to call /run."""
    import agentos.config as config
    import api

    mem = _isolated_memory(tmp_path)
    _, key_a = mem.create_api_key("a")
    _, key_b = mem.create_api_key("b")
    monkeypatch.setattr(api, "default_memory", mem)
    monkeypatch.setattr(config, "RATE_LIMIT_PER_MIN", 1)

    plan = make_plan_json(
        [{"agent": "task", "instruction": "plan it", "depends_on": []}])

    def fake_chat(messages, tools=None, response_format=None):
        if response_format is not None:
            if response_format["json_schema"]["name"] == "plan":
                return fake_response(content=plan)
            return fake_response(content=json.dumps(
                {"satisfied": True, "feedback": ""}))
        return fake_response(content="OK")

    patch_llm(fake_chat)
    client = TestClient(api.app)

    r1 = client.post("/run", json={"request": "first"},
                     headers={"Authorization": f"Bearer {key_a}"})
    assert r1.status_code == 200

    # key A is now at its budget of 1/min
    r2 = client.post("/run", json={"request": "second"},
                     headers={"Authorization": f"Bearer {key_a}"})
    events = [json.loads(line) for line in r2.text.strip().splitlines()]
    assert events[0]["type"] == "error"
    assert "Rate limit" in events[0]["message"]

    # key B is unaffected - its own independent budget
    r3 = client.post("/run", json={"request": "third"},
                     headers={"Authorization": f"Bearer {key_b}"})
    events3 = [json.loads(line) for line in r3.text.strip().splitlines()]
    assert events3[0]["type"] == "plan"
