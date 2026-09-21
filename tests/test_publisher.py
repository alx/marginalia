"""Unit tests for marginalia.publisher (offline parts). Run: .venv/bin/python -m pytest tests/ -q"""
from marginalia.publisher import with_scheme


def test_with_scheme_defaults_to_http():
    assert with_scheme("127.0.0.1:8300") == "http://127.0.0.1:8300"


def test_with_scheme_ssl():
    assert with_scheme("example.org:443", ssl=True) == "https://example.org:443"


def test_with_scheme_keeps_existing():
    assert with_scheme("http://10.0.0.1:8300") == "http://10.0.0.1:8300"
    assert with_scheme("https://mk.example", ssl=False) == "https://mk.example"


def test_ext_map_covers_attachable_mimes():
    from marginalia.publisher import EXT
    assert set(EXT) == {"image/jpeg", "image/png", "image/webp", "image/gif"}
