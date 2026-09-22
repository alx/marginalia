"""Offline tests for the ops checks (marginalia-ops)."""
import os
import tempfile
from datetime import datetime, timedelta, timezone

from marginalia import ops
from marginalia.state import State

_TS = "%Y-%m-%dT%H:%M:%SZ"


def _db_with_posts(posts):
    """posts: {agent: datetime|None} -> temp State; returns (db, path)."""
    p = tempfile.mktemp(suffix=".sqlite")
    db = State(p)
    for agent, dt in posts.items():
        if dt is not None:
            ts = dt.strftime(_TS)
            db.conn.execute(
                "INSERT OR REPLACE INTO posts (agent, topic, path, note_id, posted_at)"
                " VALUES (?,?,?,?,?)",
                (agent, "t", f"path-{agent}", f"n-{agent}", ts))
    return db, p


def test_disk_free_gb_positive():
    assert ops.disk_free_gb("/home/alx" if os.path.isdir("/home/alx") else "/") > 0


def test_stale_agents_fresh_fleet_none_stale():
    now = datetime.now(timezone.utc)
    posts = {a: now - timedelta(hours=2) for a in ("atlas", "quark", "chronicle")}
    db, p = _db_with_posts(posts)
    try:
        assert ops.stale_agents(db, list(posts)) == []
    finally:
        db.close(); os.remove(p)


def test_stale_agents_old_post():
    now = datetime.now(timezone.utc)
    posts = {"atlas": now - timedelta(hours=2),
             "quark": now - timedelta(hours=40)}       # > 30h
    db, p = _db_with_posts(posts)
    try:
        assert ops.stale_agents(db, ["atlas", "quark"]) == ["quark"]
    finally:
        db.close(); os.remove(p)


def test_never_posted_flagged_only_on_seasoned_fleet():
    now = datetime.now(timezone.utc)
    # Seasoned fleet: another agent posted > 30h ago, "cipher" has never posted.
    posts = {"atlas": now - timedelta(hours=40), "quark": now - timedelta(hours=2)}
    db, p = _db_with_posts(posts)
    try:
        # atlas (>30h) is itself stale AND its old post marks the fleet as
        # seasoned, so never-posted cipher is flagged too.
        assert ops.stale_agents(db, ["atlas", "quark", "cipher"]) == ["atlas", "cipher"]
    finally:
        db.close(); os.remove(p)

    # Fresh fleet: no post older than 30h -> never-posted is not flagged yet.
    fresh = {a: now - timedelta(hours=1) for a in ("atlas", "quark")}
    db2, p2 = _db_with_posts(fresh)
    try:
        assert ops.stale_agents(db2, ["atlas", "quark", "cipher"]) == []
    finally:
        db2.close(); os.remove(p2)


def test_check_all_clean():
    now = datetime.now(timezone.utc)
    db, p = _db_with_posts({"atlas": now - timedelta(hours=1)})
    cfg = {"zim": {"dir": "/"}}
    agents = [type("A", (), {"id": "atlas"})]
    llm = type("L", (), {"is_online": staticmethod(lambda: True)})
    try:
        assert ops.check_all(cfg, db, agents, llm) == []
    finally:
        db.close(); os.remove(p)


def test_check_all_flags_offline_llm():
    now = datetime.now(timezone.utc)
    db, p = _db_with_posts({"atlas": now - timedelta(hours=1)})
    cfg = {"zim": {"dir": "/"}}
    agents = [type("A", (), {"id": "atlas"})]
    llm = type("L", (), {"is_online": staticmethod(lambda: False)})
    try:
        warnings = ops.check_all(cfg, db, agents, llm)
        assert any("llm offline" in w for w in warnings)
    finally:
        db.close(); os.remove(p)
