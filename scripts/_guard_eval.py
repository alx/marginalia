"""Dry-run guard evaluation: drafts real articles (NO posting) and reports
how many LLM attempts each draft needed to pass the guards at the configured
max_post_chars. Run on the host that has the ZIMs and the .env.

Usage:
    source .env
    python scripts/_guard_eval.py [articles_per_topic=2] [cfg=agents.yaml]
"""
import sys
import yaml

from marginalia import extract, guards
from marginalia.agent import _draft_context, path_title
from marginalia.run import build


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    cfg_path = sys.argv[2] if len(sys.argv) > 2 else "agents.yaml"
    cfg, _db, lib, agents = build(cfg_path)
    limit = cfg["defaults"]["max_post_chars"]
    print(f"evaluating {len(agents)} agents x {n} articles, limit={limit}\n")

    totals = {"OK1": 0, "OK2": 0, "OK3": 0, "FAIL": 0}
    for ag in agents:
        for topic in ag.topics:
            store = lib.stores.get(topic)
            if not store:
                print(f"{ag.id:10} {topic}: NO STORE")
                continue
            for path in store.search("the", n):
                got = store.html(path)
                if not got:
                    continue
                _, html = got
                soup = extract.parse(html)
                source, extra = _draft_context(ag, soup)
                draft = None
                attempts = 0
                for _ in range(3):
                    attempts += 1
                    d = ag.llm.write_post(ag.persona, ag.skills,
                                          title=path_title(path),
                                          source=source, extra=extra,
                                          limit=limit)
                    if guards.ok(d, source, ag, limit):
                        draft = d
                        break
                key = f"OK{attempts}" if draft is not None else "FAIL"
                totals[key] += 1
                print(f"{ag.id:10} {topic:15} {path[:38]:38} "
                      f"{key} len={len(draft or '')}", flush=True)
    print("\n=== summary ===")
    for k in ("OK1", "OK2", "OK3", "FAIL"):
        print(f"{k}: {totals[k]}")
    passed = totals["OK1"] + totals["OK2"] + totals["OK3"]
    total = passed + totals["FAIL"]
    print(f"pass rate: {passed}/{total} "
          f"({100 * passed / max(total, 1):.0f}%), "
          f"first-try: {100 * totals['OK1'] / max(total, 1):.0f}%")


if __name__ == "__main__":
    main()
