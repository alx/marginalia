"""Living-person skill (spec §4.7, Palette/Lexis): neutral mode.

For articles about someone still living, the agent sticks to career/public
facts from the lead — no speculation about private life or controversies
unless the lead itself states them. Detection is deliberately dumb: a person
infobox has "Born" and, for the deceased, a "Died" row; living people lack it.
"""
from __future__ import annotations

CONSTRAINT = (
    "The article is about a living person: use career facts from the lead only; "
    "no speculation about private life or controversies."
)

_BORN = ("born", "birth date", "date of birth")
_DIED = ("died", "death date", "date of death")


def is_living(box: dict) -> bool:
    """True if the infobox marks a person who was born and never died (yet).

    Empty boxes and non-person infoboxes (no Born row) return False.
    """
    keys = {k.lower().strip() for k in box}
    born = any(k in keys for k in _BORN)
    died = any(k in keys for k in _DIED)
    return born and not died
