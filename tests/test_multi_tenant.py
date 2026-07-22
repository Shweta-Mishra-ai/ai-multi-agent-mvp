"""Multi-tenant isolation: two different callers must never see each
other's workspace files, long-term memory, or conversation history."""

import json

from tests.conftest import fake_response, fake_tool_call, make_plan_json

from agentos import identity
from agentos.memory import Memory
from agentos.tools import TOOLS


def test_workspace_files_are_scoped_per_caller(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTOS_WORKSPACE", str(tmp_path / "workspace"))

    identity.set_caller("key-a")
    TOOLS["write_file"]["fn"](name="report.md", content="alice's data")

    identity.set_caller("key-b")
    assert "(workspace is empty)" == TOOLS["list_files"]["fn"]()
    try:
        TOOLS["read_file"]["fn"](name="report.md")
        assert False, "key-b must not see key-a's file"
    except FileNotFoundError:
        pass

    identity.set_caller("key-a")
    assert TOOLS["read_file"]["fn"](name="report.md") == "alice's data"
    identity.set_caller(None)  # reset for other tests


def test_long_term_memory_is_scoped_per_caller(tmp_path, monkeypatch):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    mem.remember("favorite_color", "blue", scope="key-a")
    mem.remember("favorite_color", "red", scope="key-b")

    assert mem.recall(scope="key-a") == {"favorite_color": "blue"}
    assert mem.recall(scope="key-b") == {"favorite_color": "red"}
    assert mem.recall(scope="default") == {}  # unrelated to either


def test_legacy_unscoped_memory_stays_visible_in_default_scope(tmp_path):
    """Regression safeguard: facts saved before per-caller scoping existed
    must not become invisible after upgrading - only for the default/
    open-mode scope, since that's what a pre-existing single-user
    deployment was implicitly using."""
    mem = Memory(db_path=str(tmp_path / "t.db"))
    with mem._conn() as conn:
        conn.execute(
            "INSERT INTO kv VALUES ('old_fact', 'still here', 0)")

    assert mem.recall(scope="default") == {"old_fact": "still here"}
    assert mem.recall(scope="key-a") == {}  # legacy facts are not "key-a"'s


def test_kernel_rejects_session_id_owned_by_a_different_caller(patch_llm, tmp_path):
    from agentos.kernel import Kernel

    mem = Memory(db_path=str(tmp_path / "t.db"))
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
    kernel = Kernel(memory=mem)

    # key-a creates a session
    events_a = list(kernel.run("first request", api_key_id="key-a"))
    session_id = [e for e in events_a if e["type"] == "plan"][0]["session_id"]

    # key-b tries to resume key-a's session id
    events_b = list(kernel.run("second request", session_id=session_id,
                               api_key_id="key-b"))
    plan_event = [e for e in events_b if e["type"] == "plan"][0]
    assert plan_event["session_id"] != session_id  # got a fresh session instead

    # key-a can still resume their own session normally
    events_a2 = list(kernel.run("third request", session_id=session_id,
                                api_key_id="key-a"))
    plan_event_a2 = [e for e in events_a2 if e["type"] == "plan"][0]
    assert plan_event_a2["session_id"] == session_id


def test_execute_approved_scopes_tool_calls_to_the_approving_caller(tmp_path, monkeypatch):
    """The /execute path bypasses run() entirely by design (no re-planning),
    so it must set caller identity itself - otherwise an approved
    write_file would land in the wrong caller's workspace."""
    monkeypatch.setenv("AGENTOS_WORKSPACE", str(tmp_path / "workspace"))
    from agentos.kernel import Kernel

    identity.set_caller("stale-caller-from-a-previous-run")
    try:
        Kernel().execute_approved(
            [{"tool": "write_file", "args": {"name": "x.txt", "content": "hi"}}],
            api_key_id="key-a",
        )
        identity.set_caller("key-a")
        assert "x.txt" in TOOLS["list_files"]["fn"]()
        identity.set_caller("key-b")
        assert "(workspace is empty)" == TOOLS["list_files"]["fn"]()
    finally:
        identity.set_caller(None)
