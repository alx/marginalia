"""Pilot (spec §12.4): wire Atlas end to end and publish a real post.

Run on lamai270 (where the ZIMs and the local LLM are reachable):
    .venv/bin/python scripts/_atlas_e2e.py [n]      # n = number of ticks (default 1)

For each tick: pick a candidate from Atlas's seeds, extract the lead, draft a
grounded post via the local LLM, attach an image, publish the note + the
agent's own build-note reply, and record state. Prints everything for review.
"""
import sys
sys.path.insert(0, ".")
import yaml
from marginalia.zimstore import ZimLibrary
from marginalia.state import State
from marginalia.llm import LLM
from marginalia.publisher import Publisher
from marginalia.agent import Agent, tick

cfg = yaml.safe_load(open("agents.yaml"))
mk, llmc = cfg["misskey"], cfg["llm"]

env = {}
for line in open(".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
token = env["MK_TOKEN_ATLAS"]

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1

db = State("state.sqlite")
lib = ZimLibrary(cfg["zim"]["dir"])
llm = LLM(llmc["base_url"], llmc["model"])
pub = Publisher(mk["host"], token, mk.get("ssl", False))
agent = Agent("atlas", cfg, db, lib, llm, pub)

if not llm.is_online():
    sys.exit("LLM offline at " + llmc["base_url"] + " — aborting, nothing posted")
print("LLM online. Running", n, "tick(s) as @atlas ...\n")

for i in range(n):
    note_id = tick(agent)
    if not note_id:
        print(f"[tick {i+1}] skipped (no usable candidate or guard failed)")
        continue
    note = pub.note(note_id)
    files = note.get("files", [])
    row = db.post_by_note(note_id)
    print(f"--- tick {i+1}: {row['title']} ({row['topic']}/{row['path']}) ---")
    print(f"note {note_id} ({len(note.get('text',''))} chars)")
    print(note.get("text"))
    print("attached :", [(f["name"], f["type"], f["size"]) for f in files])
    if row and row.get("build_note_id"):
        build = pub.note(row["build_note_id"])
        print(f"  ↳ build note {row['build_note_id']}: {build.get('text')}")
    print("\n")

print("done.")
