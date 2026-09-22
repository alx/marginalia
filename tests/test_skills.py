"""Offline tests for the skills/ modules (spec §4.7) and their wiring."""
from datetime import date
from types import SimpleNamespace

from bs4 import BeautifulSoup

from marginalia import guards
from marginalia.agent import Agent
from marginalia.skills import (ALL, coordinates, dates, has, infobox,
                               living_person, safety, spoilers, units)


# -- units --------------------------------------------------------------------
def test_units_km():
    assert units.augment("9,200 km of coastline") == \
        "9,200 km (≈ 5,717 mi) of coastline"


def test_units_km_squared_and_millions():
    out = units.augment("It covers 9.2 million km².")
    assert out == "It covers 9.2 million km² (≈ 3,552,138 mi²)."


def test_units_celsius_and_kg():
    assert units.augment("It is 0 °C outside") == "It is 0 °C (32.0 °F) outside"
    assert units.augment("It weighs 1 kg") == "It weighs 1 kg (≈ 2.20 lb)"


def test_units_no_match_and_idempotent():
    assert units.augment("Nothing to see here.") == "Nothing to see here."
    once = units.augment("It is 10 km long")
    assert units.augment(once) == once


# -- coordinates ----------------------------------------------------------------
def test_coordinates_dms():
    assert coordinates.decimal("46°36′00″N 116°52′00″E") == (46.6, 116.8667)


def test_coordinates_negative_hemispheres():
    lat, lon = coordinates.decimal("33°51′S 18°25′E")
    assert lat < 0 and lon > 0


def test_coordinates_decimal_pair():
    assert coordinates.decimal("46.6, -116.867") == (46.6, -116.867)


def test_coordinates_from_infobox():
    box = {"Location": "Lakeba, Papua New Guinea",
           "Coordinates": "5°00′S 151°00′E"}
    line = coordinates.from_infobox(box)
    assert line and line.startswith("Coordinates: -")
    assert "151" in line
    assert coordinates.from_infobox({"Population": "5"}) is None


# -- dates ----------------------------------------------------------------------
def test_today_article_title():
    assert dates.today_article_title(date(2026, 9, 21)) == "September_21"
    assert dates.today_article_title(date(2026, 1, 1)) == "January_1"


def test_on_this_day_events():
    html = """
    <html><body>
    <section data-mw-section-id="1"><h2>Events</h2>
      <p><b>1969</b> — Something happens.</p>
      <p><b>1989</b> — Another thing.</p>
    </section>
    <section data-mw-section-id="2"><h2>Other</h2><p>Ignore me.</p></section>
    </body></html>"""
    items = dates.on_this_day(BeautifulSoup(html, "html.parser"))
    assert items == ["1969 — Something happens.", "1989 — Another thing."]


def test_rounding_violation_detected():
    source = "Founded c. 3000 BCE by the settlers."
    assert dates.rounding_violation("Founded in 3000 BCE.", source)
    assert dates.rounding_violation("Founded around 3000 by settlers.", source)
    assert not dates.rounding_violation("Founded c. 3000 BCE.", source)
    assert not dates.rounding_violation("A quiet story with no years.", source)


# -- safety -----------------------------------------------------------------------
def test_safety_advice_rejected_in_posts():
    agent = SimpleNamespace(id="mycelia", skills=["safety"])
    assert not guards.ok("You should take two of these.", "You should take two of these.", agent)
    assert not guards.ok("Take 500 mg.", "Take 500 mg.", agent)


def test_safety_refusal_for_personal_notes():
    assert safety.needs_refusal("I took 500 mg and I feel dizzy, is that normal?")
    assert safety.needs_refusal("My child has a fever, what should I give them?")
    assert not safety.needs_refusal("What is a fever, generally speaking?")
    r = safety.refusal("I can't breathe, I think I overdosed")
    assert "emergency services" in r
    assert "emergency services" not in safety.refusal("I have a headache all the time")


def test_safety_crisis_flag():
    assert safety.is_crisis("I want to kill myself")
    assert not safety.is_crisis("What is a toxin?")


# -- spoilers ---------------------------------------------------------------------
def _soup(heads):
    h = "<html><body>" + "".join(f"<section><h2>{x}</h2><p>body</p></section>" for x in heads)
    return BeautifulSoup(h + "</body></html>", "html.parser")


def test_spoilers_cw_only_for_plot_articles():
    assert spoilers.cw_for(_soup(["Plot", "Reception"])) == "Spoilers"
    assert spoilers.cw_for(_soup(["History", "Reception"])) is None


def test_agent_cw_for_uses_spoilers_skill():
    cfg = {"agents": {"palette": {"topics": ["movies"], "hashtags": "#film",
                                 "skills": ["spoilers"]}}}
    ag = Agent("palette", cfg, db=None, lib=None, llm=None, pub=None)
    assert ag.cw_for(_soup(["Plot"])) == "Spoilers"
    assert ag.cw_for(_soup(["History"])) is None


def test_agent_without_skill_has_no_cw():
    cfg = {"agents": {"atlas": {"topics": ["geography"], "hashtags": "#geo",
                                "skills": []}}}
    ag = Agent("atlas", cfg, db=None, lib=None, llm=None, pub=None)
    assert ag.cw_for(_soup(["Plot"])) is None


# -- living_person -----------------------------------------------------------------
def test_is_living():
    assert living_person.is_living({"Born": "January 1, 1970", "Nationality": "X"})
    assert not living_person.is_living({"Born": "1900", "Died": "1980"})
    assert not living_person.is_living({"Period": "1900"})


# -- infobox card -------------------------------------------------------------------
def test_infobox_card():
    card = infobox.card({"Type": "Lake", "Area": "3,718 km²"})
    assert "Type: Lake" in card and "Area: 3,718 km²" in card
    assert infobox.card({}) == ""


# -- registry ----------------------------------------------------------------------
def test_registry_matches_yaml_names():
    assert set(ALL) == {"units", "coordinates", "dates", "safety", "spoilers",
                        "living_person", "infobox"}
    assert has(["infobox", "units"], "units")
    assert not has(None, "units")
    assert not has([], "units")


# -- guards skill integration --------------------------------------------------------
def test_dates_guard_integration():
    agent = SimpleNamespace(id="chronicle", skills=["dates"])
    src = "Founded c. 3000 BCE."
    assert not guards.ok("Founded in 3000 BCE.", src, agent)
    assert guards.ok("Founded c. 3000 BCE.", src, agent)


def test_other_agents_unaffected():
    agent = SimpleNamespace(id="atlas", skills=[])
    assert guards.ok("Founded in 3000 BCE.", "Founded c. 3000 BCE.", agent)
