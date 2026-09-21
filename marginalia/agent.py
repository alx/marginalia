"""Agent object + posting loop (spec §5) and reply loop (spec §6).

``tick()`` is the posting side: pick a candidate article, extract its lead,
draft a grounded post, attach an image, publish it, and leave a build note as
the agent's own reply. ``poll()`` is the reply side (issue marginalia-poll).
"""
from __future__ import annotations

import posixpath
import random

from marginalia import extract, guards, images


# Boilerplate trailing sections we never offer as a build-note follow-up.
USED_HEADINGS = {
    "references", "reference", "see also", "further reading", "bibliography",
    "external links", "external link", "sources", "source", "notes", "citations",
    "footnotes", "works cited", "additional resources", "citations needed",
}

MAX_LINKS_PER_SEED = 12   # how many internal links to follow from each seed
MAX_CANDIDATES = 40       # cap on how many articles we fully score per tick

# Per-agent voices (spec §8) — the persona handed to the local model.
PERSONAS = {
    "atlas": "Atlas, a geography and climate account. Measured and concrete; uses scale and comparison.",
    "quark": "Quark, a physics and astronomy account. Precise and curious; orders of magnitude over adjectives, no hype.",
    "chronicle": "Chronicle, a history account. Careful with dates; flags disputed claims plainly.",
    "mycelia": "Mycelia, a medicine and chemistry account. Warm and precise; general information, never medical advice.",
    "cipher": "Cipher, a mathematics account. Terse; states the claim first, then the intuition.",
    "palette": "Palette, a film account. Visual; describes form, craft and technique, and credits the maker.",
    "lexis": "Lexis, a sociology account. Plain and even-handed; explains a term, then where it came from.",
}


class Agent:
    """One bot: its agents.yaml block plus the shared services it posts with."""

    def __init__(self, name, cfg, db, lib, llm, pub):
        a = cfg["agents"][name]
        self.id = name
        self.topics = a["topics"]
        self.hashtags = a["hashtags"]
        self.seeds = a.get("seeds", [])
        self.skills = a.get("skills", [])
        self.posts_per_day = a.get("posts_per_day", 1)
        self.sensitive_images = a.get("sensitive_images", False)
        self.daily_date_article = a.get("daily_date_article", False)
        self.persona = PERSONAS.get(name, f"{name}, a Wikipedia margin-notes account")
        self.cfg = cfg
        self.db = db
        self.lib = lib
        self.llm = llm
        self.pub = pub

    def cw_for(self, soup):
        """Content warning for this article, or None (Palette: spoilers)."""
        return None


# -- small helpers --------------------------------------------------------
def path_title(path: str) -> str:
    """``Outline_of_geography`` -> ``Outline of geography``."""
    return posixpath.basename(path).replace("_", " ")


def wiki_url(topic: str, path: str) -> str:
    """Reader link for the full article (online default; kiwix-serve when set)."""
    return f"https://en.wikipedia.org/wiki/{posixpath.basename(path)}"


def _internal_link_paths(soup) -> list[str]:
    """Flat article paths linked from a page (skips external, asset, file links)."""
    seen: set[str] = set()
    out: list[str] = []
    for a in soup.select("a[href]"):
        h = a.get("href")
        if not h:
            continue
        if h.startswith(("http://", "https://", "#", "/", "./", "../")):
            continue
        if "_assets_" in h or h.startswith("File:") or " " in h:
            continue
        h = h.split("#", 1)[0]
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


# -- candidate funnel (spec §4.3) -----------------------------------------
def pick_candidate(agent):
    """seeds -> expand -> filter -> score -> pick. Returns (topic, path) or None."""
    db, lib = agent.db, agent.lib
    pool: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(topic, path):
        if path and (topic, path) not in seen:
            seen.add((topic, path))
            pool.append((topic, path))

    for seed in agent.seeds:
        hit = lib.find(seed, prefer=agent.topics)
        if not hit:
            continue
        topic, (spath, shtml) = hit
        add(topic, spath)                                   # the seed itself
        for link in _internal_link_paths(extract.parse(shtml))[:MAX_LINKS_PER_SEED]:
            add(topic, link)
        if len(pool) >= MAX_CANDIDATES * 2:
            break

    scored: list[tuple[int, str, str]] = []
    for topic, path in pool[:MAX_CANDIDATES]:
        got = lib.stores[topic].html(path)
        if not got:
            continue
        epath, html = got
        if db.seen(agent.id, epath):                        # canonical path is what's stored
            continue
        soup = extract.parse(html)
        lead = extract.lead(soup)
        if len(lead) < 300 or "may refer to" in lead.lower():
            continue
        heads = extract.headings(soup)
        score = (2 if extract.infobox(soup) else 0) + min(len(heads), 6) \
            + (1 if extract.images(soup, epath) else 0)
        scored.append((score, topic, epath))

    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    _, topic, epath = random.choice(scored[:5])
    return topic, epath


# -- posting loop (spec §5) -------------------------------------------------
def tick(agent) -> str | None:
    """One posting iteration. Returns the note id, or None if nothing posted."""
    db, lib, llm, pub, cfg = agent.db, agent.lib, agent.llm, agent.pub, agent.cfg

    picked = pick_candidate(agent)
    if not picked:
        return None
    topic, path = picked
    store = lib.stores[topic]
    got = store.html(path)
    if not got:
        return None
    _, html = got
    soup = extract.parse(html)
    lead_text = extract.lead(soup)
    heads = extract.headings(soup)
    title = path_title(path)

    limit = cfg["defaults"]["max_post_chars"]
    draft = llm.write_post(agent.persona, agent.skills, title=title, source=lead_text)
    if not guards.ok(draft, lead_text, agent, limit):       # grounding / length / safety
        draft = llm.write_post(agent.persona, agent.skills, title=title, source=lead_text)
        if not guards.ok(draft, lead_text, agent, limit):
            return None

    pic = None
    if cfg["images"]["mode"] != "none":
        pic = images.first_usable(extract.images(soup, path), store, db,
                                  cfg["images"]["mode"], title)

    text = f"{draft}\n\n[Full article]({wiki_url(topic, path)})  {agent.hashtags}"
    if pic:
        text += f"\nImage: {pic['credit']}"
    text += "\nText from Wikipedia, CC BY-SA 4.0"

    cw = agent.cw_for(soup)
    file_ids = [pub.upload(pic, sensitive=agent.sensitive_images)] if pic else None
    note_id = pub.post(text, cw=cw, file_ids=file_ids)

    unused = [h for h in heads if h.lower() not in USED_HEADINGS]
    build = llm.write_build_note(agent.persona, title=title, left_out=unused[:4])
    build_id = pub.post(build, reply_id=note_id)

    db.save_post(agent.id, topic, path, note_id, build_id,
                 pic and pic["name"], store.book, store.date, title=title)
    return note_id


# -- reply loop (spec §6) — issue marginalia-poll --------------------------
def poll(agent) -> None:
    """Fetch new mentions, climb to root, ground, answer."""
    raise NotImplementedError("spec §6 — see issue marginalia-poll")
