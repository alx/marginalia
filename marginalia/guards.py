"""Guards: the last gate before anything is posted (spec §5.1).

The model is prompted to use only the extracted article text; these checks make
that a hard guarantee rather than a request. A draft that fails is retried once,
then the candidate is skipped (the caller decides).
"""
from __future__ import annotations

import re


def _nums(s: str) -> set[str]:
    """Every number in s, commas stripped, as a set (so '9,200,000' == '9200000')."""
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*\.?\d*", s)}


# A dosing figure (e.g. "500 mg", "2 ml") must never reach a medicine post.
DOSE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|µg|g|ml|mL|IU)\b")


def ok(draft: str, source: str, agent, limit: int = 320) -> bool:
    """True iff the draft is usable.

    * within ``limit`` characters;
    * every number in the draft already appears in ``source`` (no invented stats);
    * for ``mycelia``, no dosing figures.
    """
    if len(draft) > limit or not _nums(draft) <= _nums(source):
        return False
    if getattr(agent, "id", None) == "mycelia" and DOSE.search(draft):
        return False
    return True
