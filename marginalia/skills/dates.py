"""Dates skill (spec §4.7, Chronicle): on-this-day and careful date handling.

* ``today_article_title`` — the history-archive date article for today's date
  (``September_21``), which the scheduler posts each morning.
* ``on_this_day`` — the event bullets of a date article's Events section,
  whose links point at full articles in the history archive.
* ``rounding_violation`` — the hard guard half of the date rule: Chronicle
  keeps "c.", "circa", BCE and ranges exactly as the article writes them and
  refuses to round an uncertain date to a bare year.
"""
from __future__ import annotations

import re
from datetime import date

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# drafting instruction handed to the model when the skill is active
CONSTRAINT = (
    "Keep dates exactly as the article writes them: preserve 'c.', 'circa', "
    "BCE/CE and ranges. Never round an uncertain date to a single year."
)

_UNCERTAIN = re.compile(r"\b(?:c\.|ca\.|circa)\s+(\d{1,4})\b", re.I)


def today_article_title(today: date | None = None) -> str:
    """``September_21`` for today (or the given date)."""
    d = today or date.today()
    return f"{MONTHS[d.month - 1]}_{d.day}"


def on_this_day(soup, max_items: int = 12) -> list[str]:
    """Event bullets from a date article's Events section, in order."""
    items: list[str] = []
    for h in soup.select("h2"):
        if h.get_text(strip=True).lower() != "events":
            continue
        sec = h.find_parent("section") or h.parent
        for p in sec.find_all("p"):
            t = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
            if t:
                items.append(t)
                if len(items) >= max_items:
                    return items
    return items


def rounding_violation(draft: str, source: str) -> bool:
    """True if the draft uses a year the source marks as uncertain
    (``c. 3000 BCE``) without the ``c.``/``circa`` marker, i.e. rounds an
    uncertain date to a bare year."""
    for m in _UNCERTAIN.finditer(source):
        year = m.group(1)
        uses_year = re.search(rf"(?<![\d.]){year}(?:\.\d+)?\b", draft)
        has_marker = re.search(rf"\b(?:c\.|ca\.|circa)\s+{year}\b", draft, re.I)
        if uses_year and not has_marker:
            return True
    return False
