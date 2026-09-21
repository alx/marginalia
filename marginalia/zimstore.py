"""ZimStore + ZimLibrary over libzim (spec §4.1). Stub — see issue marginalia-zimstore."""
from __future__ import annotations

from libzim.reader import Archive
from libzim.search import Query, Searcher


class ZimStore:
    """One topic archive: open, resolve titles, read entries and search."""

    def __init__(self, zim_path: str):
        raise NotImplementedError("spec §4.1")

    def _resolve(self, title: str):
        """Resolve a title to a (redirect-followed) entry, or None."""
        raise NotImplementedError("spec §4.1")

    def html(self, title: str):
        """(path, html) for an article title, or None."""
        raise NotImplementedError("spec §4.1")

    def blob(self, zim_path: str):
        """(bytes, mimetype) for an entry path, or None."""
        raise NotImplementedError("spec §4.1")

    def search(self, query: str, n: int = 10) -> list[str]:
        """Full-text search, returning entry paths."""
        raise NotImplementedError("spec §4.1")


class ZimLibrary:
    """All topic archives. The agent's own topics are tried first."""

    def __init__(self, zim_dir: str):
        raise NotImplementedError("spec §4.1")

    def find(self, title: str, prefer: list[str] | None = None):
        """(topic, (path, html)) for a title, own topics first, or None."""
        raise NotImplementedError("spec §4.1")

    def search(self, query: str, topics: list[str], n: int = 5):
        """Search the given topics, returning (topic, path) hits."""
        raise NotImplementedError("spec §4.1")
