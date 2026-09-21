"""Grounded drafting and replies via an OpenAI-compatible endpoint (spec §5/§6).

Stub — see issue marginalia-llm. The model sees only extracted article text;
prompts forbid added facts and invented links. All HTTP goes to llm.base_url
(llama.cpp on the tailnet; used whenever it is online).
"""
from __future__ import annotations


class LLM:
    def __init__(self, base_url: str, model: str):
        raise NotImplementedError("spec §5/§6")

    def is_online(self) -> bool:
        """Cheap probe of GET {base_url}/models (or equivalent)."""
        raise NotImplementedError("spec §5")

    def complete(self, messages: list[dict], **kw) -> str:
        """One chat completion; return the assistant text."""
        raise NotImplementedError("spec §5")

    def write_post(self, persona: str, skills: list[str], title: str, source: str) -> str:
        """Draft a ~320-char post from the lead text only."""
        raise NotImplementedError("spec §5")

    def write_build_note(self, persona: str, title: str, left_out: list[str]) -> str:
        """Build note naming unused sections, inviting a follow-up."""
        raise NotImplementedError("spec §5")

    def classify(self, note_text: str) -> str:
        """'question' | 'section_request' | 'correction' | 'other'."""
        raise NotImplementedError("spec §6")

    def reply(self, persona: str, intent: str, question: str, grounded: str) -> str:
        """Grounded reply, < ~400 chars, using only `grounded`."""
        raise NotImplementedError("spec §6")
