"""Infobox skill (spec §4.7): structured facts as drafting context.

The parse itself (``extract.infobox``) runs for every agent; this skill
decides that the agent *may* draw on the infobox: ``card()`` renders the rows
as "Label: value" lines, which ``agent.tick`` appends to the lead so the
drafting model can use infobox measurements as its hook and the number guard
still passes (they are in the source).
"""
from __future__ import annotations

_MAX_ROWS = 12
_MAX_LEN = 900


def card(box: dict) -> str:
    """Infobox rows as 'Label: value. …' text, or '' when there is no infobox."""
    if not box:
        return ""
    rows = [f"{k}: {v}" for k, v in list(box.items())[:_MAX_ROWS] if v]
    return ". ".join(rows) + "." if rows else ""
