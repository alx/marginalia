"""Agent object + posting loop (spec §5) and reply loop (spec §6).

``tick()`` is the posting side: pick a candidate article, extract its lead,
draft a grounded post, attach an image, publish it, and leave a build note as
the agent's own reply. ``poll()`` is the reply side (issue marginalia-poll).
"""
from __future__ import annotations

import posixpath
import random
import re

from marginalia import extract, guards, images, skills
from marginalia.skills import coordinates as sk_coordinates
from marginalia.skills import dates as sk_dates
from marginalia.skills import infobox as sk_infobox
from marginalia.skills import living_person as sk_living_person
from marginalia.skills import safety as sk_safety
from marginalia.skills import spoilers as sk_spoilers
from marginalia.skills import units as sk_units


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
        if skills.has(self.skills, "spoilers"):
            return sk_spoilers.cw_for(soup)
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
def _draft_context(agent, soup) -> tuple[str, str | None]:
    """(source text for the model, drafting constraints) for this article.

    The source is the lead, plus the infobox card when the agent carries the
    infobox skill, so infobox measurements are hooks the number guard accepts.
    Constraints are the skill modules' drafting instructions, joined.
    """
    source = extract.lead(soup)
    extra: list[str] = []
    box = extract.infobox(soup)
    if skills.has(agent.skills, "infobox") and (card := sk_infobox.card(box)):
        source += f"\nFacts: {card}"
    if skills.has(agent.skills, "dates"):
        extra.append(sk_dates.CONSTRAINT)
    if skills.has(agent.skills, "safety"):
        extra.append(sk_safety.CONSTRAINT)
    if skills.has(agent.skills, "spoilers"):
        extra.append(sk_spoilers.CONSTRAINT)
    if skills.has(agent.skills, "living_person") and sk_living_person.is_living(box):
        extra.append(sk_living_person.CONSTRAINT)
    return source, " ".join(extra) or None


def tick(agent) -> str | None:
    """One posting iteration: pick a candidate article, then post it."""
    picked = pick_candidate(agent)
    if not picked:
        return None
    return post_article(agent, *picked)


def post_article(agent, topic: str, path: str) -> str | None:
    """Draft, guard, picture and publish one specific article.

    The build note (spec §5) is folded into the post as a trailing
    conversation hook instead of a self-reply. Returns the note id, or None
    if nothing was posted (guards failed, no article, ...). ``tick`` is
    pick_candidate + this; the scheduler's morning date-article job calls it
    directly with today's date article.
    """
    db, lib, llm, pub, cfg = agent.db, agent.lib, agent.llm, agent.pub, agent.cfg

    store = lib.stores.get(topic)
    if not store or not (got := store.html(path)):
        return None
    _, html = got
    soup = extract.parse(html)
    heads = extract.headings(soup)
    title = path_title(path)

    source, extra = _draft_context(agent, soup)
    limit = cfg["defaults"]["max_post_chars"]
    draft = llm.write_post(agent.persona, agent.skills, title=title, source=source,
                           extra=extra, limit=limit)
    if not guards.ok(draft, source, agent, limit):       # grounding / length / safety
        draft = llm.write_post(agent.persona, agent.skills, title=title, source=source,
                               extra=extra, limit=limit)
        if not guards.ok(draft, source, agent, limit):
            return None

    pic = None
    if cfg["images"]["mode"] != "none":
        pic = images.first_usable(extract.images(soup, path), store, db,
                                  cfg["images"]["mode"], title)

    # conversation hook (the old build note): names the sections not covered
    # and invites a follow-up, folded into the post rather than a self-reply
    unused = [h for h in heads if h.lower() not in USED_HEADINGS]
    hook = ""
    if unused:
        hook = "\n" + llm.write_build_note(agent.persona, title=title, left_out=unused[:4])

    text = f"{draft}{hook}\n\n[Full article]({wiki_url(topic, path)})  {agent.hashtags}"
    if pic:
        text += f"\nImage: {pic['credit']}"
    text += "\nText from Wikipedia, CC BY-SA 4.0"

    # code-side skill augmentations, applied after the guards: converted units
    # and the coordinate line are facts the model is not allowed to invent
    if skills.has(agent.skills, "units"):
        text = sk_units.augment(text)
    if skills.has(agent.skills, "coordinates") and (line := sk_coordinates.from_infobox(extract.infobox(soup))):
        text += f"\n{line}"

    cw = agent.cw_for(soup)
    file_ids = [pub.upload(pic, sensitive=agent.sensitive_images)] if pic else None
    note_id = pub.post(text, cw=cw, file_ids=file_ids)

    db.save_post(agent.id, topic, path, note_id, None,
                 pic and pic["name"], store.book, store.date, title=title)
    return note_id


# -- reply loop (spec §6) -------------------------------------------------
_STOP = set("a an the is are was were be to of in on for with about how what why "
            "when where which do does did this that and or but it its as at by from "
            "into please can could would should just want would like me my you your "
            "some any more most tell me about".split())


def _keywords(text: str) -> str:
    """A short content-word query for the search fallback."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    kws = [w for w in words if w not in _STOP and len(w) > 2]
    return " ".join(dict.fromkeys(kws))[:60]


def _heading_in(heading: str, text: str) -> bool:
    """True if the reader's note is clearly about this section heading."""
    h = heading.lower()
    if h in text.lower():
        return True
    hw = [w for w in re.findall(r"[a-z0-9]+", h) if len(w) > 3]
    q = text.lower()
    return bool(hw) and all(w in q for w in hw)


def _ground(agent, post, note_text: str) -> str:
    """Lead + any sections the note is about; full-text search fallback (spec §6)."""
    lib = agent.lib
    store = lib.stores.get(post["topic"])
    chunks: list[str] = []
    if store:
        got = store.html(post["path"])
        if got:
            soup = extract.parse(got[1])
            if lead := extract.lead(soup):
                chunks.append(lead)
            for h in extract.headings(soup):
                if _heading_in(h, note_text):
                    if sec := extract.section(soup, h):
                        chunks.append(sec)
    if len(chunks) <= 1:   # lead only -> search the agent's topics
        for topic, path in lib.search(_keywords(note_text), agent.topics, 2):
            got = lib.stores[topic].html(path)
            if got and (lead := extract.lead(extract.parse(got[1]))):
                chunks.append(lead)
    return "\n\n".join(chunks)[:4000]


def answer(agent, post, n) -> str:
    """Classify -> ground -> reply (spec §6). Returns the reply text (may be empty)."""
    llm, text = agent.llm, n.get("text", "")
    if not text.strip():
        return ""
    if skills.has(agent.skills, "safety") and sk_safety.needs_refusal(text):
        return sk_safety.refusal(text)                 # personal health / crisis
    intent = llm.classify(text)
    grounded = _ground(agent, post, text)
    reply = llm.reply(agent.persona, intent, text, grounded)
    return (reply or "").strip()[:400]


def climb_to_root(n, pub, max_hops: int = 6):
    """Follow replyId up to `max_hops` to the top of the thread."""
    cur = n
    for _ in range(max_hops):
        rid = cur.get("replyId")
        if not rid:
            return cur
        try:
            cur = pub.note(rid)
        except Exception:                                  # noqa: BLE001 - deleted note
            return cur
    return cur


def poll(agent) -> int:
    """One reply pass: answer new mentions to this agent's posts. Returns count."""
    db, pub, llm = agent.db, agent.pub, agent.llm
    if not llm.is_online():
        return 0
    since = db.get_cursor(agent.id, "mention_cursor")
    answered = 0
    for n in reversed(pub.new_mentions(since)):             # oldest first
        db.set_cursor(agent.id, "mention_cursor", n["id"])
        if (n.get("user") or {}).get("isBot") or db.replied(n["id"]):
            continue                                        # never answer bots / twice
        root = climb_to_root(n, pub)
        post = db.post_by_note(root["id"])
        if not post:
            continue                                        # not one of our posts
        reply = answer(agent, post, n)
        if not reply:
            continue
        rid = pub.post(reply, reply_id=n["id"])
        db.save_reply(n["id"], rid, agent.id)
        answered += 1
    return answered
