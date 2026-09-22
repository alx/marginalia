"""SQLite state: schema + persistence helpers (spec §4.6).

Single file, ``state.sqlite`` (kept out of git; lives on lamai270 at runtime).
Holds what was posted, reply cursors, which mentions were answered, and the
image-licence cache.

The posting/reply loops pass this object around as ``db``. Modules that want
raw SQL (e.g. ``images.check``) can use ``db.conn`` (a ``sqlite3.Connection``),
which already exposes ``execute``/``commit``.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
  agent TEXT, topic TEXT, path TEXT, title TEXT, zim_book TEXT, zim_date TEXT,
  note_id TEXT PRIMARY KEY, build_note_id TEXT, image_file TEXT, posted_at TEXT,
  text TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS posts_once ON posts(agent, path);
CREATE TABLE IF NOT EXISTS seen_articles (agent TEXT, path TEXT, PRIMARY KEY (agent, path));
CREATE TABLE IF NOT EXISTS cursors (agent TEXT, key TEXT, value TEXT, PRIMARY KEY (agent, key));
CREATE TABLE IF NOT EXISTS replies (incoming_note_id TEXT PRIMARY KEY, reply_note_id TEXT, agent TEXT);
CREATE TABLE IF NOT EXISTS image_licences (file TEXT PRIMARY KEY, ok INTEGER, credit TEXT);
CREATE TABLE IF NOT EXISTS pending_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  epic TEXT, hitl TEXT, staging_note TEXT,
  agent TEXT, topic TEXT, path TEXT, title TEXT,
  draft TEXT, concerns TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT, published_note TEXT
);
"""


class _LockedConn:
    """A sqlite3.Connection serialized for use across scheduler threads.

    ``run.py`` shares one State across APScheduler's worker threads; the
    underlying connection is opened with ``check_same_thread=False`` and
    every operation takes a lock so only one thread touches it at a time.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = threading.Lock()

    def execute(self, sql, *args, **kwargs):
        with self._lock:
            return self._conn.execute(sql, *args, **kwargs)

    def executescript(self, sql):
        with self._lock:
            return self._conn.executescript(sql)

    def commit(self):
        with self._lock:
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


class State:
    """Thin wrapper over the SQLite database with the named helpers the loops use."""

    def __init__(self, path: str = "state.sqlite"):
        raw = sqlite3.connect(path, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        self.conn = _LockedConn(raw)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()
        # one-off migration: CREATE TABLE IF NOT EXISTS never alters an old table
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(posts)")}
        if "text" not in cols:
            self.conn.execute("ALTER TABLE posts ADD COLUMN text TEXT")
            self.conn.commit()

    # -- posts -------------------------------------------------------------
    def save_post(self, agent, topic, path, note_id, build_note_id,
                  image_file, zim_book, zim_date, title=None, text=None) -> None:
        """Record a published note and the article/build it came from."""
        self.conn.execute(
            """INSERT OR REPLACE INTO posts
               (agent, topic, path, title, zim_book, zim_date,
                note_id, build_note_id, image_file, posted_at, text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (agent, topic, path, title, zim_book, zim_date,
             note_id, build_note_id, image_file,
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), text),
        )
        self.conn.commit()

    def recent_posts(self, n: int = 15) -> list[dict]:
        """The n most recent posts (any agent), newest first."""
        rows = self.conn.execute(
            """SELECT agent, title, text, posted_at FROM posts
               ORDER BY posted_at DESC, note_id DESC LIMIT ?""", (n,)).fetchall()
        return [dict(r) for r in rows]

    def post_by_note(self, note_id):
        """The post row for a Misskey note id, or None."""
        row = self.conn.execute(
            "SELECT * FROM posts WHERE note_id=?", (note_id,)).fetchone()
        return dict(row) if row else None

    def seen(self, agent, path) -> bool:
        """True if this agent already posted (or is queueing) this article."""
        row = self.conn.execute(
            "SELECT 1 FROM posts WHERE agent=? AND path=?", (agent, path)).fetchone()
        if row is not None:
            return True
        return self.conn.execute(
            "SELECT 1 FROM seen_articles WHERE agent=? AND path=?",
            (agent, path)).fetchone() is not None

    def mark_seen(self, agent, path) -> None:
        """Remember an article without a post row (e.g. escalated to HITL).

        Keeps the rotation from re-drafting an article that is sitting in
        the approval queue, without polluting the recent-posts digest.
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_articles (agent, path) VALUES (?,?)",
            (agent, path))
        self.conn.commit()

    # -- cursors -----------------------------------------------------------
    def get_cursor(self, agent, key, default=None):
        row = self.conn.execute(
            "SELECT value FROM cursors WHERE agent=? AND key=?", (agent, key)).fetchone()
        return row["value"] if row else default

    def set_cursor(self, agent, key, value) -> None:
        self.conn.execute(
            """INSERT INTO cursors (agent, key, value) VALUES (?,?,?)
               ON CONFLICT(agent, key) DO UPDATE SET value=excluded.value""",
            (agent, key, str(value)),
        )
        self.conn.commit()

    # convenience aliases used verbatim in spec §5/§6
    get = get_cursor
    set = set_cursor

    # -- replies -----------------------------------------------------------
    def replied(self, incoming_note_id) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM replies WHERE incoming_note_id=?", (incoming_note_id,)).fetchone()
        return row is not None

    def save_reply(self, incoming_note_id, reply_note_id, agent) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO replies
               (incoming_note_id, reply_note_id, agent) VALUES (?,?,?)""",
            (incoming_note_id, reply_note_id, agent),
        )
        self.conn.commit()

    # -- image licence cache ----------------------------------------------
    def licence(self, file_title):
        row = self.conn.execute(
            "SELECT ok, credit FROM image_licences WHERE file=?", (file_title,)).fetchone()
        if not row:
            return None
        return bool(row["ok"]), row["credit"]

    def set_licence(self, file_title, ok, credit) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO image_licences VALUES (?,?,?)",
            (file_title, int(ok), credit),
        )
        self.conn.commit()

    # -- pending (human-in-the-loop) posts ---------------------------------
    def save_pending(self, epic, hitl, staging_note, agent, topic, path, title,
                     draft, concerns) -> int:
        """Record an escalated draft; returns the row id."""
        cur = self.conn.execute(
            """INSERT INTO pending_posts
               (epic, hitl, staging_note, agent, topic, path, title, draft,
                concerns, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,'pending',?)""",
            (epic, hitl, staging_note, agent, topic, path, title, draft,
             json.dumps(concerns),
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        self.conn.commit()
        return cur.lastrowid

    def pending_posts(self) -> list[dict]:
        """All rows still awaiting a human decision."""
        rows = self.conn.execute(
            "SELECT * FROM pending_posts WHERE status='pending' ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def claim_pending(self, pid: int) -> bool:
        """Atomically flip a row pending -> approving; True if we got it."""
        cur = self.conn.execute(
            "UPDATE pending_posts SET status='approving' "
            "WHERE id=? AND status='pending'", (pid,))
        self.conn.commit()
        return cur.rowcount == 1

    def release_pending(self, pid: int) -> None:
        """Back off to pending (publish failed; retry next pass)."""
        self.conn.execute(
            "UPDATE pending_posts SET status='pending' WHERE id=?", (pid,))
        self.conn.commit()

    def resolve_pending(self, pid: int, note_id: str) -> None:
        """Mark published; the staging note id is kept for the audit trail."""
        self.conn.execute(
            "UPDATE pending_posts SET status='published', published_note=? WHERE id=?",
            (note_id, pid))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
