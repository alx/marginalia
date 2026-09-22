"""Guards: the last gate before anything is posted (spec §5.1).

The model is prompted to use only the extracted article text; these checks make
that a hard guarantee rather than a request. A draft that fails is retried once,
then the candidate is skipped (the caller decides).
"""
from __future__ import annotations

import re

from marginalia.skills import dates as _dates
from marginalia.skills import safety as _safety


def _nums(s: str) -> set[str]:
    """Every number in s, commas stripped, as a set (so '9,200,000' == '9200000').

    A trailing full stop is not part of the number ('in 2003.' -> '2003'), so
    numbers ending a sentence are not mis-tokenised as '2003.'.
    """
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}


# A dosing figure (e.g. "500 mg", "2 ml") must never reach a medicine post.
DOSE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|µg|g|ml|mL|IU)\b")


def ok(draft: str, source: str, agent, limit: int = 320) -> bool:
    """True iff the draft is usable.

    * within ``limit`` characters;
    * every number in the draft already appears in ``source`` (no invented stats);
    * no dosing figures for ``mycelia`` or any agent carrying the safety skill;
    * no advice phrasing, no rounded uncertain dates (safety / dates skills).
    """
    if len(draft) > limit or not _nums(draft) <= _nums(source):
        return False
    sk = getattr(agent, "skills", None) or []
    if getattr(agent, "id", None) == "mycelia" or "safety" in sk:
        if DOSE.search(draft):
            return False
    if "safety" in sk and _safety.ADVICE.search(draft):
        return False
    if "dates" in sk and _dates.rounding_violation(draft, source):
        return False
    return True
