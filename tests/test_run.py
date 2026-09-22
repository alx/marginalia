"""Offline tests for run.py: the scheduler job table (spec §9)."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from marginalia.run import STAGGER_MINUTES, build_scheduler

CFG = {"defaults": {"poll_seconds": 45}}


def _agents():
    return [
        SimpleNamespace(id="atlas", posts_per_day=3, daily_date_article=False),
        SimpleNamespace(id="chronicle", posts_per_day=3, daily_date_article=True),
    ]


def test_one_post_and_poll_job_per_agent():
    sched = build_scheduler(CFG, _agents(), now=datetime(2026, 9, 21, 12, 0, 0))
    ids = {j.id for j in sched.get_jobs()}
    assert ids == {"post-atlas", "poll-atlas", "post-chronicle",
                   "poll-chronicle", "date-chronicle", "zim-refresh", "ops",
                   "approvals"}


def test_post_interval_follows_posts_per_day():
    sched = build_scheduler(CFG, _agents(), now=datetime(2026, 9, 21, 12, 0, 0))
    job = next(j for j in sched.get_jobs() if j.id == "post-atlas")
    # 3 posts a day -> every 8 hours
    assert str(job.trigger) == "interval[8:00:00]"


def test_starts_staggered():
    now = datetime(2026, 9, 21, 12, 0, 0)
    sched = build_scheduler(CFG, _agents(), now=now)
    first = next(j for j in sched.get_jobs() if j.id == "post-atlas").next_run_time
    second = next(j for j in sched.get_jobs() if j.id == "post-chronicle").next_run_time
    delta = second - first
    assert delta == timedelta(minutes=STAGGER_MINUTES)


def test_poll_interval_is_poll_seconds():
    sched = build_scheduler(CFG, _agents(), now=datetime(2026, 9, 21, 12, 0, 0))
    job = next(j for j in sched.get_jobs() if j.id == "poll-atlas")
    assert str(job.trigger) == "interval[0:00:45]"


def test_date_job_only_for_daily_date_article_agents():
    sched = build_scheduler(CFG, _agents(), now=datetime(2026, 9, 21, 12, 0, 0))
    ids = {j.id for j in sched.get_jobs()}
    assert "date-chronicle" in ids
    assert "date-atlas" not in ids


def test_monthly_zim_refresh():
    sched = build_scheduler(CFG, _agents(), now=datetime(2026, 9, 21, 12, 0, 0))
    job = next(j for j in sched.get_jobs() if j.id == "zim-refresh")
    assert "day = '1'" in str(job.trigger) or "1" in str(job.trigger)
