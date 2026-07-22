import contextlib
import json
import os
import sqlite3
import time
import uuid

DB_PATH = os.getenv("AGENTOS_DB", "agentos.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at REAL,
    title TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    session_id TEXT,
    ts REAL,
    role TEXT,
    content TEXT
);
CREATE TABLE IF NOT EXISTS events (
    session_id TEXT,
    ts REAL,
    type TEXT,
    payload TEXT
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at REAL
);
CREATE TABLE IF NOT EXISTS metrics (
    session_id TEXT,
    ts REAL,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);
"""


class Memory:
    """Persistent memory: sessions, conversation history, events, run metrics
    and a key-value store. WAL mode + busy timeout make concurrent access
    (parallel steps, multiple frontends) safe."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextlib.contextmanager
    def _conn(self):
        # Using a bare sqlite3.Connection as `with conn:` only commits or
        # rolls back the transaction on exit - it does NOT close the
        # connection, so every call would leak one, relying solely on GC to
        # eventually close it. Wrap it so callers keep writing
        # `with self._conn() as conn:` (getting the same commit/rollback
        # behavior) while the connection is *also* guaranteed to close.
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # --- sessions & conversation ---

    def create_session(self, title):
        session_id = uuid.uuid4().hex[:12]
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?)",
                (session_id, time.time(), title[:80]),
            )
        return session_id

    def add_message(self, session_id, role, content):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO messages VALUES (?, ?, ?, ?)",
                (session_id, time.time(), role, content),
            )

    def get_messages(self, session_id, limit=10):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? "
                "ORDER BY ts DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def log_event(self, session_id, event):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?)",
                (session_id, time.time(), event.get("type", "?"),
                 json.dumps(event, default=str)),
            )

    def recent_sessions(self, limit=10):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, created_at, title FROM sessions "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"id": i, "created_at": t, "title": title} for i, t, title in rows]

    # --- metrics & rate limiting ---

    def save_metrics(self, session_id, payload):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO metrics VALUES (?, ?, ?)",
                (session_id, time.time(), json.dumps(payload, default=str)),
            )

    def recent_metrics(self, limit=100):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT payload FROM metrics ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def runs_in_last_minute(self):
        with self._conn() as conn:
            (count,) = conn.execute(
                "SELECT COUNT(*) FROM events WHERE type = 'plan' AND ts > ?",
                (time.time() - 60,),
            ).fetchone()
        return count

    # --- long-term key-value memory (used by agents via tools) ---

    def remember(self, key, value):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO kv VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?",
                (key, value, time.time(), value, time.time()),
            )

    def recall(self, query=""):
        with self._conn() as conn:
            if query:
                rows = conn.execute(
                    "SELECT key, value FROM kv WHERE key LIKE ? OR value LIKE ? "
                    "ORDER BY updated_at DESC LIMIT 20",
                    (f"%{query}%", f"%{query}%"),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key, value FROM kv ORDER BY updated_at DESC LIMIT 20"
                ).fetchall()
        return dict(rows)

    # --- retention ---

    def prune(self, older_than_days=30):
        """Delete events/messages/metrics older than N days, and sessions
        that no longer have any messages. Without this, a daily-use
        deployment's database grows unbounded forever (events are logged
        for every single run). The kv store is untouched - it's meant to
        persist indefinitely."""
        cutoff = time.time() - older_than_days * 86400
        with self._conn() as conn:
            events = conn.execute(
                "DELETE FROM events WHERE ts < ?", (cutoff,)).rowcount
            messages = conn.execute(
                "DELETE FROM messages WHERE ts < ?", (cutoff,)).rowcount
            metrics = conn.execute(
                "DELETE FROM metrics WHERE ts < ?", (cutoff,)).rowcount
            sessions = conn.execute(
                "DELETE FROM sessions WHERE created_at < ? AND id NOT IN "
                "(SELECT DISTINCT session_id FROM messages)", (cutoff,)).rowcount
        return {"events": events, "messages": messages,
                "metrics": metrics, "sessions": sessions}


default_memory = Memory()
