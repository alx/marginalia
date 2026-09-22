"""Delete notes by id as the admin (reader) account. Usage:
    .venv/bin/python scripts/_cleanup.py <note_id> [more...]
"""
import sys
sys.path.insert(0, ".")
import requests

API = "http://127.0.0.1:8300/api"
env = {}
for line in open(".env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

r = requests.post(f"{API}/signin-flow",
                  json={"username": env["MK_USERNAME"], "password": env["MK_PASSWORD"]},
                  timeout=30).json()
tok = r.get("i") or r.get("token")
for nid in sys.argv[1:]:
    d = requests.post(f"{API}/notes/delete", json={"noteId": nid},
                      headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    print(nid, d.status_code)
