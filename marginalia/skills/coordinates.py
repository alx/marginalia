"""Coordinates skill (spec §4.7, Atlas): a plain-text decimal coordinate line.

When the infobox carries geographic coordinates (``46°36′00″N 116°52′00″E``,
``46.5 N``, or a decimal pair), the agent appends one line to the post, e.g.
``Coordinates: 46.6, -116.8667``. Negative for S/W hemispheres, the convention
readers can paste into a map.
"""
from __future__ import annotations

import re

# a degree value (digits with any single non-digit separators, e.g. ° ′ ″ ' ")
# immediately followed, past separators/whitespace, by a hemisphere letter
_HEMI = re.compile(r"(-?\d{1,3}(?:[^\d]\d{1,2}){0,2}[^\d]*)\s*([NSEW])\b")
_DECIMAL = re.compile(r"(-?\d{1,3}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)")


def _parts(tok: str) -> tuple[float, float, float]:
    """``46°36′00`` -> (46, 36, 0); decimal points are kept."""
    bits = [b for b in re.split(r"[^\d.]+", tok.strip()) if b]
    vals = [float(b) for b in bits]
    while len(vals) < 3:
        vals.append(0.0)
    return vals[0], vals[1], vals[2]


def _tot(p: tuple[float, float, float]) -> float:
    return p[0] + p[1] / 60 + p[2] / 3600


def decimal(line: str) -> tuple[float, float] | None:
    """Parse an infobox coordinate line to (lat, lon), or None if absent.

    Handles dms/dm forms with hemisphere letters and bare decimal pairs
    (``46.6, -116.867``) where the sign carries the hemisphere.
    """
    lat: float | None = None
    lon: float | None = None
    for m in _HEMI.finditer(line):
        v = _tot(_parts(m.group(1)))
        h = m.group(2).upper()
        if h in "NS" and lat is None:
            lat = v if h == "N" else -v
        elif h in "EW" and lon is None:
            lon = v if h == "E" else -v
        if lat is not None and lon is not None:
            break
    if lat is not None and lon is not None:
        return round(lat, 4), round(lon, 4)
    if (m := _DECIMAL.search(line)):
        return float(m.group(1)), float(m.group(2))
    return None


def from_infobox(box: dict) -> str | None:
    """The coordinate line for a post, or None when the infobox has none."""
    for key, val in box.items():
        if "oordinate" in key:
            if d := decimal(val):
                return f"Coordinates: {d[0]}, {d[1]}"
    return None
