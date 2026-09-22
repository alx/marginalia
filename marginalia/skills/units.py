"""Units skill (spec §4.7): keep the article's unit, add a converted value.

Applied to the *finished* post text by code, after the guards have passed —
never by the model, because a converted value is a number that does not appear
in the article and would trip the number-grounding guard (spec §5.1).

Only a small, fixed set of conversions; anything else is left alone.
"""
from __future__ import annotations

import re

# number, optional "million/billion/trillion" suffix
# the core matches plain and comma-grouped digits, and also space-grouped
# thousands ("152 097 597", ZIM/French style) — without that, "152 097 597 km"
# matched only the final "597" and got converted as 597 km.
_NUM_CORE = r"\d[\d,]*(?:\.\d+)?(?:[ \u00A0]\d{3})*(?:\.\d+)?"
_NUM = rf"({_NUM_CORE})(\s*(?:million|billion|trillion))?"
_MULT = {"": 1.0, "million": 1e6, "billion": 1e9, "trillion": 1e12}


def _value(num: str, suffix: str | None) -> float:
    n = num.replace(",", "").replace(" ", "").replace("\u00A0", "")
    return float(n) * _MULT.get((suffix or "").strip().lower(), 1.0)


def _fmt(x: float) -> str:
    if x >= 100:
        return f"{x:,.0f}"
    if x >= 10:
        return f"{x:,.1f}"
    return f"{x:,.2f}"


def convert_km(text: str) -> str:
    """Append `(≈ N mi)` / `(≈ N mi²)` after kilometre measurements."""
    for unit, conv, factor in ((r"km²", "mi²", 0.386102),
                               (r"square\s+km\b", "square miles", 0.386102),
                               (r"square\s+kilometres?", "square miles", 0.386102),
                               (r"km\b", "mi", 0.621371)):
        pat = re.compile(_NUM + rf"\s*{unit}")

        def _sub(m: re.Match, _conv=conv, _factor=factor):
            v = _value(m.group(1), m.group(2)) * _factor
            return f"{m.group(0)} (≈ {_fmt(v)} {_conv})"

        text = pat.sub(_sub, text)
    return text


def convert_mass(text: str) -> str:
    pat = re.compile(_NUM + r"\s*kg\b")

    def _sub(m: re.Match):
        v = _value(m.group(1), m.group(2)) * 2.20462
        return f"{m.group(0)} (≈ {_fmt(v)} lb)"
    return pat.sub(_sub, text)


def convert_celsius(text: str) -> str:
    pat = re.compile(rf"({_NUM_CORE})\s*°?C\b")

    def _sub(m: re.Match):
        f = _value(m.group(1), None) * 9 / 5 + 32
        return f"{m.group(0)} ({_fmt(f)} °F)"
    return pat.sub(_sub, text)


def augment(text: str) -> str:
    """Add converted values where the article's unit appears. Idempotent."""
    if "≈" in text:
        return text
    return convert_celsius(convert_mass(convert_km(text)))
