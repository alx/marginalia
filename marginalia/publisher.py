"""Misskey.py publishing wrapper (spec §4.5). Stub — see issue marginalia-publisher.

NOTE (spec §11 / issue marginalia-mkcompat): Misskey.py 4.1.0's constructor is
`Misskey(address, i=None, session=None)` — no `ssl` argument. HTTP vs HTTPS is
inferred from the address scheme, so `host` in agents.yaml carries no scheme and
the wrapper must decide how to pass it. Verify against the live server before use.
"""
from __future__ import annotations

import io

from misskey import Misskey
from misskey.exceptions import MisskeyAPIException

EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


class Publisher:
    def __init__(self, host: str, token: str, ssl: bool = False):
        raise NotImplementedError("spec §4.5")

    def upload(self, img: dict, sensitive: bool = False) -> str:
        """Upload image bytes to the drive; return the file id."""
        raise NotImplementedError("spec §4.5")

    def post(self, text: str, reply_id: str | None = None, cw: str | None = None,
             file_ids: list[str] | None = None) -> str:
        """Create a local-only public note; return the note id."""
        raise NotImplementedError("spec §4.5")

    def new_mentions(self, since_id: str | None) -> list[dict]:
        """Mentions newer than since_id (newest first)."""
        raise NotImplementedError("spec §4.5")

    def note(self, note_id: str) -> dict:
        """Fetch a note by id."""
        raise NotImplementedError("spec §4.5")
