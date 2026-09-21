"""Offline tests for marginalia.extract against a mwoffliner-style fixture.
Run: .venv/bin/python -m pytest tests/ -q
"""
from marginalia.extract import parse, lead, headings, section, infobox, images

HTML = """
<div>
<section data-mw-section-id="0">
  <p>The Sahara is the largest hot desert on Earth, covering about 9.2 million square kilometres.</p>
  <p class="mw-empty-elt"></p>
  <p>Water is H<sub>2</sub>O and area is m<sup>2</sup>.</p>
</section>
<table class="infobox">
  <tr><th>Area</th><td>9.2 million km&sup2;</td></tr>
</table>
<section data-mw-section-id="1"><h2>Ecology</h2><p>Dunes and oases.</p></section>
<section data-mw-section-id="2"><h2>Climate</h2><p>Under 250 mm rain.</p></section>
<figure><img src="map.png" width="300" resource="./File:map.png" alt="Map"/></figure>
<figure><img src="icon.png" width="16" resource="./File:icon.png" alt="x"/></figure>
</div>
"""


def test_lead_skips_empty_and_normalises():
    s = parse(HTML)
    t = lead(s)
    assert t.startswith("The Sahara is the largest hot desert")
    assert "H\u2082O" in t          # H2O unicode
    assert "m\u00b2" in t or "m²" in t
    assert "mw-empty" not in t


def test_headings_and_section():
    s = parse(HTML)
    assert headings(s) == ["Ecology", "Climate"]
    assert "Dunes and oases" in section(s, "Ecology")
    assert section(s, "nope") == ""
    assert section(s, "clImate").strip() == "Climate Under 250 mm rain."


def test_infobox():
    s = parse(HTML)
    assert infobox(s) == {"Area": "9.2 million km²"}
    assert infobox(parse("<p>no box</p>")) == {}


def test_images_filters_small_and_orders():
    s = parse(HTML)
    imgs = images(s, "wikipedia/Sahara.html")
    # 16px icon dropped, only the 300px map remains
    assert [i["file"] for i in imgs] == ["map.png"]
    assert imgs[0]["alt"] == "Map"
    assert imgs[0]["zim_path"].endswith("/File:map.png") or "map.png" in imgs[0]["zim_path"]


ASSETS_HTML = """
<div>
<figure><img src="./_assets_/0c70a4/Sahara_real_color.jpg" width="272"/></figure>
<figure><img src="./_assets_/0c70a4/Flag_of_Chad.svg.png" width="23"/></figure>
</div>
"""


def test_images_assets_build_basename_and_alt_fallback():
    s = parse(ASSETS_HTML)
    imgs = images(s, "Sahara")
    # 23px flag filtered; file comes from the src basename, alt from the stem
    assert [i["file"] for i in imgs] == ["Sahara_real_color.jpg"]
    assert imgs[0]["alt"] == "Sahara real color"
    assert imgs[0]["zim_path"].endswith("_assets_/0c70a4/Sahara_real_color.jpg")


def test_math_to_tex():
    s = parse('<p><span class="mwe-math-element"><math>'
              '<annotation encoding="application/x-tex">{\\displaystyle x=1}</annotation></math>'
              '</span></p>')
    assert s.get_text() == "x=1" or "\\(x=1\\)" in s.get_text()
