"""Tests for marginalia.state (spec §4.6). Run: .venv/bin/python -m pytest tests/ -q"""
import os
import tempfile

from marginalia.state import State


def _db():
    p = tempfile.mktemp(suffix=".sqlite")
    return State(p), p


def test_posts():
    db, p = _db()
    try:
        db.save_post("atlas", "geography", "Deserts", "note-1", "build-1",
                     "Desert.jpg", "wikipedia_en_geography", "2026-07", title="Deserts")
        assert db.seen("atlas", "Deserts")
        assert not db.seen("quark", "Deserts")
        row = db.post_by_note("note-1")
        assert row["topic"] == "geography" and row["zim_book"] == "wikipedia_en_geography"
        assert db.post_by_note("nope") is None
    finally:
        db.close(); os.remove(p)


def test_cursors():
    db, p = _db()
    try:
        assert db.get_cursor("atlas", "mention_cursor") is None
        db.set_cursor("atlas", "mention_cursor", "n123")
        assert db.get_cursor("atlas", "mention_cursor") == "n123"
        assert db.get_cursor("atlas", "missing", "dflt") == "dflt"
    finally:
        db.close(); os.remove(p)


def test_replies():
    db, p = _db()
    try:
        assert not db.replied("in-1")
        db.save_reply("in-1", "out-1", "atlas")
        assert db.replied("in-1")
    finally:
        db.close(); os.remove(p)


def test_licence_cache():
    db, p = _db()
    try:
        assert db.licence("Poster.jpg") is None
        db.set_licence("Poster.jpg", True, "Poster.jpg, anon, CC BY-SA")
        assert db.licence("Poster.jpg") == (True, "Poster.jpg, anon, CC BY-SA")
    finally:
        db.close(); os.remove(p)


def test_cross_thread_access():
    """run.py shares one State across APScheduler worker threads; the
    connection must be usable from a thread other than the one that made it."""
    import threading
    db, p = _db()
    errors = []
    try:
        def worker():
            try:
                db.save_post("atlas", "geography", "Deserts", "n1", "b1",
                             None, "book", "2026-07", title="Deserts")
                assert db.seen("atlas", "Deserts")
                db.set_cursor("atlas", "mention_cursor", "n1")
                assert db.get_cursor("atlas", "mention_cursor") == "n1"
            except Exception as e:
                errors.append(e)
        t = threading.Thread(target=worker)
        t.start(); t.join()
        assert not errors, errors
        # main thread can still use it afterwards
        assert db.seen("atlas", "Deserts")
    finally:
        db.close(); os.remove(p)


# -- pending (HITL) posts ----------------------------------------------------
def test_pending_lifecycle():
    db, p = _db()
    try:
        pid = db.save_pending("ep1", "hitl1", "st1", "atlas", "geography",
                              "Mars", "Mars", "draft text", ["c1"])
        rows = db.pending_posts()
        assert len(rows) == 1 and rows[0]["status"] == "pending"
        assert rows[0]["draft"] == "draft text" and rows[0]["hitl"] == "hitl1"

        assert db.claim_pending(pid) is True
        assert db.claim_pending(pid) is False        # second claim loses
        assert db.pending_posts() == []              # approving rows are hidden
        db.release_pending(pid)
        assert len(db.pending_posts()) == 1          # back to pending

        assert db.claim_pending(pid) is True
        db.resolve_pending(pid, "note-9")
        assert db.pending_posts() == []
    finally:
        db.close(); os.remove(p)


def test_recent_posts_and_post_text():
    db, p = _db()
    try:
        db.save_post("atlas", "geography", "Mars", "n1", None, None,
                     "book", "2026-07", title="Mars", text="full text one")
        db.save_post("quark", "physics", "Atom", "n2", None, None,
                     "book", "2026-07", title="Atom", text="full text two")
        rows = db.recent_posts(5)
        assert [r["title"] for r in rows] == ["Atom", "Mars"]   # newest first
        assert rows[0]["text"] == "full text two"
    finally:
        db.close(); os.remove(p)


def test_old_schema_migrates_posts_text():
    """A state file created before the `text` column still opens cleanly."""
    import sqlite3
    p = tempfile.mktemp(suffix=".sqlite")
    conn = sqlite3.connect(p)
    conn.execute(
        """CREATE TABLE posts (
           agent TEXT, topic TEXT, path TEXT, title TEXT, zim_book TEXT,
           zim_date TEXT, note_id TEXT PRIMARY KEY, build_note_id TEXT,
           image_file TEXT, posted_at TEXT)""")
    conn.commit(); conn.close()
    try:
        db = State(p)
        db.save_post("atlas", "geography", "Mars", "n1", None, None,
                     "book", "2026-07", title="Mars", text="hello")
        assert db.post_by_note("n1")["text"] == "hello"
        db.close()
    finally:
        os.remove(p)


def test_mark_seen_without_post_row():
    db, p = _db()
    try:
        assert not db.seen("atlas", "Mars")
        db.mark_seen("atlas", "Mars")
        assert db.seen("atlas", "Mars")
        assert not db.seen("quark", "Mars")
        # a real post still counts and does not duplicate
        db.save_post("atlas", "geography", "Mars", "n1", None, None,
                     "book", "2026-07", title="Mars")
        assert db.seen("atlas", "Mars")
    finally:
        db.close(); os.remove(p)
