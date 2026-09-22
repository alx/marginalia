"""Managing-editor gate between the guards and publish (marginalia-3rb).

Flow per draft, after the guards have passed:

  epic -> review round 1
         -> (rejected: revision subtask -> review round 2)
    approved      publish normally, close the epic
    rejected x2   escalate: the ``editor`` account posts the draft as a
                  staging note and a ``hitl``-labelled task opens on the
                  epic; it stays open until the approval poller sees the
                  admin's reaction and publishes.

Guards stay the hard floor: a revision that breaks a guard is discarded and
the previous draft is what gets reviewed / published. The board is
best-effort audit; ``state.sqlite`` holds the operational state that
publishing decisions rely on.
"""
from __future__ import annotations

import logging

from marginalia import guards
from marginalia.agent import finalize

log = logging.getLogger("marginalia.editorial")

REVIEW_ROUNDS = 2


class Editorial:
    """Gate + escalation + approval handling, shared by all agents."""

    def __init__(self, board, editor_pub, admin_user_id: str):
        self.board = board
        self.editor_pub = editor_pub
        self.admin_user_id = admin_user_id

    # -- the gate ----------------------------------------------------------
    def gate(self, agent, topic, path, title, source, draft, limit) -> dict:
        """Review ``draft`` (already guard-clean) and resolve its fate.

        Returns ``{"outcome": "publish"|"pending", "draft": str, "epic": id}``.
        On ``pending`` the draft is staged under the editor account and the
        human is queued on beads; the caller must not publish it.
        """
        epic = self.board.open_epic(
            f"Draft: {title} — {agent.id}",
            meta={"agent": agent.id, "article": title}, assign=agent.id)
        grounding = f"{title}\n{source}"
        current = draft
        concerns: list[str] = []
        for rnd in range(1, REVIEW_ROUNDS + 1):
            task = self.board.open_task(epic, f"Editor review — round {rnd}",
                                        assign="editor")
            verdict = agent.llm.editor_review(
                agent.persona, title, source, current,
                self._recent(agent.db, agent.id), limit)
            if verdict.get("unparseable"):
                log.warning("editorial %s: round %d verdict unparseable, failing open",
                            agent.id, rnd)
            if verdict["approved"]:
                self.board.close(task, note="approved")
                return {"outcome": "publish", "draft": current, "epic": epic}
            concerns = verdict["concerns"] or ["no specific concerns given"]
            if rnd < REVIEW_ROUNDS:
                # the revision is a child of this review round; beads will not
                # let the round close while its subtask is still open, so the
                # subtask is closed first and the round after it
                sub = self.board.open_task(task, f"Revision v{rnd + 1}",
                           assign=agent.id)
                revised = agent.llm.revise(
                    agent.persona, title, source, current, concerns, limit)
                bad = guards.report(revised, grounding, agent, limit)
                if bad:
                    self.board.close(sub, note=f"revision failed guards "
                                               f"({', '.join(bad)}); previous draft kept")
                else:
                    current = revised
                    self.board.close(sub, note="revised; guards pass")
            self.board.close(task, note="rejected: " + " | ".join(concerns)[:400])
        staging = self._escalate(agent, epic, topic, path, title, current, concerns)
        log.info("editorial %s: '%s' escalated to human review (staging %s)",
                 agent.id, title, staging)
        return {"outcome": "pending", "draft": current, "epic": epic}

    def _recent(self, db, agent_id: str, n: int = 15) -> str:
        """A short digest of the most recent posts, for the duplication check."""
        out = []
        for r in db.recent_posts(n):
            text = (r.get("text") or r.get("title") or "").replace("\n", " ")[:140]
            out.append(f"- [{r['agent']}] {r.get('title') or ''}: {text}")
        return "\n".join(out)

    def _escalate(self, agent, epic, topic, path, title, draft, concerns) -> str | None:
        """Post the draft as a pending note under the editor account.

        Opens the HITL task on the epic and records the staging row in
        ``state.sqlite`` (the poller's source of truth).
        """
        note = (f"⏸ PENDING — {title} ({agent.id})\n\n{draft}\n\n"
                "Editor concerns:\n" + "\n".join(f"- {c}" for c in concerns)
                + f"\n\nReact with any emoji to approve publication as @{agent.id}.")
        staging = self.editor_pub.post(note)
        hitl = self.board.open_task(
            epic, f"Human approval: {title} — {agent.id}",
            labels=("hitl",),
            meta={"staging_note": staging, "agent": agent.id, "article": title},
            assign="admin")
        agent.db.save_pending(epic, hitl, staging, agent.id, topic, path, title,
                              draft, concerns)
        return staging

    # -- approvals -----------------------------------------------------------
    def check_approvals(self, db, agents_by_id: dict) -> int:
        """Publish pending drafts the admin has reacted to. Returns the count.

        Any emoji reaction from ``admin_user_id`` on the staging note is an
        approval. The staging note is kept (audit trail); a short confirmation
        is posted in-thread under the editor account.
        """
        published = 0
        for row in db.pending_posts():
            staging = row["staging_note"]
            try:
                rxs = self.editor_pub.reactions(staging)
            except Exception:
                log.exception("approvals: reactions for %s failed", staging)
                continue
            emoji = next((r.get("type") for r in rxs
                          if (r.get("user") or {}).get("id") == self.admin_user_id), None)
            if emoji is None or not db.claim_pending(row["id"]):
                continue
            try:
                agent = agents_by_id.get(row["agent"])
                note_id = (finalize(agent, row["topic"], row["path"], row["draft"])
                           if agent else None)
            except Exception:
                log.exception("approvals: publish of '%s' raised", row["title"])
                note_id = None
            if not note_id:
                db.release_pending(row["id"])
                log.warning("approvals: could not publish '%s' "
                            "(agent %r available?)", row["title"], row["agent"])
                continue
            db.resolve_pending(row["id"], note_id)
            self.board.note(row["hitl"],
                            f"Approved by @admin ({emoji}) — published as {note_id}")
            self.board.close(row["hitl"])
            self.board.close(row["epic"], note=f"published as {note_id}")
            try:
                self.editor_pub.post(
                    f"✅ Approved — published by @{agent.id}", reply_id=staging)
            except Exception:
                log.exception("approvals: confirmation reply failed")
            log.info("approvals: published '%s' as %s", row["title"], note_id)
            published += 1
        return published
