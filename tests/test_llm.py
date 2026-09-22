"""Tests for marginalia.llm. extract_class is pure; the live e2e runs only if the
endpoint answers (set MARGINALIA_LIVE=1 to force-include it in a CI without net).
Run: .venv/bin/python -m pytest tests/ -q
"""
import os
import pytest
import requests

from marginalia.llm import LLM, extract_class, parse_verdict

ENDPOINT = "http://llm.internal:8081/v1"
MODEL = "qwen3.8"


# -- offline ---------------------------------------------------------------
def test_extract_class_exact():
    assert extract_class("question") == "question"
    assert extract_class("section_request") == "section_request"


def test_extract_class_embedded():
    # model sometimes wraps its answer; we still pull the class out
    assert extract_class("The class is question.") == "question"
    assert extract_class("correction!") == "correction"


def test_extract_class_defaults_to_other():
    assert extract_class("I don't know") == "other"
    assert extract_class("") == "other"


# -- editorial verdict parsing ---------------------------------------------
def test_parse_verdict_clean_json():
    v = parse_verdict('{"approved": false, "concerns": ["a number"], "suggested_revision": "fix"}')
    assert v == {"approved": False, "concerns": ["a number"],
                "suggested_revision": "fix", "unparseable": False}


def test_parse_verdict_fenced_and_embedded():
    v = parse_verdict('Sure! Here is the review:\n```json\n{"approved": true, "concerns": []}\n```\nDone.')
    assert v["approved"] is True and v["unparseable"] is False


def test_parse_verdict_concerns_string_becomes_list():
    v = parse_verdict('{"approved": false, "concerns": "too long"}')
    assert v["concerns"] == ["too long"]


def test_parse_verdict_missing_approval_defaults_to_reject():
    v = parse_verdict('{"concerns": ["x"]}')
    assert v["approved"] is False


def test_parse_verdict_garbage_fails_open():
    v = parse_verdict("I cannot review this note at all.")
    assert v["approved"] is True and v["unparseable"] is True
    assert v["concerns"] == []


def _live():
    try:
        return requests.get(ENDPOINT + "/models", timeout=4).status_code == 200
    except requests.RequestException:
        return False


@pytest.mark.skipif(
    os.environ.get("MARGINALIA_LIVE") != "1" and not _live(),
    reason="LLM endpoint offline (set MARGINALIA_LIVE=1 to force)",
)
def test_llm_live_roundtrip():
    llm = LLM(ENDPOINT, MODEL)
    assert llm.is_online()
    lead = ("The Sahara is the largest hot desert on Earth, covering about "
            "9.2 million square kilometres across North Africa.")
    post = llm.write_post("Atlas, a geography blogger", ["images"], "Sahara", lead)
    assert 0 < len(post) <= 400
    assert llm.classify("Tell me more about the climate") == "question"
    reply = llm.reply("Atlas", "question", "How big is it?", lead)
    assert len(reply) > 0
