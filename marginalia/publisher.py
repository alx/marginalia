"""Misskey.py publishing wrapper (spec §4.5).

Deviations from the spec example, resolved against Misskey.py 4.1.0 + the live
server (see issue marginalia-mkcompat):

* The exception lives in ``misskey.exceptions``, not the top level.
* ``Misskey.__init__`` is ``(address, i=None, session=None)`` — there is no
  ``ssl`` argument, and ``address`` needs a scheme. We derive the scheme from
  the ``ssl`` flag (``http://`` when False).
* There is no ``notes_mentions`` method. Mentions/replies are read through
  ``i_notifications`` filtered by type; we return the *note* objects so the
  reply loop (``agent.poll``) can climb ``replyId`` and check ``user.isBot``.
"""
from __future__ import annotations

import io

from misskey import Misskey
from misskey.exceptions import MisskeyAPIException

EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}

# Notification types that mean "someone addressed a note to this agent".
_INBOUND = ["mention", "reply"]


def with_scheme(host: str, ssl: bool = False) -> str:
    """Ensure the host has a URL scheme (Misskey.py infers nothing; it needs one)."""
    if "://" in host:
        return host
    return f"{'https' if ssl else 'http'}://{host}"


class Publisher:
    def __init__(self, host: str, token: str, ssl: bool = False):
        self.mk = Misskey(with_scheme(host, ssl), i=token)

    def upload(self, img: dict, sensitive: bool = False) -> str:
        """Upload image bytes to the drive; return the file id.

        The article's alt text is written to the file's comment for
        accessibility (drive_files_create has no comment param, so it is a
        follow-up drive_files_update when alt text is present).
        """
        name = img["name"]
        if not name.lower().endswith(tuple(EXT.values())):
            name += EXT[img["mime"]]
        f = self.mk.drive_files_create(io.BytesIO(img["bytes"]), name=name, is_sensitive=sensitive)
        fid = f["id"]
        alt = img.get("alt")
        if alt:
            self.mk.drive_files_update(fid, comment=alt)
        return fid

    def post(self, text: str, reply_id: str | None = None, cw: str | None = None,
             file_ids: list[str] | None = None) -> str:
        """Create a local-only public note; return the note id."""
        r = self.mk.notes_create(
            text=text, cw=cw, reply_id=reply_id, file_ids=file_ids,
            visibility="public", local_only=True,
        )
        return r["createdNote"]["id"]

    def new_mentions(self, since_id: str | None) -> list[dict]:
        """Notes addressed to this agent (mentions/replies), newest first.

        ``since_id`` is a *note* id (MASTON ids sort by time), used by the
        reply loop as its cursor. We keep only notes newer than it.
        """
        notifs = self.mk.i_notifications(limit=30, include_types=_INBOUND, mark_as_read=False)
        seen: dict[str, dict] = {}
        for n in notifs:
            note = n.get("note") if isinstance(n, dict) else None
            if not note or not note.get("id"):
                continue
            if since_id and note["id"] <= since_id:
                continue
            seen[note["id"]] = note
        return sorted(seen.values(), key=lambda x: x["id"], reverse=True)

    def note(self, note_id: str) -> dict:
        """Fetch a note by id."""
        return self.mk.notes_show(note_id)

    def delete(self, note_id: str) -> None:
        """Delete a note (used to clean up pilot posts)."""
        self.mk.notes_delete(note_id)
