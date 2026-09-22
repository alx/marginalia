"""Grounded drafting and replies via an OpenAI-compatible endpoint (spec §5/§6).

The model sees ONLY the article text this module is handed. Every prompt repeats
that constraint: use only this text, add no facts, invent no links. All HTTP
goes to ``llm.base_url`` (llama.cpp on the tailnet); the endpoint is probed with
``is_online()`` so the caller can skip drafting when it is down.
"""
from __future__ import annotations

import requests

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
