"""Image selection and credit line (spec §4.4).

Posts get a picture when the article has one. Candidates come from
``extract.images()`` (infobox first, then lead figures); bytes come from the
same archive via ``store.blob()``.

Modes (``images.mode`` in agents.yaml):
  trust_local  (default)  attach the first suitable image, no licence lookup
  licence_check          attach only allow-listed Commons licences (needs internet)
  none                   text-only posts

The upload ``name`` is the file stem, *not* the src extension: mwoffliner
serves images transcoded (e.g. a ``.jpg`` src that is really webp), so the real
extension is appended from the blob's mimetype by ``Publisher.upload``.
"""
from __future__ import annotations

import re

import requests

from marginalia.fetch_zims import HEADERS

API = "https://commons.wikimedia.org/w/api.php"
# lower-case prefixes; "cc by" also covers CC BY-SA
ALLOW = ("cc by", "cc0", "public domain", "pd")
MIMES = ("image/jpeg", "image/png", "image/webp", "image/gif")


def check(file_title: str, db):
    """licence_check mode only. Return (ok, credit). Cached so each file is
    looked up once. Offline (no internet) -> (False, None), not cached."""
    row = db.licence(file_title)
    if row:
        return row
    try:
        r = requests.get(API, headers=HEADERS, timeout=20, params={
            "action": "query", "titles": "File:" + file_title, "prop": "imageinfo",
            "iiprop": "extmetadata", "format": "json", "formatversion": 2}).json()
    except requests.RequestException:
        return False, None
    page = r["query"]["pages"][0]
    if page.get("missing") or "imageinfo" not in page:      # not on Commons: assume non-free
        ok, credit = False, None
    else:
        md = page["imageinfo"][0]["extmetadata"]
        lic = md.get("LicenseShortName", {}).get("value", "")
        artist = re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", "")).strip() or "unknown author"
        norm = lic.lower().replace("-", " ")
        ok = norm.startswith(ALLOW) and not re.search(r"\b(nc|nd)\b", norm)
        credit = f"{file_title.rsplit('.', 1)[0]}, {artist}, {lic}"
    db.set_licence(file_title, ok, credit)
    return ok, credit


def _credit_local(c, article_title: str) -> str:
    return f'{c["file"] or "image"}, from the Wikipedia article "{article_title}"'


def first_usable(cands, store, db, mode: str, article_title: str):
    """First attachable image, or None.

    Returns ``{bytes, mime, name, alt, credit}`` where ``name`` is the file stem
    (Publisher adds the real extension from ``mime``).
    """
    for c in cands:
        blob = store.blob(c["zim_path"])
        if not blob or blob[1] not in MIMES:
            continue
        stem = (c["file"] or "image").rsplit(".", 1)[0]
        if mode == "licence_check":
            if not c["file"]:
                continue
            ok, credit = check(c["file"], db)
            if not ok:
                continue
            credit = f"{credit}, via Wikimedia Commons"
        else:                                                 # trust_local (or "none" -> caller skips)
            credit = _credit_local(c, article_title)
        return {"bytes": blob[0], "mime": blob[1], "name": stem, "alt": c["alt"], "credit": credit}
    return None
