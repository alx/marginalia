"""One-off: repair the three corrupted km conversions on the live 'Earth' note.

This Misskey build has no notes/edit endpoint, so the note is deleted and
re-created with the corrected text (same drive files), and state.sqlite is
pointed at the new note id.

Usage (on lamai270): source .env; python scripts/_fix_earth_note.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml
from marginalia.publisher import Publisher

NOTE_ID = "arfv7bo800zu007m"
# old corrupted fragment -> corrected fragment (whole number now converted)
FIXES = [
    ("152 097 597 km (≈ 371 mi)", "152 097 597 km (≈ 94,509,036 mi)"),
    ("147 098 450 km (≈ 280 mi)", "147 098 450 km (≈ 91,402,711 mi)"),
    ("149 598 023 km (≈ 14.3 mi)", "149 598 023 km (≈ 92,955,873 mi)"),
]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / "agents.yaml").read_text())
    pub = Publisher(cfg["misskey"]["host"], os.environ["MK_TOKEN_ATLAS"],
                    cfg["misskey"].get("ssl", False))

    note = pub.note(NOTE_ID)
    text = note["text"]
    children = pub.mk.notes_children(note_id=NOTE_ID, limit=1)
    if children:
        sys.exit(f"note {NOTE_ID} has replies — refusing to delete it")

    applied = 0
    for old, new in FIXES:
        if old in text:
            text = text.replace(old, new)
            applied += 1
        else:
            print(f"  (not found, already fixed?: {old!r})")
    if applied == 0:
        sys.exit("nothing to fix — aborting, note untouched")

    files = [f["id"] for f in note.get("files") or []]
    pub.delete(NOTE_ID)
    new_id = pub.post(text, file_ids=files)

    # point dedup state at the replacement note so replies still resolve
    import sqlite3
    conn = sqlite3.connect(str(root / "state.sqlite"))
    conn.execute("UPDATE posts SET note_id=? WHERE note_id=?", (new_id, NOTE_ID))
    conn.commit()
    conn.close()
    print(f"reposted with {applied} fixes: {NOTE_ID} -> {new_id}")


if __name__ == "__main__":
    main()
