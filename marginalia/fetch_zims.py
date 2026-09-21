"""ZIM archive downloader (spec §3). Stub — see issue marginalia-fetch-zims.

Reads the Kiwix mirror directory page, keeps the newest build of each wanted
topic/flavour, downloads with resume + verification, and rotates old builds.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = "https://dumps.wikimedia.org/other/kiwix/zim/wikipedia/"


def newest(wanted: dict[str, str]) -> dict[str, str]:
    """Map wanted {topic: flavour} -> {topic: filename} using the newest YYYY-MM build."""
    raise NotImplementedError("spec §3")


def remote_size(name: str) -> int:
    """Content-Length of BASE+name, following redirects."""
    raise NotImplementedError("spec §3")


def sha256_file(path: Path) -> str:
    """Streaming sha256 of a local file."""
    raise NotImplementedError("spec §3")


def expected_sha(name: str) -> str | None:
    """sha256 published next to the file, if the mirror ships one."""
    raise NotImplementedError("spec §3")


def download(name: str, dest: Path, size: int) -> None:
    """Resumable download of BASE+name into dest/.part, then atomic rename."""
    raise NotImplementedError("spec §3")


def main(cfg_path: str = "agents.yaml", dry_run: bool = False) -> None:
    """Fetch/rotate every topic in agents.yaml into zim.dir, updating manifest.json."""
    raise NotImplementedError("spec §3")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
