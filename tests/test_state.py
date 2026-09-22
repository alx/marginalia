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
