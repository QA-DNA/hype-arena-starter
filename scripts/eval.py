"""Local evaluation, no Docker: the main dev loop.

Hides every 5th practice label (exactly as scripts/input.py does for check.sh), runs the
pipeline in-process, and scores it against the hidden labels.

    python scripts/eval.py                    # full system
    python scripts/eval.py --gold-extraction  # truth engine alone, as if extraction were perfect
    python scripts/eval.py --no-claims        # labels only (faster)
    python scripts/eval.py --show-errors 20   # print 20 wrong labels with the why
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from polygraph import pipeline  # noqa: E402
from polygraph.lexicon import Lexicon  # noqa: E402
from polygraph.validate import validate  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gold-extraction", action="store_true")
    p.add_argument("--no-claims", action="store_true")
    p.add_argument("--every", type=int, default=5, help="hide every Nth label (default 5, like input.py)")
    p.add_argument("--offset", type=int, default=0, help="which fold to hide (0..every-1)")
    p.add_argument("--show-errors", type=int, default=0)
    a = p.parse_args()

    lexicon = Lexicon.load(ROOT / "data" / "lexicon.json")
    bundle = pipeline.Bundle.load()
    truth = {r.id: r.label for r in bundle.rows}
    rows = [replace(r, label="" if i % a.every == a.offset else r.label) for i, r in enumerate(bundle.rows)]

    t0 = time.perf_counter()
    res = pipeline.run(rows, lexicon, bundle, claims=not a.no_claims, gold_extraction=a.gold_extraction)
    secs = time.perf_counter() - t0

    print(f"\n== stages ({secs:.1f}s total)")
    for s in res.stages:
        print(f"  {s['name']:<10} {s['ms']:>9} ms   {s['count']}")

    cm = Counter((truth[v.id], v.label) for v in res.verdicts)
    n = sum(cm.values())
    right = sum(c for (t, p_), c in cm.items() if t == p_)
    decided = [(t, p_) for (t, p_) in cm.elements() if p_ != "unsure" and t != "unsure"]
    print(f"\n== labels on {n} hidden rows")
    print(f"  exact match (incl. unsure): {right / n:.3f}")
    if decided:
        print(f"  accuracy on true/false calls: {sum(t == p_ for t, p_ in decided) / len(decided):.3f}")
    print("  confusion (rows = truth, cols = ours):")
    labels = ["true", "false", "unsure"]
    print("            " + "".join(f"{l:>8}" for l in labels))
    for t in labels:
        print(f"  {t:<10}" + "".join(f"{cm[(t, p_)]:>8}" for p_ in labels))

    # Brier score of the confidences on true/false calls (lower is better)
    brier = [((v.confidence or 0.5) - (truth[v.id] == v.label)) ** 2 for v in res.verdicts if v.label != "unsure"]
    if brier:
        print(f"  Brier score of confidences: {sum(brier) / len(brier):.3f}")

    if a.show_errors:
        print(f"\n== first {a.show_errors} wrong labels")
        texts = {r.id: r for r in bundle.rows}
        for v in [v for v in res.verdicts if truth[v.id] != v.label][: a.show_errors]:
            r = texts[v.id]
            print(f"  {v.id} [{r.date}] truth={truth[v.id]} ours={v.label}({v.confidence}) {v.why}\n     {r.text}")

    if not a.no_claims:
        problems = Counter()
        for c in res.claims:
            for w in validate(c, lexicon):
                problems[w.split(":")[0]] += 1
        print(f"\n== claims: {len(res.claims)} (target exactly 1000)")
        print("  by type:", dict(Counter(c.type for c in res.claims)))
        print("  validator problems:", dict(problems) or "none")
        for c in res.claims[:: max(1, len(res.claims) // 8)][:8]:
            print(f"   {c.confidence:.2f} {c.type:<9} {c.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
