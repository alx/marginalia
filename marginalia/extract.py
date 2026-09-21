"""Article HTML -> lead, sections, infobox, images, math, scripts (spec §4.2).

Stub — see issue marginalia-extract. Selectors target recent mwoffliner builds
(section wrappers + `resource` attrs); tune against the actual archives.
"""
from __future__ import annotations

from bs4 import BeautifulSoup


def parse(html: str) -> BeautifulSoup:
    """Parse article HTML, strip junk, convert math->TeX and sub/sup->Unicode."""
    raise NotImplementedError("spec §4.2")


def math_to_tex(soup: BeautifulSoup) -> None:
    """Replace rendered maths with \\( TeX \\) so Misskey can display it."""
    raise NotImplementedError("spec §4.2")


def unicode_scripts(soup: BeautifulSoup) -> None:
    """Turn <sub>/<sup> runs into Unicode sub/superscripts (H₂O, m²)."""
    raise NotImplementedError("spec §4.2")


def lead(soup: BeautifulSoup, max_chars: int = 900) -> str:
    """Lead section prose, whitespace-normalised, truncated."""
    raise NotImplementedError("spec §4.2")


def headings(soup: BeautifulSoup) -> list[str]:
    """All h2 headings, in order."""
    raise NotImplementedError("spec §4.2")


def section(soup: BeautifulSoup, heading: str, max_chars: int = 1500) -> str:
    """Text of the h2 section named `heading` (case-insensitive), or ''."""
    raise NotImplementedError("spec §4.2")


def infobox(soup: BeautifulSoup) -> dict:
    """{label: value} from the infobox table, or {} if absent."""
    raise NotImplementedError("spec §4.2")


def images(soup: BeautifulSoup, article_path: str, min_px: int = 200) -> list[dict]:
    """Image candidates in reading order: infobox first, then lead figures."""
    raise NotImplementedError("spec §4.2")
