"""Pilot publish (spec §12.3): one real bot posts a hard-coded note with a
real ZIM image attached. Proves publisher + drive upload + image attach + note
rendering before any automation runs. Run on lamai270:
    .venv/bin/python scripts/_pilot_pub.py
Leaves the note posted; prints its id for review/cleanup.
"""
import sys
sys.path.insert(0, ".")
import yaml
from marginalia.zimstore import ZimLibrary
from marginalia import extract
from marginalia.publisher import Publisher

cfg = yaml.safe_load(open("agents.yaml"))
mk = cfg["misskey"]

env = {}
for line in open(".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
token = env["MK_TOKEN_ATLAS"]

# 1. pull a real image out of the pilot geography ZIM
lib = ZimLibrary(cfg["zim"]["dir"])
store = lib.stores["geography"]
path, html = store.html("Sahara")
imgs = extract.images(extract.parse(html), path)
img = imgs[0]
data, mime = store.blob(img["zim_path"])
name = img["file"].rsplit(".", 1)[0]  # drop the src extension; real ext comes from mime
print(f"image: {img['file']} -> {name} {mime} ({len(data)} bytes) alt={img['alt']!r}")

# 2. upload + post
pub = Publisher(mk["host"], token, mk.get("ssl", False))
fid = pub.upload({"name": name, "bytes": data, "mime": mime, "alt": img["alt"]})
print("uploaded drive file:", fid)

text = ("The Sahara is the world's largest hot desert, covering roughly 9.2 million "
        "square kilometres across North Africa. Smaller only to the polar deserts by "
        "area, it gets under 250 mm of rain a year — and it has been getting hotter and "
        "drier over the past century. #geography #climate")
assert len(text) <= 320, f"note too long: {len(text)}"
note_id = pub.post(text, file_ids=[fid])
print(f"posted note {note_id} ({len(text)} chars)")

# 3. verify it rendered with the file attached
note = pub.note(note_id)
files = note.get("files", [])
print("note text :", note.get("text"))
print("attached  :", [(f["name"], f["type"], f["size"]) for f in files])
assert files and files[0]["type"].startswith("image/"), "image not attached"
print("PILOT_OK  note_id=" + note_id)
