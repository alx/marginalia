"""Tests for marginalia.board against a REAL, temporary beads repo.

``bd init`` needs a git repo and takes a moment, so one tmp repo is shared
by the whole module. The no-op path (missing binary) is tested separately
without touching a repo.
"""
import json
import shutil
import subprocess

import pytest

from marginalia.board import Board


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    if shutil.which("bd") is None:
        pytest.skip("bd (beads) CLI not installed")
    d = tmp_path_factory.mktemp("beads")
    subprocess.run(["git", "init", "-q", "."], cwd=d, check=True)
    r = subprocess.run(["bd", "init", "-p", "tb", "--non-interactive"],
                       cwd=d, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return d


def test_epic_task_subtask_roundtrip(repo):
    b = Board(str(repo))
    assert b.available()
    epic = b.open_epic("Draft: Sahara — atlas", assign="atlas")
    assert epic and epic.startswith("tb-")
    task = b.open_task(epic, "Editor review — round 1")
    assert task and task.startswith(epic + ".")
    sub = b.open_task(task, "Revision v2")
    assert sub and sub.startswith(task + ".")
    b.note(task, "working on it")
    b.close(sub, note="revised; guards pass")
    b.close(task, note="rejected: tone")
    b.close(epic, note="published as abc123")


def test_hitl_queue_listing(repo):
    b = Board(str(repo))
    epic = b.open_epic("Draft: Mars — atlas")
    hitl = b.open_task(epic, "Human approval: Mars — atlas", labels=("hitl",),
                       meta={"staging_note": "note123"})
    assert hitl
    queue = b.open_hitls()
    assert any(i["id"] == hitl and "hitl" in i.get("labels", [])
               and i["metadata"]["staging_note"] == "note123" for i in queue)
    # tidy up so the module-scoped repo stays quiet
    b.close(hitl)
    b.close(epic)


def test_cannot_close_epic_with_open_children(repo):
    b = Board(str(repo))
    epic = b.open_epic("Draft: Venus — atlas")
    b.open_task(epic, "Human approval: Venus — atlas", labels=("hitl",))
    r = b._run(["close", epic])            # refused: open child
    assert r is None
    for i in b.open_hitls():
        if i["parent"] == epic:
            b.close(i["id"])
    assert b._run(["close", epic]) is not None


def test_close_never_forces_past_open_children(repo):
    """The assignee force-retry must not bypass the bottom-up rule."""
    b = Board(str(repo))
    epic = b.open_epic("Draft: Mars — atlas", assign="atlas")
    b.open_task(epic, "Human approval: Mars — atlas", labels=("hitl",))
    b.close(epic)                          # must refuse, must NOT --force
    out = b._run(["list", "--flat", "--no-pager", "--json"])
    issues = {i["id"]: i for i in json.loads(out)}
    assert issues[epic]["status"] == "open"
    for i in b.open_hitls():              # tidy up
        if i["parent"] == epic:
            b.close(i["id"])
    b.close(epic)


def test_missing_binary_is_a_silent_noop(tmp_path):
    b = Board(str(tmp_path), bd="definitely-not-a-bd")
    assert not b.available()
    assert b.open_epic("x") is None
    assert b.open_hitls() == []
    b.close(None)                          # must not raise


def test_bd_without_repo_is_a_clean_noop(tmp_path):
    """bd exists but the directory is not a beads repo: warn, never raise."""
    b = Board(str(tmp_path))          # default binary name; dir has no bd repo
    if not b.available():
        pytest.skip("bd binary not installed")
    assert b.open_epic("Draft: X") is None
    assert b.open_hitls() == []
