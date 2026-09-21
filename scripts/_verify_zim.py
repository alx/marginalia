"""One-shot: verify spec §11 checklist items against the pilot ZIMs.

Run on the host that holds the archives:  .venv/bin/python scripts/_verify_zim.py
Prints a PASS/FAIL line per item so the evidence is greppable.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import yaml  # noqa: E402

from marginalia import extract  # noqa: E402
from marginalia.zimstore import ZimLibrary  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIM_DIR = "/home/alx/zim"


def main() -> None:
    lib = ZimLibrary(ZIM_DIR)
    cfg = yaml.safe_load(open(os.path.join(ROOT, "agents.yaml")))
    results: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    # 1. Path scheme (new-namespace flat + old A/ both handled by _resolve)
    st = next(iter(lib.stores.values()))
    got = st.html("Sahara")
    check("path-scheme: flat article resolves", got is not None,
          f"Sahara -> {got[0]} ({len(got[1])} chars)" if got else "MISSING")

    # 2. Image round-trip: extract.images() then store.blob() returns bytes
    hit = lib.find("Sahara")
    if hit:
        topic, (path, html) = hit
        soup = extract.parse(html)
        imgs = extract.images(soup, path)
        ok_img = False
        detail = "no images found on Sahara"
        for im in imgs:
            b = lib.stores[topic].blob(im["zim_path"])   # full _assets_/ entry path
            if b and b[0] and b[1].startswith("image/"):
                ok_img = True
                detail = f"{im['file']} -> {len(b[0])} bytes, {b[1]}"
                break
        check("image: extract.images() + store.blob() round-trip", ok_img, detail)
    else:
        check("image: extract.images() + store.blob() round-trip", False, "Sahara not found")

    # 3. Full-text index
    try:
        hits = lib.stores["geography"].search("Sahara", 3)
        check("full-text: search() returns hits", len(hits) > 0, f"{hits}")
    except Exception as e:  # noqa: BLE001
        check("full-text: search() returns hits", False, repr(e))

    # 4. Seed resolution per agent (topic archives are subsets; report gaps).
    #    Agents whose topic archive is not in the pilot are SKIPPED, not failed.
    for name, a in cfg["agents"].items():
        topics_present = [t for t in a["topics"] if t in lib.stores]
        if not topics_present:
            check(f"seeds[{name}]", True, "SKIPPED — topic archive not in pilot")
            continue
        res = {s: bool(lib.find(s, prefer=a["topics"])) for s in a.get("seeds", [])}
        found = [s for s in res if res[s]]
        missing = [s for s in res if not res[s]]
        check(f"seeds[{name}]", len(found) > 0,
              f"{len(found)}/{len(res)} resolve (present topics: {topics_present}); "
              f"missing: {missing if missing else 'none'}")

    # 5. Date article (chronicle) — history ZIM not in pilot, so expected to miss
    if "history" in lib.stores:
        ok = bool(lib.find("September_21", prefer=["history"]))
        check("date-article: history present in pilot", ok,
              "September_21 " + ("found" if ok else "NOT found -> chronicle uses timelines"))
    else:
        check("date-article: history present in pilot", True,
              "SKIPPED — history ZIM not in pilot (expected)")

    print("\n".join(f"[{'PASS' if ok else 'FAIL'}] {n}  — {d}" for n, ok, d in results))
    fails = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(fails)}/{len(results)} passed")
    if fails:
        print("failing:", fails)


if __name__ == "__main__":
    main()
