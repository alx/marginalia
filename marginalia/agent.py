"""Agent loops: tick() posting (spec §5), poll() replies (spec §6).

Stubs — see issues marginalia-agent (tick) and marginalia-poll (poll).
"""
from __future__ import annotations


def pick_candidate(agent):
    """Run the seed->expand->filter->score->pick funnel; return (topic, path)."""
    raise NotImplementedError("spec §4.3/§5")


def tick(agent) -> None:
    """One posting iteration: pick, extract, draft, guard, image, post, build note."""
    raise NotImplementedError("spec §5")


def poll(agent) -> None:
    """One reply iteration: fetch new mentions, climb to root, ground, answer."""
    raise NotImplementedError("spec §6")
