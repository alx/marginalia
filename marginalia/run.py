"""Scheduler entry point (spec §9): one process, all agents, unattended.

* **Posting** — one interval job per agent, ``24 / posts_per_day`` hours apart.
  Agents start staggered (``STAGGER_MINUTES`` apart) so the feed does not get
  seven posts at once.
* **Chronicle's morning post** — a daily 08:30 job posting today's date
  article ("September_21"), falling back to a normal pick when the history
  archive has none for today.
* **Replies** — each agent polls mentions every ``poll_seconds`` (45), also
  staggered.
* **ZIM refresh** — a monthly (1st, 03:30) ``fetch_zims.py`` run rotates the
  archives; it runs as a subprocess so a hung download cannot take the
  scheduler down with it.

Meant to run forever under systemd (see the deploy issues). Every job body
catches and logs its own exceptions, so one bad note never kills the process.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from marginalia.agent import Agent, poll, post_article, tick
from marginalia.board import Board
from marginalia.editorial import Editorial
from marginalia.llm import LLM
from marginalia.publisher import Publisher
from marginalia.skills import dates as sk_dates
from marginalia import ops
from marginalia.state import State
from marginalia.zimstore import ZimLibrary

log = logging.getLogger("marginalia.run")

STAGGER_MINUTES = 7      # agent i starts i*7 minutes after agent 0
MORNING_HOUR, MORNING_MINUTE = 8, 30   # Chronicle's "on this day" post


# -- building the pieces ------------------------------------------------------
def build(cfg_path: str = "agents.yaml"):
    """Load config, state, library, the editorial gate, and the tokened agents."""
    cfg = yaml.safe_load(Path(cfg_path).read_text())
    db = State(cfg.get("state", "state.sqlite"))
    lib = ZimLibrary(cfg["zim"]["dir"])
    llm = LLM(cfg["llm"]["base_url"], cfg["llm"]["model"],
              timeout=cfg["llm"].get("timeout", 120))
    # Editorial gate (spec §7): active only when the editor token exists; the
    # board is best-effort, so a missing bd binary degrades to log-only.
    board = Board(cfg.get("beads", {}).get("repo", "."))
    editorial = None
    etoken = os.environ.get("MK_TOKEN_EDITOR", "")
    if etoken:
        editorial = Editorial(
            board,
            Publisher(cfg["misskey"]["host"], etoken, cfg["misskey"].get("ssl", False)),
            os.environ.get("MK_ADMIN_USER_ID", ""))
    else:
        log.warning("MK_TOKEN_EDITOR unset: editorial gate disabled")
    agents: list[Agent] = []
    for name, a in cfg["agents"].items():
        token = os.environ.get(a.get("token_env", ""), "")
        if not token:
            log.warning("skip %s: no token for %s", name, a.get("token_env"))
            continue
        pub = Publisher(cfg["misskey"]["host"], token, cfg["misskey"].get("ssl", False))
        agents.append(Agent(name, cfg, db, lib, llm, pub, editorial=editorial))
    return cfg, db, lib, agents, editorial


# -- job bodies (each catches its own errors) ---------------------------------
def post_job(agent: Agent) -> None:
    """One posting iteration for one agent."""
    try:
        if not agent.llm.is_online():
            log.info("post %s: LLM offline, skipping", agent.id)
            return
        if tick(agent):
            log.info("post %s: published", agent.id)
    except Exception:
        log.exception("post %s failed", agent.id)


def poll_job(agent: Agent) -> None:
    """One reply pass for one agent (poll() itself checks the LLM)."""
    try:
        if (n := poll(agent)):
            log.info("poll %s: answered %d", agent.id, n)
    except Exception:
        log.exception("poll %s failed", agent.id)


def date_job(agent: Agent) -> None:
    """Chronicle's morning post: today's date article, else a normal pick."""
    try:
        if not agent.llm.is_online():
            log.info("date %s: LLM offline, skipping", agent.id)
            return
        title = sk_dates.today_article_title()
        hit = agent.lib.find(title, prefer=agent.topics)
        if hit and not agent.db.seen(agent.id, hit[1][0]):
            if post_article(agent, hit[0], hit[1][0]):
                log.info("date %s: posted %s", agent.id, title)
                return
        tick(agent)                                   # no date article / already posted
    except Exception:
        log.exception("date %s failed", agent.id)


def ops_job(cfg, db, agents, llm) -> None:
    """Periodic ops checks; one WARNING log line per problem (marginalia-ops)."""
    try:
        for warning in ops.check_all(cfg, db, agents, llm):
            log.warning("OPS: %s", warning)
    except Exception:
        log.exception("ops check failed")


def refresh_job(cfg_path: str) -> None:
    """Monthly ZIM rotation; subprocess so a hung download stays contained."""
    log.info("monthly ZIM refresh: starting")
    r = subprocess.run([sys.executable, "-m", "marginalia.fetch_zims", cfg_path])
    if r.returncode:
        log.error("ZIM refresh failed (exit %d)", r.returncode)
    else:
        log.info("ZIM refresh done")


def approval_job(editorial, db, agents_by_id) -> None:
    """HITL pass: publish pending drafts the admin has reacted to (spec §7)."""
    try:
        if editorial and (n := editorial.check_approvals(db, agents_by_id)):
            log.info("approvals: published %d", n)
    except Exception:
        log.exception("approval check failed")


# -- scheduler -----------------------------------------------------------------
def build_scheduler(cfg, agents, cfg_path: str = "agents.yaml",
                    now: datetime | None = None, db=None, llm=None,
                    editorial=None) -> BlockingScheduler:
    """The full job table: posting, polling, date article, approvals,
    monthly refresh, ops."""
    now = now or datetime.now()
    sched = BlockingScheduler()
    poll_every = int(cfg.get("defaults", {}).get("poll_seconds", 45))

    for i, ag in enumerate(agents):
        start = now + timedelta(minutes=i * STAGGER_MINUTES)
        sched.add_job(
            post_job, IntervalTrigger(hours=24.0 / ag.posts_per_day),
            args=[ag], id=f"post-{ag.id}",
            name=f"post {ag.id}",
            next_run_time=start,
            max_instances=1, coalesce=True, misfire_grace_time=6 * 3600)
        sched.add_job(
            poll_job, IntervalTrigger(seconds=poll_every),
            args=[ag], id=f"poll-{ag.id}",
            name=f"poll {ag.id}",
            next_run_time=start + timedelta(seconds=15),
            max_instances=1, coalesce=True, misfire_grace_time=3600)
        if ag.daily_date_article:
            sched.add_job(
                date_job, CronTrigger(hour=MORNING_HOUR, minute=MORNING_MINUTE),
                args=[ag], id=f"date-{ag.id}",
                name=f"date article {ag.id}",
                max_instances=1, coalesce=True, misfire_grace_time=6 * 3600)

    sched.add_job(
        refresh_job, CronTrigger(day=1, hour=3, minute=30),
        args=[cfg_path], id="zim-refresh", name="monthly ZIM refresh",
        max_instances=1, coalesce=True, misfire_grace_time=24 * 3600)

    # HITL approvals: any emoji from the admin on a staging note publishes
    # the draft under the author account. Runs even when editorial is None
    # (the job body is a no-op), so the job table stays stable in tests.
    sched.add_job(
        approval_job, IntervalTrigger(
            minutes=int(cfg.get("defaults", {}).get("approval_every_minutes", 5))),
        args=[editorial, db, {a.id: a for a in agents}],
        id="approvals", name="HITL approvals",
        max_instances=1, coalesce=True, misfire_grace_time=3600)

    # First ops check 15 min after boot (after the first posting round has
    # had a chance to complete), then every 6 h.
    sched.add_job(
        ops_job, IntervalTrigger(hours=6),
        args=[cfg, db, agents, llm], id="ops", name="ops checks",
        next_run_time=now + timedelta(minutes=15),
        max_instances=1, coalesce=True, misfire_grace_time=3600)
    return sched


def main(cfg_path: str = "agents.yaml") -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg, db, lib, agents, editorial = build(cfg_path)
    if not agents:
        log.error("no agents have tokens; nothing to do (set MK_TOKEN_* env vars)")
        return
    log.info("scheduling %d agents: %s", len(agents), ", ".join(a.id for a in agents))
    llm = agents[0].llm          # shared by every agent
    build_scheduler(cfg, agents, cfg_path, db=db, llm=llm,
                    editorial=editorial).start()                   # blocks forever


if __name__ == "__main__":
    main()
