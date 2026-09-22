"""Spoilers skill (spec §4.7, Palette): plot details behind a content warning.

A Misskey content warning hides the *whole* note body until tapped, so the
rule is: when the article has a plot section (it is a film with a story), the
post goes out with ``cw="Spoilers"`` and the visible draft stays spoiler-free
(the drafting constraint tells the model to keep to form, craft and technique).
"""
from __future__ import annotations

CW = "Spoilers"

CONSTRAINT = (
    "Say nothing about the plot, the ending, or twists; keep to form, craft "
    "and technique, and credit the maker."
)

_PLOT_HEADINGS = {"plot", "synopsis", "storyline"}


def has_plot(soup) -> bool:
    """True if the article has a Plot/Synopsis h2 (i.e. a film with a story)."""
    return any(h.get_text(" ", strip=True).lower() in _PLOT_HEADINGS
               for h in soup.select("h2"))


def cw_for(soup) -> str | None:
    """The content warning for this article, or None to post without one."""
    return CW if has_plot(soup) else None
