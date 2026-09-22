"""Tests for the editorial gate (spec §7): review loop, escalation, HITL approvals.

The real State (SQLite) and real Agent run; only the LLM, publishers and the
beads board are faked. Store/article fakes are shared with test_agent.py.
"""
import json
from marginalia.agent import Agent, post_article
from marginalia.editorial import Editorial
from marginalia.state import State

from test_agent import (CFG, LEAD, FakeLib, FakeLLM, FakePub, FakeStore,
                        _article)


class ReviewLLM(FakeLLM):
    """FakeLLM plus scripted editorial verdicts and revisions."""

    def __init__(self):
        super().__init__()
        self.verdicts: list[dict] = []
        self.revisions: list[str] = []
        self.revise_calls = 0
        self.review_calls = 0

    def editor_review(self, persona, title, source, draft, recent, limit):
        self.review_calls += 1
        v = self.verdicts.pop(0) if self.verdicts else {"approved": True}
        return {**{"approved": True, "concerns": [], "suggested_revision": "",
                   "unparseable": False}, **v}

    def revise(self, persona, title, source, draft, concerns, limit):
        self.revise_calls += 1
        return self.revisions.pop(0) if self.revisions else "Revised: " + self.draft


class EditorPub:
    """The managing editor's publisher: staging posts + reaction lookup."""

    def __init__(self):
        self.posts: list[dict] = []
        self.notes: dict[str, dict] = {}
        self.reactions_by: dict[str, list] = {}

    def post(self, text, reply_id=None, file_ids=None, cw=None):
        nid = f"st{len(self.posts) + 1}"
        self.posts.append({"id": nid, "text": text, "reply_id": reply_id})
        self.notes[nid] = {"id": nid, "text": text, "replyId": reply_id}
        return nid

    def reactions(self, note_id):
        return self.reactions_by.get(note_id, [])


class FakeBoard:
    def __init__(self):
        self.epics: list[str] = []
        self.tasks: list[tuple] = []          # (id, title, labels, meta)
        self.assignees: dict[str, str] = {}
        self.closed: list[tuple] = []         # (id, note)
        self.notes: list[tuple] = []
        self._n = 0

    def open_epic(self, title, meta=None, assign=None):
        self._n += 1
        i = f"epic{self._n}"
        self.epics.append(i)
        if assign:
            self.assignees[i] = assign
        return i

    def open_task(self, parent, title, meta=None, labels=(), assign=None):
        self._n += 1
        i = f"task-{parent}-{self._n}"
        self.tasks.append((i, title, tuple(labels), meta))
        if assign:
            self.assignees[i] = assign
        return i

    def note(self, issue, text):
        self.notes.append((issue, text))

    def close(self, issue, note=None):
        self.closed.append((issue, note))


def _setup(tmp_path, verdicts, revisions=()):
    """Agent + Editorial wired together on a real State; the article is 'Mars'."""
    db = State(str(tmp_path / "state.sqlite"))
    store = FakeStore()
    store.articles = {"Mars": _article(LEAD, ["One", "Two"])}
    llm = ReviewLLM()
    llm.verdicts = list(verdicts)
    llm.revisions = list(revisions)
    pub = FakePub()
    board, edpub = FakeBoard(), EditorPub()
    ed = Editorial(board, edpub, "admin1")
    lib = FakeLib({"geography": store})
    agent = Agent("atlas", CFG, db, lib, llm, pub, editorial=ed)
    return db, agent, ed, board, edpub, llm


DRAFT = "The Sahara is vast and dry."
REJECT_A = {"approved": False, "concerns": ["invented a number"]}
REJECT_B = {"approved": False, "concerns": ["reads like the last post"]}
APPROVE = {"approved": True}


# -- the gate ---------------------------------------------------------------
def test_gate_approves_first_round(tmp_path):
    db, agent, ed, board, edpub, llm = _setup(tmp_path, [APPROVE])
    res = ed.gate(agent, "geography", "Mars", "Mars", "source", DRAFT, 1500)
    assert res["outcome"] == "publish" and res["draft"] == DRAFT
    assert llm.revise_calls == 0
    assert [t[1] for t in board.tasks] == ["Editor review — round 1"]
    assert board.closed[-1] == (board.tasks[0][0], "approved")
    assert len(board.epics) == 1               # one epic per draft
    assert db.pending_posts() == []


def test_gate_revises_then_approves(tmp_path):
    revised = "The Sahara covers about 9.2 million square kilometres."
    db, agent, ed, board, edpub, llm = _setup(tmp_path, [REJECT_A, APPROVE],
                                               revisions=[revised])
    res = ed.gate(agent, "geography", "Mars", "Mars", LEAD, DRAFT, 1500)
    assert res["outcome"] == "publish" and res["draft"] == revised
    titles = [t[1] for t in board.tasks]
    assert titles == ["Editor review — round 1", "Revision v2",
                      "Editor review — round 2"]
    # the revision subtask must close before its parent review round
    closed = [c[0] for c in board.closed]
    assert closed.index(board.tasks[1][0]) < closed.index(board.tasks[0][0])
    assert db.pending_posts() == []


def test_revision_failing_guards_is_discarded(tmp_path):
    bad = "The Sahara is 99999 square kilometres."   # number not in the source
    db, agent, ed, board, edpub, llm = _setup(tmp_path, [REJECT_A, REJECT_B],
                                               revisions=[bad])
    res = ed.gate(agent, "geography", "Mars", "Mars", LEAD, DRAFT, 1500)
    assert res["outcome"] == "pending"
    assert res["draft"] == DRAFT               # previous draft kept
    sub_note = [c[1] for c in board.closed if c[0] == board.tasks[1][0]][0]
    assert "guards" in sub_note


def test_escalation_posts_staging_and_records_hitl(tmp_path):
    db, agent, ed, board, edpub, llm = _setup(tmp_path, [REJECT_A, REJECT_B])
    res = ed.gate(agent, "geography", "Mars", "Mars", LEAD, DRAFT, 1500)
    assert res["outcome"] == "pending"

    staging = edpub.posts[-1]
    assert staging["text"].startswith("⏸ PENDING — Mars")
    # the fallback revision passed the guards, so it (not the original) is staged
    assert ("Revised: " + DRAFT) in staging["text"]
    assert "reads like the last post" in staging["text"]   # last round's concerns
    assert "as @atlas" in staging["text"]

    hitl = [t for t in board.tasks if "hitl" in t[2]]
    assert len(hitl) == 1
    assert hitl[0][3]["staging_note"] == staging["id"]
    assert board.assignees[hitl[0][0]] == "admin"      # human queue by assignee
    assert board.assignees[board.epics[0]] == "atlas"  # author owns the epic

    row = db.pending_posts()[0]
    assert row["staging_note"] == staging["id"]
    assert row["agent"] == "atlas" and row["path"] == "Mars"
    assert row["title"] == "Mars" and row["draft"] == "Revised: " + DRAFT
    assert row["status"] == "pending"
    # the epic stays open — its HITL child is still open
    assert res["epic"] not in [c[0] for c in board.closed]


# -- approvals ----------------------------------------------------------------
def _pending(tmp_path):
    db, agent, ed, board, edpub, llm = _setup(tmp_path, [REJECT_A, REJECT_B])
    ed.gate(agent, "geography", "Mars", "Mars", LEAD, DRAFT, 1500)
    return db, agent, ed, board, edpub


def test_no_admin_reaction_means_nothing_happens(tmp_path):
    db, agent, ed, board, edpub = _pending(tmp_path)
    staging = edpub.posts[-1]["id"]
    edpub.reactions_by[staging] = [
        {"type": "👍", "user": {"id": "somebot"}},        # not the admin
    ]
    assert ed.check_approvals(db, {"atlas": agent}) == 0
    assert len(db.pending_posts()) == 1
    assert agent.pub.posts == []


def test_admin_reaction_publishes_and_closes_the_loop(tmp_path):
    db, agent, ed, board, edpub = _pending(tmp_path)
    staging = edpub.posts[-1]["id"]
    edpub.reactions_by[staging] = [
        {"type": "👍", "user": {"id": "somebot"}},
        {"type": "👍", "user": {"id": "admin1"}},         # any emoji from @admin
    ]
    assert ed.check_approvals(db, {"atlas": agent}) == 1

    texts = [p[0] for p in agent.pub.posts]
    assert len(texts) == 1
    assert DRAFT in texts[0] and "[Full article]" in texts[0]
    assert "✅ Approved" in edpub.posts[-1]["text"]
    assert edpub.posts[-1]["reply_id"] == staging         # in-thread confirmation

    assert db.pending_posts() == []                       # published row is gone
    closed_ids = {c[0] for c in board.closed}
    assert any("published as" in (c[1] or "") for c in board.closed)   # epic closed
    hitl_id = next(t[0] for t in board.tasks if "hitl" in t[2])
    assert hitl_id in closed_ids                          # the hitl task closed too


def test_approval_without_agent_releases_row(tmp_path):
    db, agent, ed, board, edpub = _pending(tmp_path)
    staging = edpub.posts[-1]["id"]
    edpub.reactions_by[staging] = [{"type": "👍", "user": {"id": "admin1"}}]
    assert ed.check_approvals(db, {}) == 0                # agent missing
    rows = db.pending_posts()
    assert len(rows) == 1 and rows[0]["status"] == "pending"


def test_double_claim_publishes_once(tmp_path):
    db, agent, ed, board, edpub = _pending(tmp_path)
    staging = edpub.posts[-1]["id"]
    edpub.reactions_by[staging] = [{"type": "👍", "user": {"id": "admin1"}}]
    counts = [ed.check_approvals(db, {"atlas": agent}),
              ed.check_approvals(db, {"atlas": agent})]   # e.g. restart race
    assert sum(counts) == 1
    assert len(agent.pub.posts) == 1


# -- integration with post_article ---------------------------------------------
def test_post_article_with_editorial_publishes_and_closes_epic(tmp_path):
    db, agent, ed, board, edpub, llm = _setup(tmp_path, [APPROVE])
    note_id = post_article(agent, "geography", "Mars")
    assert note_id is not None
    assert any(f"published as {note_id}" in (c[1] or "") for c in board.closed)
    assert agent.pub.posts and DRAFT in agent.pub.posts[0][0]


def test_post_article_escalates_instead_of_publishing(tmp_path):
    db, agent, ed, board, edpub, llm = _setup(tmp_path, [REJECT_A, REJECT_B])
    note_id = post_article(agent, "geography", "Mars")
    assert note_id is None
    assert agent.pub.posts == []                          # author never posted
    assert edpub.posts and edpub.posts[0]["text"].startswith("⏸ PENDING")


def test_reaction_lookup_failure_keeps_row_pending(tmp_path):
    """A deleted staging note must not wedge or publish the row."""
    db, agent, ed, board, edpub = _pending(tmp_path)
    staging = edpub.posts[-1]["id"]
    def _boom(note_id):
        raise RuntimeError("note deleted")
    edpub.reactions = _boom
    assert ed.check_approvals(db, {"atlas": agent}) == 0
    rows = db.pending_posts()
    assert len(rows) == 1 and rows[0]["status"] == "pending"


def test_publish_failure_releases_row(tmp_path):
    """If the article vanished from the store, the row goes back to pending."""
    db, agent, ed, board, edpub = _pending(tmp_path)
    agent.lib.stores["geography"].articles = {}        # article vanished
    staging = edpub.posts[-1]["id"]
    edpub.reactions_by[staging] = [{"type": "👍", "user": {"id": "admin1"}}]
    assert ed.check_approvals(db, {"atlas": agent}) == 0
    rows = db.pending_posts()
    assert len(rows) == 1 and rows[0]["status"] == "pending"
    assert agent.pub.posts == []


def test_concerns_stored_as_json(tmp_path):
    db, agent, ed, board, edpub = _pending(tmp_path)
    row = db.pending_posts()[0]
    assert json.loads(row["concerns"]) == REJECT_B["concerns"]
