import contextlib
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid

from agentos.embeddings import cosine_similarity, embed

DB_PATH = os.getenv("AGENTOS_DB", "agentos.db")

_MISSING = object()  # sentinel: "no session with this id", distinct from
                     # "session exists and is unowned/open-mode" (None)

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
    last_used_at REAL,
    can_execute INTEGER DEFAULT 1,
    google_email TEXT
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
    updated_at REAL,
    embedding TEXT
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

        cols = {row[1] for row in conn.execute("PRAGMA table_info(api_keys)")}
        if "can_execute" not in cols:
            # Default existing keys to full access (1) - a pre-existing key
            # must not silently lose the ability to execute approved
            # actions just because this column was introduced later.
            conn.execute(
                "ALTER TABLE api_keys ADD COLUMN can_execute INTEGER DEFAULT 1")
        if "google_email" not in cols:
            conn.execute("ALTER TABLE api_keys ADD COLUMN google_email TEXT")

        cols = {row[1] for row in conn.execute("PRAGMA table_info(kv)")}
        if "embedding" not in cols:
            conn.execute("ALTER TABLE kv ADD COLUMN embedding TEXT")

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

    def get_session_owner(self, session_id):
        """The api_key_id a session was created under (None for
        open-mode/anonymous), or _MISSING if the session doesn't exist -
        distinct from None so a caller can't "resume" a nonexistent id
        into someone else's future session of the same identity."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT api_key_id FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return row[0] if row else _MISSING

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

    def create_api_key(self, name, can_execute=True):
        """Create a new API key. Returns (key_id, plaintext_key) - the
        plaintext is only ever available at creation time; only its hash
        is stored, so a leaked database backup does not leak usable keys.

        can_execute=False creates a restricted key that can call /run
        (plan, research, draft, preview irreversible actions) but is
        always refused at /execute - useful for giving a key to a caller
        who should never be able to actually send an email, for example,
        even if they can request one be drafted."""
        key_id = uuid.uuid4().hex[:12]
        plaintext = "ak_" + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO api_keys "
                "(id, name, key_hash, created_at, can_execute) "
                "VALUES (?, ?, ?, ?, ?)",
                (key_id, name[:80], key_hash, time.time(), int(can_execute)),
            )
        return key_id, plaintext

    def verify_api_key(self, plaintext):
        """Return {"id", "name", "can_execute"} for a valid, non-revoked
        key, else None. Uses a constant-time comparison so response timing
        can't be used to brute-force a key one character at a time."""
        if not plaintext:
            return None
        key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, key_hash, can_execute FROM api_keys "
                "WHERE revoked_at IS NULL"
            ).fetchall()
            for key_id, name, stored_hash, can_execute in rows:
                if hmac.compare_digest(stored_hash, key_hash):
                    conn.execute(
                        "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                        (time.time(), key_id),
                    )
                    return {"id": key_id, "name": name,
                            "can_execute": bool(can_execute)}
        return None

    def revoke_api_key(self, key_id):
        with self._conn() as conn:
            changed = conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (time.time(), key_id),
            ).rowcount
        return changed > 0

    def upsert_google_key(self, email):
        """Issue a fresh API key for a Google account signing in, revoking
        any previous key tied to the same email first. A login always
        yields exactly one currently-valid key per account - we cannot
        show the same plaintext twice, since (like every other key) only
        its hash is ever stored, so "reuse the old key" isn't possible;
        the previous one is simply retired in favor of a new one."""
        with self._conn() as conn:
            old_ids = [row[0] for row in conn.execute(
                "SELECT id FROM api_keys WHERE google_email = ? AND revoked_at IS NULL",
                (email,))]
            for old_id in old_ids:
                conn.execute(
                    "UPDATE api_keys SET revoked_at = ? WHERE id = ?",
                    (time.time(), old_id))

        key_id, plaintext = self.create_api_key(email, can_execute=True)
        with self._conn() as conn:
            conn.execute(
                "UPDATE api_keys SET google_email = ? WHERE id = ?", (email, key_id))
        return key_id, plaintext

    def list_api_keys(self):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name, created_at, revoked_at, last_used_at, can_execute "
                "FROM api_keys ORDER BY created_at DESC"
            ).fetchall()
        return [
            {"id": i, "name": n, "created_at": c, "revoked_at": r,
             "last_used_at": u, "can_execute": bool(x)}
            for i, n, c, r, u, x in rows
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

    def remember(self, key, value, scope="default"):
        """Scoped per caller so different callers' facts never collide.
        Stored as a "scope::key" composite rather than changing the kv
        table's schema (avoids a risky primary-key migration); the prefix
        is transparent to callers - remember/recall always deal in the
        plain key the caller gave.

        Also best-effort computes and stores a semantic embedding of the
        value, so recall() can later find it even without any literal
        substring overlap with the search query. A no-op when the
        provider doesn't support embeddings (e.g. Groq) - the fact is
        still saved and still findable via substring search."""
        embedding = embed(value)
        embedding_json = json.dumps(embedding) if embedding else None
        with self._conn() as conn:
            scoped_key = f"{scope}::{key}"
            conn.execute(
                "INSERT INTO kv (key, value, updated_at, embedding) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                "value = ?, updated_at = ?, embedding = ?",
                (scoped_key, value, time.time(), embedding_json,
                 value, time.time(), embedding_json),
            )

    def recall(self, query="", scope="default"):
        prefix = f"{scope}::"
        with self._conn() as conn:
            if query:
                rows = conn.execute(
                    "SELECT key, value, embedding FROM kv WHERE key LIKE ? AND "
                    "(key LIKE ? OR value LIKE ?) ORDER BY updated_at DESC LIMIT 20",
                    (f"{prefix}%", f"%{query}%", f"%{query}%"),
                ).fetchall()
                substring_keys = {k for k, _, _ in rows}

                # Semantic match: surfaces a fact even with no literal
                # substring overlap (e.g. query "leadership style" finding
                # a fact worded "prefers collaborative decisions"). A
                # no-op - same rows as above - if this provider doesn't
                # support embeddings.
                query_embedding = embed(query)
                if query_embedding:
                    embedded_rows = conn.execute(
                        "SELECT key, value, embedding FROM kv WHERE key LIKE ? "
                        "AND embedding IS NOT NULL", (f"{prefix}%",),
                    ).fetchall()
                    scored = sorted((
                        (cosine_similarity(query_embedding, json.loads(e)), k, v)
                        for k, v, e in embedded_rows
                    ), key=lambda t: -t[0])
                    for score, k, v in scored[:20]:
                        if score >= 0.3 and k not in substring_keys:
                            rows.append((k, v, None))
            else:
                rows = conn.execute(
                    "SELECT key, value, embedding FROM kv WHERE key LIKE ? "
                    "ORDER BY updated_at DESC LIMIT 20",
                    (f"{prefix}%",),
                ).fetchall()
            result = {k[len(prefix):]: v for k, v, _ in rows}

            # Backward compatibility: facts saved before per-caller scoping
            # existed have no "scope::" prefix at all. Surface them for the
            # default/open-mode scope only, so an existing single-user
            # deployment doesn't lose access to what it already remembered.
            if scope == "default":
                legacy_filter = "key NOT LIKE '%::%'"
                if query:
                    legacy = conn.execute(
                        f"SELECT key, value FROM kv WHERE {legacy_filter} AND "
                        "(key LIKE ? OR value LIKE ?) ORDER BY updated_at DESC LIMIT 20",
                        (f"%{query}%", f"%{query}%"),
                    ).fetchall()
                else:
                    legacy = conn.execute(
                        f"SELECT key, value FROM kv WHERE {legacy_filter} "
                        "ORDER BY updated_at DESC LIMIT 20"
                    ).fetchall()
                for k, v in legacy:
                    result.setdefault(k, v)
        return result

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
