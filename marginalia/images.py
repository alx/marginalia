"""Image picker, credit line, optional licence check (spec §4.4). Stub — see issue marginalia-images."""
from __future__ import annotations

ALLOW = ("cc by", "cc0", "public domain", "pd")   # lower-case prefixes; CC BY also covers CC BY-SA
MIMES = ("image/jpeg", "image/png", "image/webp", "image/gif")


def check(file_title: str, db):
    """licence_check mode only. Return (ok, credit); cached in SQLite per file."""
    raise NotImplementedError("spec §4.4")


def first_usable(cands, store, db, mode: str, article_title: str):
    """First candidate with attachable bytes + a credit line, or None."""
    raise NotImplementedError("spec §4.4")
