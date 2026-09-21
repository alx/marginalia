"""Offline tests for marginalia.images (trust_local path + licence cache)."""
from marginalia.images import first_usable, check
from marginalia.state import State


class FakeStore:
    def __init__(self, blobs):
        self.blobs = blobs  # zim_path -> (bytes, mime) or absent

    def blob(self, p):
        return self.blobs.get(p)


def cands():
    return [
        {"zim_path": "a/Poster.jpg", "file": "Poster.jpg", "alt": "Poster"},
        {"zim_path": "a/icon.png", "file": "icon.png", "alt": "x"},
    ]


def test_first_usable_trust_local():
    store = FakeStore({"a/Poster.jpg": (b"fake", "image/webp"),
                       "a/icon.png": (b"i", "image/png")})
    r = first_usable(cands(), store, None, "trust_local", "Casablanca (film)")
    assert r["bytes"] == b"fake" and r["mime"] == "image/webp"
    assert r["name"] == "Poster"  # stem; Publisher adds the real extension from mime
    assert r["alt"] == "Poster"
    assert r["credit"] == 'Poster.jpg, from the Wikipedia article "Casablanca (film)"'


def test_first_usable_skips_non_image_mime():
    store = FakeStore({"a/Poster.jpg": (b"x", "image/svg+xml")})
    assert first_usable(cands(), store, None, "trust_local", "T") is None


def test_first_usable_none_when_empty():
    assert first_usable([], FakeStore({}), None, "trust_local", "T") is None


def test_first_usable_missing_blob_continues():
    # first candidate has no blob -> falls through to the second
    store = FakeStore({"a/icon.png": (b"i", "image/png")})
    r = first_usable(cands(), store, None, "trust_local", "T")
    assert r is not None and r["name"] == "icon"


def test_check_uses_cache_no_network(tmp_path):
    db = State(str(tmp_path / "s.sqlite"))
    db.set_licence("Poster.jpg", True, "Poster, an artist, CC BY 4.0")
    ok, credit = check("Poster.jpg", db)
    assert ok is True and credit == "Poster, an artist, CC BY 4.0"
