"""Safety skill (spec §4.7, Mycelia): the medical-content guard.

Two hard rules plus one soft one:

* **Posts** (checked in ``guards.ok``): no dosing figures (``guards.DOSE``) and
  no advice phrasing (``ADVICE``) may reach a post.
* **Replies** (checked in ``agent.answer``): personal-health questions get a
  short refusal to advise and a pointer to a clinician — or to emergency
  services when the note reads like a crisis — not an answer.
* The ``CONSTRAINT`` is handed to the model so drafts steer clear on the first
  try; the regexes above are what actually enforce it.
"""
from __future__ import annotations

import re

CONSTRAINT = (
    "General information only. No doses, no diagnosis, no 'you should' advice; "
    "explain, do not instruct."
)

# advice phrasing that must not appear in a post
ADVICE = re.compile(
    r"\b(you should|you can take|take (?:it|this|a dose)|i recommend|you need to take)\b",
    re.I)

# the reader is describing their own (or a named person's) condition/treatment
_PERSONAL = re.compile(
    r"\b(i|me|my) (?:have|had|feel|felt|took|take|taking|got|was|am|been)\b"
    r"|\bmy (?:child|kid|son|daughter|patient|symptoms?|meds|medication|dose)\b"
    r"|\bhow much (?:should|do i)\b|\bis (?:it|this|safe) for me\b", re.I)

_CRISIS = re.compile(
    r"\b(suicid\w*|kill myself|overdose|od\b|can'?t? breathe|chest pain|emergency)\b", re.I)


def needs_refusal(note_text: str) -> bool:
    """True if a reader note about medicine is personal-health or crisis."""
    return bool(_PERSONAL.search(note_text) or _CRISIS.search(note_text))


def refusal(note_text: str) -> str:
    """The refusal reply for a personal-health or crisis note."""
    base = ("I can only share general information, not personal medical advice — "
            "please ask a clinician about that.")
    if _CRISIS.search(note_text):
        base += " If this is urgent, call your local emergency services now."
    return base


def is_crisis(note_text: str) -> bool:
    return bool(_CRISIS.search(note_text))
