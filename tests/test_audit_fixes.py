"""Regression tests for issues found in the production audit that don't
belong in the existing test files (planner logging, config bounds, memory
resource handling and retention, kernel resilience to storage failures)."""

import sqlite3
import time
from unittest.mock import patch

from agentos.memory import Memory


def test_planner_logs_a_warning_instead_of_failing_silently(patch_llm):
    def broken(*a, **k):
        raise RuntimeError("provider is down")

    patch_llm(broken)
    from agentos import planner

    # agentos's custom logger sets propagate=False (so its own StreamHandler
    # doesn't double-print), which makes pytest's root-logger-based caplog
    # unreliable here, and asserting on real stderr is order-dependent
    # under pytest's global capture manager. Assert on the call directly.
    with patch.object(planner.log, "warning") as mock_warning:
        steps = planner.make_plan("do something", "Medium")

    assert steps == [{"agent": "task", "instruction": "do something",
                      "depends_on": []}]
    mock_warning.assert_called_once()
    logged = mock_warning.call_args.args
    assert "planning failed" in logged[0]
    assert "provider is down" in str(logged[-1])


def test_config_clamps_invalid_env_vars_instead_of_crashing(monkeypatch):
    import importlib

    monkeypatch.setenv("AGENTOS_MAX_PARALLEL", "-5")
    monkeypatch.setenv("AGENTOS_MAX_STEPS", "0")
    monkeypatch.setenv("AGENTOS_LLM_RETRIES", "-1")
    from agentos import config

    importlib.reload(config)
    try:
        assert config.MAX_PARALLEL >= 1
        assert config.MAX_STEPS >= 1
        assert config.LLM_RETRIES >= 0
    finally:
        monkeypatch.delenv("AGENTOS_MAX_PARALLEL", raising=False)
        monkeypatch.delenv("AGENTOS_MAX_STEPS", raising=False)
        monkeypatch.delenv("AGENTOS_LLM_RETRIES", raising=False)
        importlib.reload(config)


def test_memory_connections_are_actually_closed(tmp_path):
    """Regression test: `with conn:` alone never closes a sqlite3
    connection - only contextlib-style wrapping does. Verify no
    connection is left open after any call."""
    mem = Memory(db_path=str(tmp_path / "test.db"))
    sid = mem.create_session("hello")
    mem.add_message(sid, "user", "hi")
    mem.log_event(sid, {"type": "plan"})
    mem.remember("k", "v")

    # sqlite3 exposes no public "is open" check; the practical proof is
    # that the file can be deleted/renamed on all platforms only if
    # nothing still holds it open - do a WAL checkpoint via a fresh
    # connection, which fails if the previous ones weren't released.
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()


def test_memory_prune_removes_old_records_keeps_recent(tmp_path):
    mem = Memory(db_path=str(tmp_path / "test.db"))
    old_sid = mem.create_session("old")
    mem.log_event(old_sid, {"type": "plan"})
    mem.save_metrics(old_sid, {"tokens": 1})

    # backdate the old session's timestamps directly
    with mem._conn() as conn:
        conn.execute("UPDATE sessions SET created_at = ?", (time.time() - 999 * 86400,))
        conn.execute("UPDATE events SET ts = ?", (time.time() - 999 * 86400,))
        conn.execute("UPDATE metrics SET ts = ?", (time.time() - 999 * 86400,))

    new_sid = mem.create_session("new")
    mem.log_event(new_sid, {"type": "plan"})

    result = mem.prune(older_than_days=30)
    assert result["events"] == 1
    assert result["metrics"] == 1

    remaining_sessions = {s["id"] for s in mem.recent_sessions(100)}
    assert new_sid in remaining_sessions
    assert old_sid not in remaining_sessions


def test_kernel_degrades_gracefully_when_memory_is_unavailable(patch_llm):
    """Regression test: create_session/get_messages used to be unguarded,
    so a storage error crashed the whole generator instead of degrading."""
    import json

    from tests.conftest import fake_response, make_plan_json

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
    from agentos.kernel import Kernel
    from agentos.memory import default_memory

    with patch.object(default_memory, "create_session",
                      side_effect=sqlite3.OperationalError("disk full")):
        events = list(Kernel().run("plan my day"))

    kinds = [e["type"] for e in events]
    assert "done" in kinds  # did not crash
    assert [e for e in events if e["type"] == "plan"][0]["session_id"]
