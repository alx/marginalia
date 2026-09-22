"""ZIM archive downloader (spec §3).

Reads the Kiwix mirror directory page, keeps the newest build of each wanted
topic/flavour, downloads one file at a time with HTTP Range resume and
verification, and rotates the previous build only after the new one checks out.

First run: ``python fetch_zims.py --dry-run`` prints the plan and downloads
nothing. The full first download is about 17 GB.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

import requests

from marginalia.config import load_config

BASE = "https://dumps.wikimedia.org/other/kiwix/zim/wikipedia/"
HEADERS = {"User-Agent": "marginalia-agents/0.1 (local mirror; contact: you@example.org)"}
NAME = re.compile(
    r"wikipedia_en_(?P<topic>[a-z0-9-]+)_(?P<flavour>maxi|mini|nopic)_(?P<ver>\d{4}-\d{2})\.zim"
)


def newest(wanted: dict[str, str]) -> dict[str, str]:
    """Map wanted {topic: flavour} -> {topic: filename} using the newest YYYY-MM build."""
    page = requests.get(BASE, headers=HEADERS, timeout=60).text
    best: dict[str, tuple[str, str]] = {}
    for m in NAME.finditer(page):
        t = m["topic"]
        if wanted.get(t) == m["flavour"] and (t not in best or m["ver"] > best[t][0]):
            best[t] = (m["ver"], m.group(0))
    missing = set(wanted) - set(best)
    if missing:
        sys.exit(f"Not on the mirror for the requested flavour: {sorted(missing)}")
    return {t: name for t, (_, name) in best.items()}


def remote_size(name: str) -> int:
    """Content-Length of BASE+name, following redirects."""
    r = requests.head(BASE + name, headers=HEADERS, timeout=60, allow_redirects=True)
    r.raise_for_status()
    return int(r.headers["Content-Length"])


def sha256_file(path: Path) -> str:
    """Streaming sha256 of a local file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_sha(name: str) -> str | None:
    """sha256 published next to the file, if the mirror ships one."""
    r = requests.get(BASE + name + ".sha256", headers=HEADERS, timeout=30)
    return r.text.split()[0] if r.ok and r.text.strip() else None


def download(name: str, dest: Path, size: int) -> None:
    """Resumable download of BASE+name into dest/name.part, then atomic rename."""
    part = dest / (name + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have < size:
        hdr = dict(HEADERS, **({"Range": f"bytes={have}-"} if have else {}))
        with requests.get(BASE + name, headers=hdr, stream=True, timeout=60) as r:
            r.raise_for_status()
            mode = "ab" if r.status_code == 206 else "wb"  # 200 means the server ignored Range
            with open(part, mode) as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
    if part.stat().st_size != size:
        sys.exit(f"{name}: size mismatch, re-run to resume")
    want = expected_sha(name)
    if want and sha256_file(part) != want:
        part.unlink()
        sys.exit(f"{name}: checksum mismatch, deleted the partial file")
    part.rename(dest / name)  # atomic swap into place


def main(cfg_path: str = "agents.yaml", dry_run: bool = False) -> None:
    """Fetch/rotate every topic in agents.yaml into zim.dir, updating manifest.json."""
    cfg = load_config(cfg_path)
    dest = Path(cfg["zim"]["dir"])
    manifest_path = dest / "manifest.json"
    manifest = json.load(open(manifest_path)) if manifest_path.exists() else {}
    plan = {
        t: (n, remote_size(n))
        for t, n in newest(cfg["zim"]["topics"]).items()
        if manifest.get(t, {}).get("name") != n
    }  # only what is new
    for t, (n, s) in plan.items():
        print(f"{t:15} {n}  {s / 1e9:6.2f} GB")
    if dry_run or not plan:
        return
    dest.mkdir(parents=True, exist_ok=True)
    need = sum(s for _, s in plan.values()) + max(s for _, s in plan.values())
    free = shutil.disk_usage(dest).free
    if free < need:
        sys.exit(f"Need about {need / 1e9:.1f} GB free, have {free / 1e9:.1f} GB")
    for t, (n, s) in plan.items():  # one connection, one file at a time
        download(n, dest, s)
        old = manifest.get(t, {}).get("name")
        if old and old != n:
            (dest / old).unlink(missing_ok=True)  # free the previous build
        manifest[t] = {"name": n, "size": s, "fetched": time.strftime("%Y-%m-%d")}
        json.dump(manifest, open(manifest_path, "w"), indent=2)


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
