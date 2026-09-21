"""ZIM archive access: ZimStore (one archive) + ZimLibrary (a directory of them).

Spec §4.1. Built on the `libzim` Python bindings (3.13). Handles both the old
and new Kiwix namespace schemes for article paths, and redirects.
"""
from __future__ import annotations

from pathlib import Path

from libzim.reader import Archive
from libzim.search import Query, Searcher


class ZimStore:
    """One open ZIM archive with typed helpers for HTML, blobs, and search."""

    def __init__(self, zim_path: str):
        self.zim = Archive(zim_path)
        self.book = self.zim.get_metadata("Name").decode()      # id in kiwix-serve URLs
        self.date = self.zim.get_metadata("Date").decode()      # ZIM build date

    def _resolve(self, title: str):
        """Resolve a page title to a final (non-redirect) entry, or None."""
        path = title.replace(" ", "_")
        for candidate in (path, "A/" + path):                   # new + old namespace schemes
            if self.zim.has_entry_by_path(candidate):
                e = self.zim.get_entry_by_path(candidate)
                while e.is_redirect:
                    e = e.get_redirect_entry()
                return e
        return None

    def html(self, title: str):
        """(entry_path, html) for `title`, or None if the page is absent."""
        e = self._resolve(title)
        return (e.path, bytes(e.get_item().content).decode("utf-8")) if e else None

    def blob(self, zim_path: str):
        """(bytes, mimetype) for an entry path, or None if absent."""
        if not self.zim.has_entry_by_path(zim_path):
            return None
        item = self.zim.get_entry_by_path(zim_path).get_item()
        return bytes(item.content), item.mimetype

    def search(self, query: str, n: int = 10) -> list[str]:
        """Top-`n` entry paths for a full-text query."""
        result = Searcher(self.zim).search(Query().set_query(query))
        return list(result.getResults(0, n))


class ZimLibrary:
    """All topic archives in one place. The agent's own topics are tried first."""

    def __init__(self, zim_dir: str):
        self.stores: dict[str, ZimStore] = {}
        for p in sorted(Path(zim_dir).glob("wikipedia_en_*.zim")):
            topic = p.name.split("_")[2]   # wikipedia_en_<topic>_<flavour>_<ver>.zim
            self.stores[topic] = ZimStore(str(p))

    def find(self, title: str, prefer: list[str] | None = None):
        """Search `title` across archives, `prefer` topics first.

        Returns (topic, (path, html)) for the first hit, else None.
        """
        order = list(prefer or []) + [t for t in self.stores if t not in (prefer or [])]
        for t in order:
            if t in self.stores and (hit := self.stores[t].html(title)):
                return t, hit
        return None

    def search(self, query: str, topics: list[str], n: int = 5):
        """(topic, path) hits for a query restricted to `topics`."""
        return [(t, p) for t in topics if t in self.stores
                for p in self.stores[t].search(query, n)]
