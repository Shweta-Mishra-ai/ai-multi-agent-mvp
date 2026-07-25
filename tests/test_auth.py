"""Tests for API key management, per-key rate limiting, migration safety,
and HTTP auth enforcement."""

import sqlite3

from agentos.memory import Memory


def test_create_verify_and_revoke_key(tmp_path):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    key_id, plaintext = mem.create_api_key("alice")

    assert plaintext.startswith("ak_")
    identity = mem.verify_api_key(plaintext)
    assert identity == {"id": key_id, "name": "alice", "can_execute": True}

    assert mem.verify_api_key("ak_totally-wrong-key") is None
    assert mem.verify_api_key("") is None
    assert mem.verify_api_key(None) is None

    assert mem.revoke_api_key(key_id) is True
    assert mem.verify_api_key(plaintext) is None       # revoked key stops working
    assert mem.revoke_api_key(key_id) is False          # already revoked


def test_plaintext_key_is_never_stored(tmp_path):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    _, plaintext = mem.create_api_key("bob")
    with mem._conn() as conn:
        row = conn.execute("SELECT key_hash FROM api_keys").fetchone()
    assert plaintext not in row[0]
    assert row[0] != plaintext


def test_list_api_keys_shows_metadata_not_secrets(tmp_path):
    mem = Memory(db_path=str(tmp_path / "t.db"))
    mem.create_api_key("carol")
    keys = mem.list_api_keys()
    assert len(keys) == 1
    assert keys[0]["name"] == "carol"
    assert "key_hash" not in keys[0]
    assert "plaintext" not in keys[0]


def test_any_api_keys_exist_stays_true_after_revoking_the_only_key(tmp_path):
    """Regression test: if this flipped back to False whenever no ACTIVE
    key remained, revoking your only key (e.g. mid-rotation) would open a
    window where the API silently falls back to unauthenticated open mode
    - the opposite of what revoking a key should do. Once auth has ever
    been opted into, it must stay required."""
    mem = Memory(db_path=str(tmp_path / "t.db"))
    assert mem.any_api_keys_exist() is False
    key_id, _ = mem.create_api_key("dave")
    assert mem.any_api_keys_exist() is True
    mem.revoke_api_key(key_id)
    assert mem.any_api_keys_exist() is True


def test_per_key_rate_limit_isolation(tmp_path):
    """Core fix: two different callers must not share a rate-limit budget."""
    mem = Memory(db_path=str(tmp_path / "t.db"))
    key_a, _ = mem.create_api_key("a")
    key_b, _ = mem.create_api_key("b")

    for _ in range(5):
        mem.create_session("busy", api_key_id=key_a)

    assert mem.runs_in_last_minute(key_a) == 5
    assert mem.runs_in_last_minute(key_b) == 0          # unaffected by key_a's load
    assert mem.runs_in_last_minute(None) == 0            # unaffected too


def test_migration_adds_column_to_pre_existing_database(tmp_path):
    """Regression test: a database created before api_key_id existed (e.g.
    an already-deployed instance) must not break on upgrade - CREATE TABLE
    IF NOT EXISTS alone would silently skip adding the new column."""
    db_path = str(tmp_path / "old.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, created_at REAL, title TEXT)")
    conn.execute("INSERT INTO sessions VALUES ('abc', 123.0, 'old session')")
    conn.commit()
    conn.close()

    mem = Memory(db_path=db_path)  # must not raise
    # new column must be usable now
    sid = mem.create_session("new session", api_key_id="k1")
    assert mem.runs_in_last_minute("k1") == 1
    assert any(s["id"] == "abc" for s in mem.recent_sessions(10))  # old data intact


def test_check_rate_limit_scopes_by_api_key_id(tmp_path):
    from agentos.security import check_rate_limit

    mem = Memory(db_path=str(tmp_path / "t.db"))
    key_a, _ = mem.create_api_key("a")
    for _ in range(3):
        mem.create_session("x", api_key_id=key_a)

    import agentos.config as config
    old_limit = config.RATE_LIMIT_PER_MIN
    config.RATE_LIMIT_PER_MIN = 3
    try:
        assert check_rate_limit(mem, key_a) is False    # key_a is at budget
        assert check_rate_limit(mem, "other-key") is True
        assert check_rate_limit(mem, None) is True
    finally:
        config.RATE_LIMIT_PER_MIN = old_limit
