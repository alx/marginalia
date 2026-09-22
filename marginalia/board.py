"""Beads workflow board (marginalia-3rb): epics, review tasks, HITL queue.

The editorial workflow keeps its audit trail in beads: one EPIC per draft,
a TASK per editor review round, a SUBTASK per revision, and a ``hitl``-
labelled TASK per escalation — left open until the human resolves it.
All access goes through the ``bd`` CLI in a subprocess, serialised by one
lock so scheduler threads never interleave writes.

The board is best-effort by design: it must never block a publish. Every
method swallows and logs ``bd`` failures (returning ``None``); the
operational state that publish decisions depend on lives in ``state.sqlite``.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading

log = logging.getLogger("marginalia.board")


class Board:
    """A failure-tolerant wrapper around the bd CLI for one repository."""

    def __init__(self, repo: str, bd: str = "bd"):
        self.repo = repo
        self.bd = bd
        self._lock = threading.Lock()

    def available(self) -> bool:
        return shutil.which(self.bd) is not None

    def _run(self, args: list[str]) -> str | None:
        """Run one bd command; returns stdout, or None on any failure."""
        if not self.available():
            return None
        try:
            with self._lock:
                r = subprocess.run([self.bd, "-C", self.repo, *args],
                                   capture_output=True, text=True, timeout=60)
        except (subprocess.SubprocessError, OSError) as e:
            log.warning("board: bd %s error: %s", " ".join(args[:3]), e)
            return None
        if r.returncode != 0:
            log.warning("board: bd %s failed (%d): %s", " ".join(args[:3]),
                        r.returncode, (r.stderr or r.stdout).strip()[:300])
            return None
        return r.stdout.strip()

    def _run_raw(self, args: list[str]):
        """Run bd, returning (rc, stdout, stderr) for callers that must inspect the failure."""
        if not self.available():
            return 127, "", "bd binary not available"
        try:
            with self._lock:
                r = subprocess.run([self.bd, "-C", self.repo, *args],
                                   capture_output=True, text=True, timeout=60)
        except (subprocess.SubprocessError, OSError) as e:
            return 1, "", str(e)
        return r.returncode, r.stdout, r.stderr

    def _create(self, title, *, type_="task", parent=None, labels=(),
                meta=None, assign=None):
        args = ["create", title]
        if type_ != "task":
            args += ["-t", type_]
        if parent:
            args += ["--parent", parent]
        if labels:
            args += ["-l", ",".join(labels)]
        if meta:
            args += ["--metadata", json.dumps(meta)]
        if assign:
            args += ["--assignee", assign]
        out = self._run(args + ["--silent"])
        return out.split()[0] if out else None

    def open_epic(self, title, meta=None, assign=None):
        """The epic for one draft. Returns the issue id, or None."""
        return self._create(title, type_="epic", labels=("editorial",),
                            meta=meta, assign=assign)

    def open_task(self, parent, title, meta=None, labels=(), assign=None):
        """A child task of an epic (a review round) or subtask (a revision).

        ``assign`` is the owner (an agent id, ``editor`` or ``admin``) which
        makes ``bd list --assignee <name>`` a per-owner queue.
        """
        return self._create(title, parent=parent, labels=labels, meta=meta,
                            assign=assign)

    def note(self, issue, text):
        """Append a note to an issue (audit trail)."""
        if issue:
            self._run(["update", issue, "--append-notes", text[:1000]])

    def close(self, issue, note=None):
        """Close an issue, appending a final note when given.

        bd 1.3+ refuses a close by an actor other than the assignee; the
        scheduler acts on the bots' behalf, so that specific error is
        retried with ``--force``. An "open child" refusal is NEVER forced —
        the epic/task/subtask hierarchy must stay bottom-up.
        """
        if not issue:
            return
        if note:
            self._run(["update", issue, "--append-notes", note[:1000]])
        rc, out, err = self._run_raw(["close", issue])
        if rc == 0:
            return
        text = (err or out).strip()
        if "assignee" in text:
            rc2, out2, err2 = self._run_raw(["close", issue, "--force"])
            if rc2 != 0:
                log.warning("board: bd close %s --force failed (%d): %s",
                            issue, rc2, (err2 or out2).strip()[:300])
        else:
            log.warning("board: bd close %s failed (%d): %s", issue, rc, text[:300])

    def open_hitls(self) -> list[dict]:
        """The open human-in-the-loop queue, as a list of issue dicts."""
        out = self._run(["list", "-l", "hitl", "--flat", "--no-pager", "--json"])
        if out is None:
            return []
        try:
            data = json.loads(out)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            log.warning("board: could not parse hitl listing")
            return []
