"""Operational checks (spec §10 / marginalia-ops).

A scheduled job in run.py calls :func:`check_all` and logs each returned
warning to journald. The checks:

* **Disk** — alert when < ``MIN_FREE_GB`` free under the ZIM directory.
* **LLM** — alert while the LLM endpoint is down (agents already idle
  gracefully; this makes the idling visible).
* **Agent liveness** — expected cadence is ~3 posts/agent/day (every 8 h),
  so an agent whose last post is > 30 h old is stale. On a fresh fleet
  (no post older than 30 h) never-posted agents are not flagged, to avoid
  startup noise before the first staggered posting round completes.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone

MIN_FREE_GB = 10
MAX_POST_AGE_HOURS = 30

_TS = "%Y-%m-%dT%H:%M:%SZ"


def disk_free_gb(path: str) -> float:
    return shutil.disk_usage(path).free / 2 ** 30


def _parse(ts: str) -> datetime:
    return datetime.strptime(ts, _TS).replace(tzinfo=timezone.utc)


def last_post(db, agent_id: str):
    """ISO timestamp of the agent's newest post, or None."""
    row = db.conn.execute(
        "SELECT MAX(posted_at) FROM posts WHERE agent=?", (agent_id,)).fetchone()
    return row[0] if row and row[0] else None


def stale_agents(db, agent_ids, max_age_hours: float = MAX_POST_AGE_HOURS) -> list[str]:
    """Agents that have missed their posting cadence (see module docstring)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max_age_hours)
    last: dict[str, str | None] = {a: last_post(db, a) for a in agent_ids}

    ages = [_parse(l) for l in last.values() if l is not None]
    fleet_has_history = bool(ages) and min(ages) < cutoff

    stale = []
    for a, l in last.items():
        if l is None:
            if fleet_has_history:          # fleet is seasoned; you never posted
                stale.append(a)
        elif _parse(l) < cutoff:
            stale.append(a)
    return stale


def check_all(cfg, db, agents, llm=None) -> list[str]:
    """Run every ops check; one entry per warning (empty list = all good)."""
    warnings: list[str] = []

    free = disk_free_gb(cfg["zim"]["dir"])
    if free < MIN_FREE_GB:
        warnings.append(f"disk low: {free:.1f} GiB free under {cfg['zim']['dir']}")

    if llm is not None and not llm.is_online():
        warnings.append("llm offline: agents idling until it returns")

    stale = stale_agents(db, [a.id for a in agents])
    if stale:
        warnings.append(f"stale agents (no post in {MAX_POST_AGE_HOURS}h): "
                        + ", ".join(stale))
    return warnings
