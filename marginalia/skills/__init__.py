"""Per-agent skill modules (spec §4.7).

The *shared* skills (lead/section/headings, infobox parsing, images,
math-to-TeX, unicode sub/superscripts) live in ``extract.py`` / ``images.py``
because every agent uses them. This package holds the skills that only some
agents switch on, named exactly as they appear in ``agents.yaml``:

    units          converted-value hints appended to measurements (Quark, Atlas)
    coordinates    decimal coordinate line from the infobox (Atlas)
    dates          on-this-day titles, circa/BCE handling (Chronicle)
    safety         medical guard: advice/dose refusal, general info only (Mycelia)
    spoilers       content warning when the article has a plot (Palette)
    living_person  neutral mode for articles about living people (Palette, Lexis)
    infobox        structured infobox card offered as drafting context (several)

Wiring: ``Agent`` keeps the raw name list from agents.yaml as ``agent.skills``;
callers ask ``has(agent.skills, "units")`` and import the module they need.
Skill modules are plain functions with no state, so they are trivially testable
and safe to run in the scheduler's thread pool.
"""
from __future__ import annotations

from marginalia.skills import (coordinates, dates, infobox, living_person,  # noqa: F401
                               safety, spoilers, units)

# skill name in agents.yaml -> module. Names not listed here (tex, scripts,
# images) are handled by extract.py / images.py for every agent already.
ALL = {
    "coordinates": coordinates,
    "dates": dates,
    "infobox": infobox,
    "living_person": living_person,
    "safety": safety,
    "spoilers": spoilers,
    "units": units,
}


def has(skills: list[str] | None, name: str) -> bool:
    """True if an agent's agents.yaml skill list includes ``name``."""
    return name in (skills or [])
