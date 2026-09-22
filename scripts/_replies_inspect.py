"""Inspect the Atlas reply pilot result + diagnose the notes/create response."""
import sys
sys.path.insert(0, ".")
import requests, yaml
from marginalia.state import State
from marginalia.publisher import Publisher

cfg = yaml.safe_load(open("agents.yaml"))
mk = cfg["misskey"]
API = "http://" + mk["host"] + "/api"
env = {}
for line in open(".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

db = State("state.sqlite")
rows = [dict(r) for r in db.conn.execute("SELECT * FROM replies").fetchall()]
print("replies rows:", rows)

pub = Publisher(mk["host"], env["MK_TOKEN_ATLAS"], mk.get("ssl", False))
for row in rows:
    inc = pub.note(row["incoming_note_id"])
    rep = pub.note(row["reply_note_id"])
    print("\n--- reader note", row["incoming_note_id"], "---")
    print(inc.get("text"))
    print("--- atlas reply", row["reply_note_id"], "---")
    print(rep.get("text"))

# diagnose the notes/create response shape with a throwaway self-test
body = {"username": env["MK_USERNAME"], "password": env["MK_PASSWORD"]}
s = None
for path in ("auth/signin", "signin-flow"):
    r = requests.post(f"{API}/{path}", json=body, timeout=30)
    try:
        d = r.json()
    except ValueError:
        continue
    if d.get("i") or d.get("token"):
        s = (path, d)
        break
print("\nsignin ok via", s[0], "keys:", list(s[1].keys()))
rtok = s[1].get("i") or s[1].get("token")
c = requests.post(f"{API}/notes/create",
                  json={"text": "(diag) reader create shape test", "replyId": "arek5q8n00zu002j"},
                  headers={"Authorization": f"Bearer {rtok}"}, timeout=30)
print("create status:", c.status_code)
print("create body:", c.text[:400])
db.close()
