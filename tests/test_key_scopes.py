"""Restricted (--no-execute) API keys: can call /run but never /execute."""

import json

from fastapi.testclient import TestClient

from agentos.memory import Memory
from tests.conftest import fake_response, make_plan_json


def test_restricted_key_flagged_correctly(tmp_path):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    _, full_key = mem.create_api_key("full-access")
    _, restricted_key = mem.create_api_key("restricted", can_execute=False)

    assert mem.verify_api_key(full_key)["can_execute"] is True
    assert mem.verify_api_key(restricted_key)["can_execute"] is False


def test_migration_defaults_pre_existing_keys_to_full_access(tmp_path):
    """Regression safeguard: a key created before can_execute existed must
    not silently lose execute access after upgrading."""
    import sqlite3

    db_path = str(tmp_path / "old.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE api_keys (id TEXT PRIMARY KEY, name TEXT, "
        "key_hash TEXT UNIQUE, created_at REAL, revoked_at REAL, last_used_at REAL)")
    conn.execute(
        "INSERT INTO api_keys VALUES ('k1', 'legacy', 'somehash', 0, NULL, NULL)")
    conn.commit()
    conn.close()

    mem = Memory(db_path=db_path)  # must not raise
    keys = mem.list_api_keys()
    assert keys[0]["can_execute"] is True


def test_restricted_key_can_run_but_not_execute(tmp_path, monkeypatch, patch_llm):
    import api

    mem = Memory(db_path=str(tmp_path / "auth.db"))
    _, restricted_key = mem.create_api_key("intern", can_execute=False)
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
                    headers={"Authorization": f"Bearer {restricted_key}"})
    assert r.status_code == 200  # /run still works for a restricted key

    r = client.post("/execute", json={
        "actions": [{"tool": "calculate", "args": {"expression": "1+1"}}]
    }, headers={"Authorization": f"Bearer {restricted_key}"})
    assert r.status_code == 403


def test_full_access_key_can_execute(tmp_path, monkeypatch):
    import api

    mem = Memory(db_path=str(tmp_path / "auth.db"))
    _, full_key = mem.create_api_key("owner")
    monkeypatch.setattr(api, "default_memory", mem)

    client = TestClient(api.app)
    r = client.post("/execute", json={
        "actions": [{"tool": "calculate", "args": {"expression": "1+1"}}]
    }, headers={"Authorization": f"Bearer {full_key}"})
    assert r.status_code == 200
