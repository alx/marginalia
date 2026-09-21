"""Pre-publish guards: grounding, numbers, length, safety (spec §5.1). Stub — see issue marginalia-guards."""
from __future__ import annotations

DOSE = None  # dosing-figures regex; defined in the implementation


def ok(draft: str, source: str, agent, limit: int = 320) -> bool:
    """True iff the draft is grounded in `source` and passes the agent's guards."""
    raise NotImplementedError("spec §5.1")
