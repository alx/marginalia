"""Pilot (spec §12.5): Atlas replies. A reader answers one of Atlas's posts and
Atlas polls and answers in-thread, grounded in the archive. Run on lamai270:

    .venv/bin/python scripts/_atlas_replies.py [atlas_note_id] [reader_question]

Defaults: the Antarctica pilot note, asking Atlas to expand the Climate section.
"""
import sys
import time
sys.path.insert(0, ".")
import requests
import yaml
from marginalia.state import State
from marginalia.zimstore import ZimLibrary
from marginalia.llm import LLM
from marginalia.publisher import Publisher
from marginalia.agent import Agent, poll

cfg = yaml.safe_load(open("agents.yaml"))
mk, llmc = cfg["misskey"], cfg["llm"]
API = "http://" + mk["host"] + "/api"

env = {}
for line in open(".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

atlas_note = sys.argv[1] if len(sys.argv) > 1 else "arek4kj300zu002e"   # Antarctica
question = sys.argv[2] if len(sys.argv) > 2 else \
    "Can you tell me more about the Climate section?"


def reader_token() -> str:
    """Sign the reader (admin) in and return a bearer token."""
    body = {"username": env["MK_USERNAME"], "password": env["MK_PASSWORD"]}
    last = None
    for path in ("auth/signin", "signin-flow"):
        r = requests.post(f"{API}/{path}", json=body, timeout=30)
        last = r.text
        try:
            d = r.json()
        except ValueError:
            continue
        tok = d.get("i") or d.get("token")
        if tok:
            return tok
    sys.exit("reader signin failed: " + str(last))


rtok = reader_token()
resp = requests.post(f"{API}/notes/create",
                     json={"text": question, "replyId": atlas_note},
                     headers={"Authorization": f"Bearer {rtok}"}, timeout=30)
body = resp.json()
mid = (body.get("createdNote") or body).get("id")
print(f"reader replied {mid} to {atlas_note}: {question!r}")

# reply notifications have ~1s eventual consistency
for wait in (2.0, 3.0, 3.0):
    time.sleep(wait)
    db = State("state.sqlite")
    lib = ZimLibrary(cfg["zim"]["dir"])
    llm = LLM(llmc["base_url"], llmc["model"])
    pub = Publisher(mk["host"], env["MK_TOKEN_ATLAS"], mk.get("ssl", False))
    agent = Agent("atlas", cfg, db, lib, llm, pub)
    if not llm.is_online():
        sys.exit("LLM offline — aborting")
    n = poll(agent)
    print(f"[after {wait:.0f}s wait] atlas answered {n} mention(s)")
    row = db.conn.execute(
        "SELECT reply_note_id FROM replies WHERE incoming_note_id=?", (mid,)).fetchone()
    if row:
        rnote = pub.note(row["reply_note_id"])
        print("\n--- Atlas reply (" + row["reply_note_id"] + ") ---")
        print(rnote.get("text"))
        print("PILOT_OK reader_note=" + mid + " reply_note=" + row["reply_note_id"])
        sys.exit(0)
    db.close()
sys.exit("atlas did not answer the reader note within the retries")
