"""One-off: repair the three corrupted km conversions on the live 'Earth' note
(arfv7bo800zu007m) written before the units space-grouping fix.

Usage (on lamai270): source .env; python scripts/_fix_earth_note.py
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from marginalia.publisher import with_scheme

NOTE_ID = "arfv7bo800zu007m"
# old corrupted fragment -> corrected fragment (whole number now converted)
FIXES = [
    ("152 097 597 km (≈ 371 mi)", "152 097 597 km (≈ 94,509,036 mi)"),
    ("147 098 450 km (≈ 280 mi)", "147 098 450 km (≈ 91,402,711 mi)"),
    ("149 598 023 km (≈ 14.3 mi)", "149 598 023 km (≈ 92,955,873 mi)"),
]


def call(base: str, token: str, path: str, payload: dict):
    req = urllib.request.Request(
        base + "/api/" + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main() -> None:
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "agents.yaml").read_text())
    base = with_scheme(cfg["misskey"]["host"], ssl=cfg["misskey"].get("ssl", False))
    token = os.environ["MK_TOKEN_ATLAS"]
    cur = call(base, token, "notes/show", {"noteId": NOTE_ID})["text"]

    for old, new in FIXES:
        if old in cur:
            cur = cur.replace(old, new)
        else:
            print(f"  (already fixed / not found: {old!r})")

    call(base, token, "notes/edit", {"noteId": NOTE_ID, "text": cur})
    fresh = call(base, token, "notes/show", {"noteId": NOTE_ID})["text"]
    for _, new in FIXES:
        assert new in fresh, new
    print("Earth note repaired.")


if __name__ == "__main__":
    main()
