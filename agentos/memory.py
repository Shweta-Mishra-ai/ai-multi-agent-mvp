import contextlib
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid

DB_PATH = os.getenv("AGENTOS_DB", "agentos.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at REAL,
    title TEXT,
    api_key_id TEXT
);
CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    name TEXT,
    key_hash TEXT UNIQUE,
    created_at REAL,
    revoked_at REAL,
    last_used_at REAL
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
            self._migrate(conn)

    @staticmethod
    def _migrate(conn):
        # CREATE TABLE IF NOT EXISTS does not add columns to a table that
        # already exists (e.g. a live deployment's DB from before this
        # column existed) - without this, every INSERT into sessions would
        # fail on any database created before api_key_id was introduced.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        if "api_key_id" not in cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN api_key_id TEXT")

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

    def create_session(self, title, api_key_id=None):
        session_id = uuid.uuid4().hex[:12]
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?)",
                (session_id, time.time(), title[:80], api_key_id),
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

    def runs_in_last_minute(self, api_key_id=None):
        """Count runs in the last 60s, scoped to a single caller's identity
        (api_key_id) so each API key gets its own budget instead of every
        caller sharing one global bucket. api_key_id=None scopes to
        unauthenticated/local callers as a single shared bucket."""
        with self._conn() as conn:
            (count,) = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE created_at > ? AND "
                "api_key_id IS ?",
                (time.time() - 60, api_key_id),
            ).fetchone()
        return count

    # --- API key management (identity for per-caller rate limiting) ---

    def create_api_key(self, name):
        """Create a new API key. Returns (key_id, plaintext_key) - the
        plaintext is only ever available at creation time; only its hash
        is stored, so a leaked database backup does not leak usable keys."""
        key_id = uuid.uuid4().hex[:12]
        plaintext = "ak_" + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO api_keys VALUES (?, ?, ?, ?, NULL, NULL)",
                (key_id, name[:80], key_hash, time.time()),
            )
        return key_id, plaintext

    def verify_api_key(self, plaintext):
        """Return {"id", "name"} for a valid, non-revoked key, else None.
        Uses a constant-time comparison so response timing can't be used
        to brute-force a key one character at a time."""
        if not plaintext:
            return None
        key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, key_hash FROM api_keys WHERE revoked_at IS NULL"
            ).fetchall()
            for key_id, name, stored_hash in rows:
                if hmac.compare_digest(stored_hash, key_hash):
                    conn.execute(
                        "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                        (time.time(), key_id),
                    )
                    return {"id": key_id, "name": name}
        return None

    def revoke_api_key(self, key_id):
        with self._conn() as conn:
            changed = conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (time.time(), key_id),
            ).rowcount
        return changed > 0

    def list_api_keys(self):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, created_at, revoked_at, last_used_at "
                "FROM api_keys ORDER BY created_at DESC"
            ).fetchall()
        return [
            {"id": i, "name": n, "created_at": c, "revoked_at": r, "last_used_at": u}
            for i, n, c, r, u in rows
        ]

    def any_api_keys_exist(self):
        """Whether auth has ever been opted into - deliberately counts ALL
        keys, not just active ones. If this only counted active keys,
        revoking your only key (e.g. mid-rotation: revoke old, about to
        create new) would open a window where the API silently falls back
        to unauthenticated open mode - the opposite of what revoking a key
        implies. Once any key has ever been created, auth stays required;
        a revoked key still correctly fails verification."""
        with self._conn() as conn:
            (count,) = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()
        return count > 0

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
