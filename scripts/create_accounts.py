#!/usr/bin/env python3
"""Create the 7 marginalia bot accounts on the local Misskey instance.

Steps per bot:
  1. POST /api/signup                       (plain requests — not wrapped by Misskey.py)
  2. POST /api/auth/session/generate        (login -> session token)
  3. POST /api/miauth/gen-token             (long-lived access token for the bot)
  4. Misskey.py i_update (bio, is_bot, avatar) + drive_files_create (generated avatar)

Admin account (MK_USERNAME / MK_PASSWORD from .env) is created first — the first
account registered on a fresh Misskey instance becomes the administrator.

Idempotent: existing usernames are skipped (tokens for those are NOT recreated).

Usage: .venv/bin/python scripts/create_accounts.py [--dry-run]
"""
import io
import json
import os
import secrets
import string
import sys
import time

import requests
from PIL import Image, ImageDraw, ImageFont

API = "http://127.0.0.1:8300/api"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(BASE, ".env")

PERMISSIONS = [
    "read:account",
    "read:notifications",
    "write:notes",
    "write:drive",
    "write:account",
]

# username -> (display name, bio from spec §8, avatar colour)
AGENTS = {
    "atlas":     ("Atlas",     "Places, landscapes and the climate that shapes them.", (56, 142, 60)),
    "quark":     ("Quark",     "Physics and astronomy, from lab benches to the early universe.", (200, 60, 50)),
    "chronicle": ("Chronicle", "Events, empires and objects that changed how we read the past.", (200, 150, 40)),
    "mycelia":   ("Mycelia",   "From molecules to medicine. General information from Wikipedia, not medical advice.", (30, 140, 130)),
    "cipher":    ("Cipher",    "Theorems, constants and the ideas behind them.", (40, 90, 200)),
    "palette":   ("Palette",   "Film, filmmakers and how movies look.", (200, 90, 170)),
    "lexis":     ("Lexis",     "The words and ideas people use to study society.", (130, 80, 200)),
}

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]


def load_env() -> dict:
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def save_env(env: dict) -> None:
    with open(ENV_FILE, "w") as f:
        f.write("# Misskey credentials & tokens (managed by scripts/create_accounts.py)\n")
        for k in sorted(env):
            f.write(f"{k}={env[k]}\n")
    os.chmod(ENV_FILE, 0o600)


def api(path: str, body: dict, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(f"{API}/{path}", json=body, headers=headers, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"POST /{path} -> {r.status_code}: {r.text[:300]}")
    try:
        return r.json() if r.text else {}
    except json.JSONDecodeError:
        return {}


def username_exists(username: str) -> bool:
    r = requests.post(f"{API}/users/show", json={"username": username}, timeout=15)
    return r.status_code == 200


def token_is_valid(token: str) -> bool:
    r = requests.post(f"{API}/i", json={},
                      headers={"Authorization": f"Bearer {token}"}, timeout=15)
    return r.status_code == 200


def gen_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(24))


def make_avatar(letter: str, color: tuple[int, int, int]) -> io.BytesIO:
    size = 240
    img = Image.new("RGB", (size, size), color)
    d = ImageDraw.Draw(img)
    font = None
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, 140)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), letter, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), letter, fill="white", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def main() -> None:
    dry = "--dry-run" in sys.argv
    env = load_env()

    # 1. admin account (first registrant on a fresh instance becomes admin)
    admin_user, admin_pass = env.get("MK_USERNAME"), env.get("MK_PASSWORD")
    if not admin_user or not admin_pass:
        sys.exit("MK_USERNAME / MK_PASSWORD missing from .env")
    if dry:
        print(f"[dry] admin account: {admin_user}")
    else:
        if username_exists(admin_user):
            print(f"admin {admin_user}: exists, skipping signup")
        else:
            api("signup", {"username": admin_user, "password": admin_pass,
                           "emailAddress": "", "invitationCode": ""})
            print(f"admin {admin_user}: created (first account -> administrator)")

    from misskey import Misskey

    for username, (display, bio, color) in AGENTS.items():
        if dry:
            print(f"[dry] bot: {username}")
            continue
        try:
            def gen_token(session: str) -> str:
                t = api("miauth/gen-token",
                        {"session": None, "name": f"marginalia-{username}",
                         "description": f"marginalia agent {username}",
                         "permission": PERMISSIONS},
                        token=session)["token"]
                env[f"MK_TOKEN_{username.upper()}"] = t
                return t

            existing = env.get(f"MK_TOKEN_{username.upper()}")
            if existing and token_is_valid(existing):
                token = existing
                print(f"{username}: reusing existing token")
            elif not username_exists(username):
                pw = gen_password()
                api("signup", {"username": username, "password": pw,
                               "emailAddress": "", "invitationCode": ""})
                env[f"BOT_PW_{username.upper()}"] = pw
                print(f"{username}: signed up")
                time.sleep(1.1)  # signin-flow rate-limits to >=1s apart
                token = gen_token(api("signin-flow", {"username": username, "password": pw})["i"])
            elif env.get(f"BOT_PW_{username.upper()}"):
                time.sleep(1.1)  # signin-flow rate-limits to >=1s apart
                pw = env[f"BOT_PW_{username.upper()}"]
                token = gen_token(api("signin-flow", {"username": username, "password": pw})["i"])
            else:
                print(f"{username}: exists, no valid token and no saved password — skipping")
                continue

            # avatar
            mk = Misskey("http://127.0.0.1:8300", i=token)
            buf = make_avatar(display[0], color)
            f = mk.drive_files_create(buf, name=f"{username}-avatar.png")

            # profile: bio + bot flag + avatar
            mk.i_update(name=display, description=bio, is_bot=True,
                        avatar_id=f["id"], is_explorable=False,
                        hide_online_status=True)
            print(f"{username}: token + profile + avatar done")
        except Exception as e:
            print(f"{username}: FAILED — {e}")

    if not dry:
        save_env(env)
        print(f"\n.env updated with {sum(1 for k in env if k.startswith('MK_TOKEN_'))} tokens")


if __name__ == "__main__":
    main()
