"""Margin-note skill (spec §4.7, all agents): the voice of the feed.

The editor gate rejects drafts that read as a copy of the article instead of a
margin note — the recurring concerns in escalated staging notes are verbatim
lead copying, interpretive leaps the text does not make, source typos carried
over, and endings cut off mid-sentence. This constraint makes the draft aim
at the margin on the first attempt, so the gate has less to catch. It is
prompt-side only: the guards stay the hard floor and the editor still reviews.
"""
from __future__ import annotations

CONSTRAINT = (
    "A margin note, not a summary: pick ONE concrete thing — a scale, number, "
    "mechanism, term origin or disputed point — and open with it, not with a "
    "definition. Do not restate or paraphrase the article's opening paragraph, "
    "and do not walk through the whole article. Every sentence must track "
    "something the article actually says: no rhetorical openers, and no "
    "concluding judgments the text never makes. Write cleanly: never reproduce "
    "the article's typos or grammar errors. End on a complete sentence — be "
    "shorter rather than cut off."
)
