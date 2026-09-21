"""Scheduler entry point (spec §9): APScheduler cadence + monthly ZIM refresh.

Stub — see issue marginalia-run. Stagger the agents' start minutes so the feed
does not get seven posts at once; one monthly fetch_zims job rotates the archives.
"""
from __future__ import annotations


def main(cfg_path: str = "agents.yaml") -> None:
    """Load config, build the scheduler, run forever."""
    raise NotImplementedError("spec §9")


if __name__ == "__main__":
    main()
