"""Tests for agent.py: the candidate funnel (spec §4.3) and tick (spec §5).

The real extract/llm-guard code runs; only the ZIM library, db, LLM and
publisher are faked so the whole posting flow is exercised offline.
"""
from __future__ import annotations

import pytest

from marginalia import extract
from marginalia.agent import (Agent, _internal_link_paths, answer, climb_to_root,
                              path_title, pick_candidate, poll, tick, wiki_url)

LEAD = (
    "The Sahara covers about 9.2 million square kilometres, making it the largest "
    "hot desert in the world and a defining feature of North Africa. Its climate "
    "is hyperarid, with very little rainfall and intense evaporation, which shapes "
    "the sparse vegetation and the patterns of human settlement there today."
)
assert len(LEAD) >= 300

CFG = {
    "images": {"mode": "none"},
    "defaults": {"max_post_chars": 320},
    "agents": {
        "atlas": {
            "topics": ["geography"], "hashtags": "#geography",
            "seeds": ["List of things"], "skills": [], "posts_per_day": 1,
        }
    },
}


# -- fakes ----------------------------------------------------------------
def _article(lead, heads, infobox=True):
    # realistic mwoffliner shape: lead in section 0, each h2 in its own section
    h = ('<html><body><div id="content">'
         f'<section data-mw-section-id="0"><p>{lead}</p>')
    if infobox:
        h += '<table class="infobox"><tbody><tr><td>x</td></tr></tbody></table>'
    h += '</section>'
    for i, x in enumerate(heads, start=1):
        h += (f'<section data-mw-section-id="{i}">'
              f'<h2>{x}</h2><p>body of {x}</p></section>')
    return h + '</div></body></html>'


def _seed(links):
    cells = " ".join(f'<a href="{l}">{l}</a>' for l in links)
    return f'<html><body><div id="content"><p>A list.</p><p>{cells}</p></div></body></html>'


class FakeStore:
    def __init__(self):
        self.book, self.date = "wikipedia_en_geography_maxi", "2026-07"
        self.articles: dict[str, str] = {}
        self.blobs: dict[str, tuple[bytes, str]] = {}

    def html(self, title):
        path = title.replace(" ", "_")
        if path in self.articles:
            return path, self.articles[path]
        return None

    def blob(self, zim_path):
        return self.blobs.get(zim_path)


class FakeLib:
    def __init__(self, stores):
        self.stores = stores

    def find(self, title, prefer=None):
        order = (prefer or []) + [t for t in self.stores if t not in (prefer or [])]
        for t in order:
            if t in self.stores and self.stores[t].html(title):
                return t, self.stores[t].html(title)
        return None

    def search(self, q, topics, n=5):
        return []


class FakeDB:
    def __init__(self):
        self.seen_paths: set[tuple[str, str]] = set()
        self.saved = []
        self.posts_by_note: dict[str, dict] = {}
        self.cursors: dict[tuple[str, str], str] = {}
        self.replies: set[str] = set()

    def seen(self, agent, path):
        return (agent, path) in self.seen_paths

    def save_post(self, agent, topic, path, note_id, build_note_id, image_file,
                  zim_book, zim_date, title=None):
        self.seen_paths.add((agent, path))
        self.saved.append((agent, topic, path, note_id, build_note_id, image_file))
        self.posts_by_note[note_id] = {"agent": agent, "topic": topic, "path": path,
                                       "title": title}

    def post_by_note(self, note_id):
        return self.posts_by_note.get(note_id)

    def get_cursor(self, agent, key, default=None):
        return self.cursors.get((agent, key), default)

    def set_cursor(self, agent, key, value):
        self.cursors[(agent, key)] = str(value)

    def replied(self, note_id):
        return note_id in self.replies

    def save_reply(self, incoming, reply_id, agent):
        self.replies.add(incoming)


class FakeLLM:
    def __init__(self):
        self.draft = "The Sahara is vast and dry."      # no numbers -> guard passes
        self.calls = 0
        self.online = True
        self.classify_result = "question"
        self.last_ground = None

    def is_online(self):
        return self.online

    def classify(self, text):
        return self.classify_result

    def reply(self, persona, intent, question, grounded):
        self.last_ground = grounded
        return f"reply({intent}) :: {grounded[:30]}"

    def write_post(self, persona, skills, title, source):
        self.calls += 1
        return self.draft

    def write_build_note(self, persona, title, left_out):
        return "Left out " + ", ".join(left_out) + "."


class FakePub:
    def __init__(self):
        self.posts = []
        self.files = []
        self.notes: dict[str, dict] = {}
        self.mentions: list[dict] = []

    def post(self, text, reply_id=None, file_ids=None, cw=None):
        self.posts.append((text, reply_id, file_ids, cw))
        return f"note{len(self.posts)}"

    def upload(self, img, sensitive=False):
        self.files.append(img["name"])
        return f"file{len(self.files)}"

    def note(self, note_id):
        return self.notes[note_id]

    def new_mentions(self, since=None):
        return [m for m in self.mentions if not since or m["id"] > since]


def _agent(store, db, llm, pub):
    lib = FakeLib({"geography": store})
    return Agent("atlas", CFG, db, lib, llm, pub)


# -- pure helpers ---------------------------------------------------------
def test_path_title():
    assert path_title("Outline_of_geography") == "Outline of geography"
    assert path_title("Sahara") == "Sahara"
    assert path_title("A/Sahara") == "Sahara"


def test_wiki_url():
    assert wiki_url("geography", "Outline_of_geography").endswith(
        "/wiki/Outline_of_geography")
    assert wiki_url("geography", "A/Sahara").endswith("/wiki/Sahara")


def test_internal_link_paths_filtering():
    html = ('<a href="Alpha">A</a><a href="Alpha">A again</a>'
            '<a href="https://x.y/z">ext</a><a href="#top">frag</a>'
            '<a href="/abs">abs</a><a href="./_assets_/h/a.jpg">img</a>'
            '<a href="File:pic.jpg">file</a><a href="Beta">B</a>')
    paths = _internal_link_paths(extract.parse(html))
    assert "Alpha" in paths and "Beta" in paths
    assert paths.count("Alpha") == 1          # deduped
    assert not any("http" in p or p.startswith(("#", "/", ".")) for p in paths)
    assert not any("_assets_" in p or p.startswith("File:") for p in paths)


# -- pick_candidate (spec §4.3) -------------------------------------------
def _store_two_articles():
    store = FakeStore()
    store.articles = {
        "List_of_things": _seed(["Alpha", "Beta"]),
        "Alpha": _article(LEAD, ["One", "Two", "Three"]),
        "Beta": _article(LEAD, ["A", "B"]),
    }
    return store


def test_pick_candidate_returns_unposted_article():
    store, db, pub = _store_two_articles(), FakeDB(), FakePub()
    agent = _agent(store, db, FakeLLM(), pub)
    got = pick_candidate(agent)
    assert got is not None
    topic, path = got
    assert topic == "geography" and path in ("Alpha", "Beta")
    assert path != "List_of_things"           # short-lead list filtered out


def test_pick_candidate_skips_seen():
    store, db, pub = _store_two_articles(), FakeDB(), FakePub()
    db.seen_paths.add(("atlas", "Alpha"))
    agent = _agent(store, db, FakeLLM(), pub)
    assert pick_candidate(agent) == ("geography", "Beta")


def test_pick_candidate_returns_none_when_all_seen():
    store, db, pub = _store_two_articles(), FakeDB(), FakePub()
    db.seen_paths |= {("atlas", "Alpha"), ("atlas", "Beta")}
    agent = _agent(store, db, FakeLLM(), pub)
    assert pick_candidate(agent) is None


# -- tick (spec §5) --------------------------------------------------------
def _store_one_article():
    store = FakeStore()
    store.articles = {
        "List_of_things": _seed(["Alpha"]),
        "Alpha": _article(LEAD, ["One", "Two", "Three", "Four", "Five", "Six", "Seven"]),
    }
    return store


def test_tick_posts_note_and_build_note():
    store, db, pub = _store_one_article(), FakeDB(), FakePub()
    agent = _agent(store, db, FakeLLM(), pub)
    note_id = tick(agent)
    assert note_id is not None
    # two posts: the note, then the agent's own build-note reply
    assert len(pub.posts) == 2
    note_text, note_reply, note_files, note_cw = pub.posts[0]
    assert note_reply is None and note_files is None
    assert "[Full article](https://en.wikipedia.org/wiki/Alpha)" in note_text
    assert "#geography" in note_text
    assert note_text.endswith("Text from Wikipedia, CC BY-SA 4.0")
    build_text, build_reply, *_ = pub.posts[1]
    assert build_reply == note_id            # build note replies to the post
    assert "Left out One, Two, Three, Four." in build_text
    assert len(db.saved) == 1
    assert db.saved[0][0] == "atlas" and db.saved[0][2] == "Alpha"


def test_tick_skips_when_guard_fails():
    store, db, pub = _store_one_article(), FakeDB(), FakePub()
    llm = FakeLLM()
    llm.draft = "It sits 999 metres above sea level."   # 999 not in the lead
    agent = _agent(store, db, llm, pub)
    assert tick(agent) is None
    assert pub.posts == []                    # nothing published
    assert llm.calls == 2                     # drafted, retried once, gave up


# -- reply loop (spec §6) ---------------------------------------------------
def _recorded_agent():
    store = _store_one_article()             # has article "Alpha"
    db, pub = FakeDB(), FakePub()
    pub.notes["N1"] = {"id": "N1", "replyId": None}
    db.save_post("atlas", "geography", "Alpha", "N1", "B1", None,
                 store.book, store.date, title="Alpha")
    agent = _agent(store, db, FakeLLM(), pub)
    return agent, db, pub


def test_climb_to_root():
    pub = FakePub()
    pub.notes["A"] = {"id": "A", "replyId": None}
    pub.notes["B"] = {"id": "B", "replyId": "A"}
    pub.notes["C"] = {"id": "C", "replyId": "B"}
    root = climb_to_root({"id": "D", "replyId": "C"}, pub)
    assert root["id"] == "A"


def test_poll_replies_to_question():
    agent, db, pub = _recorded_agent()
    pub.mentions = [{"id": "m1", "text": "Tell me about One",
                     "replyId": "N1", "user": {"isBot": False}}]
    assert poll(agent) == 1
    text, reply_id, _, _ = pub.posts[0]
    assert reply_id == "m1"                  # answered in-thread
    assert "m1" in db.replies
    assert db.get_cursor("atlas", "mention_cursor") == "m1"


def test_poll_skips_bot():
    agent, db, pub = _recorded_agent()
    pub.mentions = [{"id": "m1", "text": "hi", "replyId": "N1",
                     "user": {"isBot": True}}]
    assert poll(agent) == 0 and pub.posts == []


def test_poll_skips_already_replied():
    agent, db, pub = _recorded_agent()
    db.replies.add("m1")
    pub.mentions = [{"id": "m1", "text": "hi", "replyId": "N1",
                     "user": {"isBot": False}}]
    assert poll(agent) == 0 and pub.posts == []


def test_poll_skips_post_we_never_made():
    agent, db, pub = _recorded_agent()
    pub.notes["X1"] = {"id": "X1", "replyId": None}
    pub.mentions = [{"id": "m1", "text": "hi", "replyId": "X1",
                     "user": {"isBot": False}}]
    assert poll(agent) == 0 and pub.posts == []


def test_answer_grounds_named_section():
    agent, db, pub = _recorded_agent()
    agent.llm.classify_result = "section_request"
    post = db.post_by_note("N1")
    n = {"id": "m1", "text": "Tell me about Two", "replyId": "N1", "user": {}}
    reply = answer(agent, post, n)
    assert reply
    assert "body of Two" in agent.llm.last_ground    # the section was pulled in
