"""Article HTML -> lead, sections, infobox, images, math, scripts (spec §4.2).

Selectors target recent `mwoffliner` builds (each top section wrapped in
``<section data-mw-section-id="N">``, images keeping a ``resource="./File:…"``
attribute). Tune against your actual archives if the markup differs.
"""
from __future__ import annotations

import posixpath
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

SUB = str.maketrans("0123456789+-−=()", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎")
SUP = str.maketrans("0123456789+-−=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿ")

_JUNK = "sup.mw-ref, style, .mw-editsection, .hatnote, .navbox"


def parse(html: str) -> BeautifulSoup:
    """Parse article HTML, strip junk, convert math->TeX and sub/sup->Unicode."""
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup.select(_JUNK):
        junk.decompose()
    math_to_tex(soup)
    unicode_scripts(soup)
    return soup


def math_to_tex(soup: BeautifulSoup) -> None:
    """Replace rendered maths with ``\\( TeX \\)`` so Misskey can display it."""
    for el in soup.select("span.mwe-math-element"):
        ann = el.find("annotation", attrs={"encoding": "application/x-tex"})
        tex = (ann.get_text() if ann else (el.find("img") or {}).get("alt", "")).strip()
        m = re.match(r"^\{\\(?:displaystyle|textstyle)\s*(.*)\}$", tex, re.S)
        tex = m.group(1) if m else tex
        el.replace_with(f"\\({tex}\\)" if tex else "")


def unicode_scripts(soup: BeautifulSoup) -> None:
    """H<sub>2</sub>O -> H₂O and m<sup>2</sup> -> m². Citation markers already removed."""
    for t in soup.find_all(["sub", "sup"]):
        t.replace_with(t.get_text().translate(SUB if t.name == "sub" else SUP))


def _tight(el) -> str:
    """Text of one block, inline tags kept tight (H<sub>2</sub>O -> H₂O)."""
    return re.sub(r"\s+", " ", el.get_text()).strip()


def lead(soup: BeautifulSoup, max_chars: int = 900) -> str:
    """Lead-section prose, whitespace-normalised, truncated."""
    root = soup.select_one("section[data-mw-section-id='0']") or soup
    paras = [_tight(p) for p in root.find_all("p")
             if "mw-empty-elt" not in (p.get("class") or [])]
    paras = [t for t in paras if t]
    return " ".join(paras)[:max_chars]


def headings(soup: BeautifulSoup) -> list[str]:
    """All h2 headings, in order."""
    return [_tight(h) for h in soup.select("h2")]


def section(soup: BeautifulSoup, heading: str, max_chars: int = 1500) -> str:
    """Text of the h2 section named `heading` (case-insensitive), or ''."""
    for h in soup.select("h2"):
        if h.get_text(strip=True).lower() == heading.lower():
            sec = h.find_parent("section")
            if not sec:
                return ""
            parts = [h.get_text(strip=True)]
            parts += [t for t in (_tight(b) for b in sec.find_all(["p", "li"])) if t]
            return " ".join(parts)[:max_chars]
    return ""


def infobox(soup: BeautifulSoup) -> dict:
    """{label: value} from the infobox table, or {} if absent."""
    out: dict[str, str] = {}
    if box := soup.select_one("table.infobox"):
        for row in box.select("tr"):
            k, v = row.find("th"), row.find("td")
            if k and v:
                out[k.get_text(" ", strip=True)] = v.get_text(" ", strip=True)
    return out


def images(soup: BeautifulSoup, article_path: str, min_px: int = 200) -> list[dict]:
    """Picture candidates in reading order: infobox first, then lead figures."""
    out: list[dict] = []
    for img in soup.select("table.infobox img, figure img"):
        if "mwe-math" in " ".join(img.get("class", [])) or not img.get("src"):
            continue
        try:
            if int(img.get("width", 0)) < min_px:
                continue  # icons, flags, badges
        except ValueError:
            pass
        res = img.get("resource") or (img.find_parent("a") or {}).get("href", "")
        out.append({
            "zim_path": posixpath.normpath(
                posixpath.join(posixpath.dirname(article_path), unquote(img["src"]))
            ),
            "file": unquote(res.split("File:")[-1]) if "File:" in res else None,
            "alt": img.get("alt", ""),
        })
    return out
