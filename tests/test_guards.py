"""Offline tests for marginalia.guards."""
from types import SimpleNamespace

from marginalia.guards import ok, _nums, DOSE


def test_nums_normalises_commas():
    assert _nums("9,200,000 sq mi and 3.5") == {"9200000", "3.5"}
    assert _nums("no digits here") == set()


def test_nums_ignores_sentence_final_period():
    # 'in 2003.' must not tokenise as '2003.' — the full stop is punctuation
    assert _nums("It happened in 2003.") == {"2003"}
    assert _nums("Released in 1969. Then 1970.") == {"1969", "1970"}


def test_ok_accepts_grounded_draft():
    agent = SimpleNamespace(id="atlas")
    # every number in the draft (9.2) appears verbatim in the source
    assert ok("Covering 9.2 million km².", "It covers 9.2 million square kilometres.", agent)


def test_ok_rejects_invented_number():
    agent = SimpleNamespace(id="atlas")
    assert not ok("It is 999 km wide.", "It is 9.2 million km².", agent)


def test_ok_rejects_over_limit():
    agent = SimpleNamespace(id="atlas")
    assert not ok("x" * 321, "source text", agent)
    assert ok("x" * 320, "source text", agent)  # exactly at the limit is fine


def test_ok_mycelia_rejects_dose():
    assert not ok("Take 500 mg daily.", "A dose of 500 mg.", SimpleNamespace(id="mycelia"))


def test_ok_other_agent_ignores_dose_guard():
    assert ok("Contains 500 mg.", "Contains 500 mg.", SimpleNamespace(id="atlas"))


def test_ok_agent_without_id_is_safe():
    class A:
        pass
    assert ok("Fine text.", "Fine text source.", A())
