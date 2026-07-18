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
"""


class Memory:
    """Persistent memory: sessions, conversation history, events, key-value store."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.db_path)

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


default_memory = Memory()
