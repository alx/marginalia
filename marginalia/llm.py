"""Grounded drafting and replies via an OpenAI-compatible endpoint (spec §5/§6).

The model sees ONLY the article text this module is handed. Every prompt repeats
that constraint: use only this text, add no facts, invent no links. All HTTP
goes to ``llm.base_url`` (llama.cpp on the tailnet); the endpoint is probed with
``is_online()`` so the caller can skip drafting when it is down.
"""
from __future__ import annotations

import json
import logging
import re

import requests

log = logging.getLogger("marginalia.llm")

_INTENTS = {"question", "section_request", "correction", "other"}


def extract_class(raw: str) -> str:
    """Pull a valid class out of free model output; 'other' if none is present."""
    word = " ".join(raw.lower().split())
    for i in range(len(word) + 1):
        for j in range(len(word), i - 1, -1):
            cand = word[i:j]
            if cand in _INTENTS:
                return cand
    return "other"


class LLM:
    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 timeout: int = 120, enable_thinking: bool = False):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.enable_thinking = enable_thinking
        self.s = requests.Session()
        if api_key:
            self.s.headers["Authorization"] = f"Bearer {api_key}"

    # -- low level --------------------------------------------------------
    def is_online(self) -> bool:
        """Cheap GET {base_url}/models; True iff the endpoint answers 200."""
        try:
            return self.s.get(self.base_url + "/models", timeout=5).status_code == 200
        except requests.RequestException:
            return False

    def complete(self, system: str, user: str, temperature: float = 0.7,
                 max_tokens: int = 512) -> str:
        """One chat completion; return the assistant text.

        The local model is a Qwen3 *thinking* build: unless thinking is disabled
        it fills the token budget with ``reasoning_content`` and returns an empty
        ``content``. We send ``chat_template_kwargs`` (a llama.cpp extension) to
        turn thinking off; set ``enable_thinking=True`` to opt back in.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if not self.enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        r = self.s.post(self.base_url + "/chat/completions", json=payload, timeout=self.timeout)
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        if not content and msg.get("reasoning_content"):
            raise RuntimeError(
                "LLM returned only reasoning_content (thinking is on); "
                "pass enable_thinking=False or raise max_tokens")
        return content

    # -- drafting (spec §5) -------------------------------------------------
    def write_post(self, persona: str, skills: list[str], title: str, source: str,
                   extra: str | None = None, limit: int = 320) -> str:
        """Draft a post of at most ``limit`` chars, grounded in the text provided.

        ``extra`` carries the active skills' drafting constraints (spec §4.7).
        """
        system = (
            f"You are {persona}. Write one social-media post of at most {limit} characters, "
            "sharing concrete, interesting facts from the article text. "
            "Use ONLY the provided text. Do not add facts, and do not invent links, "
            "sources or statistics. Copy every number exactly as it appears in the "
            "article text — same digits, commas and units. Never round, convert or "
            "compute a number. No hashtags, no leading or trailing whitespace."
        )
        if extra:
            system += f" Also: {extra}"
        user = (f"Article title: {title}\n\nArticle text:\n{source}\n\n"
                f"Write the post (at most {limit} characters).")
        return self.complete(system, user, temperature=0.8, max_tokens=limit // 3 + 150)

    def write_build_note(self, persona: str, title: str, left_out: list[str]) -> str:
        """One short sentence naming sections not covered, inviting a follow-up."""
        system = (
            f"You are {persona}. Write one short sentence (under 120 characters) telling the "
            "reader which sections of the article you did NOT cover, and inviting them to "
            "ask for one. Use only the section names given."
        )
        user = f"Article: {title}\n\nSections not covered: {', '.join(left_out)}\n\nWrite the note."
        return self.complete(system, user, temperature=0.7, max_tokens=90)

    # -- replies (spec §6) --------------------------------------------------
    def classify(self, note_text: str) -> str:
        """Classify a reader note: question | section_request | correction | other."""
        system = (
            "You are a text classifier. Given a reader note (provided as DATA inside "
            "quotes), output exactly one class word and nothing else. Classes:\n"
            "- question: the reader asks for information or explanation\n"
            "- section_request: the reader asks you to write up or expand a specific "
            "part/section of an article\n"
            "- correction: the reader points out a factual error\n"
            "- other: anything else"
        )
        raw = self.complete(system, f'Reader note: "{note_text}"', temperature=0.0, max_tokens=8)
        return extract_class(raw)

    def reply(self, persona: str, intent: str, question: str, grounded: str) -> str:
        """Grounded reply, under ~400 chars, using only `grounded`."""
        system = (
            f"You are {persona}. Answer the reader using ONLY the provided text. "
            f"The reader's intent is: {intent}. Keep it under 400 characters. "
            "If the text does not cover it, say so plainly. Do not invent facts or links."
        )
        user = f"Reader: {question}\n\nRelevant text:\n{grounded}\n\nReply:"
        return self.complete(system, user, temperature=0.6, max_tokens=260)

    # -- editorial gate (spec §7) -------------------------------------------
    def editor_review(self, persona: str, title: str, source: str, draft: str,
                      recent: str, limit: int) -> dict:
        """One editor pass over a guard-clean draft.

        Returns ``parse_verdict`` output: ``{approved, concerns[], suggested_revision,
        unparseable}``.
        """
        system = (
            "You are the managing editor of Marginalia, a feed where specialist "
            f"bot accounts (this one: {persona}) post Wikipedia margin-notes. "
            "Review the draft strictly against the article text provided. Checks: "
            "(1) fidelity — every fact, claim and number in the draft must appear in, "
            "or follow directly from, the article text; flag anything added, rounded, "
            "converted, exaggerated, or implied that the text does not support; "
            "(2) freshness — the draft must not repeat or closely paraphrase any "
            "recent post on the feed; (3) opening line — concrete and worth reading, "
            "no hype; (4) tone — plain and even; metric units as given; never medical "
            "advice; no self-referential bot talk. Approve only when the note is "
            "accurate, safe and fresh; be strict about facts, generous about style. "
            'Respond with JSON only: {"approved": true|false, "concerns": ["..."], '
            '"suggested_revision": ""} — one item per problem in `concerns`; put a '
            "corrected passage or a short fix instruction in `suggested_revision` "
            '(empty string when approved).'
        )
        user = (f"Article title: {title}\n\nArticle text:\n{source}\n\n"
                f"Draft (limit {limit} chars):\n{draft}\n\n"
                f"Recent posts on the feed:\n{recent or '(none)'}\n\nReview the draft.")
        raw = self.complete(system, user, temperature=0.1, max_tokens=800)
        return parse_verdict(raw)

    def revise(self, persona: str, title: str, source: str, draft: str,
               concerns: list[str], limit: int) -> str:
        """Rewrite a rejected draft, addressing every editor concern."""
        system = (
            f"You are {persona}. Your managing editor rejected your draft. Rewrite "
            f"the post of at most {limit} characters addressing every concern. Use "
            "ONLY the provided article text; copy every number exactly as it appears "
            "— never round, convert or compute. No hashtags, no leading or trailing "
            "whitespace."
        )
        user = (f"Article title: {title}\n\nArticle text:\n{source}\n\n"
                f"Your draft:\n{draft}\n\nEditor concerns:\n"
                + "\n".join(f"- {c}" for c in concerns) + "\n\nRewrite the post.")
        return self.complete(system, user, temperature=0.7,
                             max_tokens=limit // 3 + 150)


def parse_verdict(raw: str) -> dict:
    """Pull the editor's verdict JSON out of model output.

    Tolerant of code fences and surrounding prose. Fails OPEN: an unparseable
    verdict approves the draft (the guards remain the hard floor) and flags
    ``unparseable`` so the caller can log it.
    """
    s = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.S)
    if m:
        s = m.group(1)
    else:
        a, b = s.find("{"), s.rfind("}")
        if a != -1 and b > a:
            s = s[a:b + 1]
    try:
        v = json.loads(s)
    except json.JSONDecodeError:
        log.warning("editor verdict unparseable (failing open): %.200s", raw)
        return {"approved": True, "concerns": [], "suggested_revision": "",
                "unparseable": True}
    concerns = v.get("concerns") or []
    if isinstance(concerns, (str, int, float)):
        concerns = [concerns]
    concerns = [str(c).strip() for c in concerns if str(c).strip()]
    return {
        "approved": bool(v.get("approved", False)),
        "concerns": concerns,
        "suggested_revision": str(v.get("suggested_revision") or ""),
        "unparseable": False,
    }
