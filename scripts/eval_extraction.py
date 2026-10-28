"""How well do we turn sentences into facts? Cross-validated on practice.csv's `form` column.

    python scripts/eval_extraction.py            # 5 folds, grouped by page
    python scripts/eval_extraction.py --errors 30

Precision: of the facts we extract, how many are in the gold form.
Recall:    of the gold facts, how many we extract.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from itertools import groupby
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from polygraph import pipeline  # noqa: E402
from polygraph.attributor import Attributor  # noqa: E402
from polygraph.lexicon import Lexicon  # noqa: E402
from polygraph.linker import Linker  # noqa: E402
from polygraph.model import value_key  # noqa: E402
from polygraph.reader import parse_values  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--errors", type=int, default=0)
    a = p.parse_args()

    lex = Lexicon.load(ROOT / "data" / "lexicon.json")
    b = pipeline.Bundle.load()
    linker = Linker(lex, derived=True)
    mentions = {}
    for _, page in groupby(b.rows, key=lambda r: r.page):
        page = list(page)
        for r, ms in zip(page, linker.link_page([r.text for r in page])):
            mentions[r.id] = ms

    tp = fp = fn = 0
    by_kind = Counter()
    errors = []
    t0 = time.perf_counter()
    for k in range(a.folds):
        train = [r for r in b.rows if r.page % a.folds != k]
        test = [r for r in b.rows if r.page % a.folds == k]
        att = Attributor(lex).fit(train, b.forms, mentions)
        items = [(r, parse_values(r.text, [(m.start, m.end) for m in mentions[r.id] if m.start >= 0]), mentions[r.id]) for r in test]
        for r, facts in zip(test, att.assign_many(items)):
            gold = {(f["subject"], f["attribute"], value_key(f["value"])) for f in b.forms[r.id]}
            got = {(f.subject, f.attribute, value_key(f.value)) for f in facts}
            tp += len(gold & got)
            fp += len(got - gold)
            fn += len(gold - got)
            for g in gold:
                by_kind[(g[2].split('"kind": "')[1].split('"')[0], g in got)] += 1
            if gold != got:
                errors.append((r.text, sorted(gold - got), sorted(got - gold)))
    prec, rec = tp / max(1, tp + fp), tp / max(1, tp + fn)
    print(f"{a.folds}-fold, grouped by page ({time.perf_counter() - t0:.0f}s)")
    print(f"  precision {prec:.3f}  recall {rec:.3f}  F1 {2 * prec * rec / max(1e-9, prec + rec):.3f}")
    print("  recall by kind:", {k: f"{by_kind[(k, True)]}/{by_kind[(k, True)] + by_kind[(k, False)]}"
                                for k in sorted({k for k, _ in by_kind})})
    print(f"  rows fully right: {1 - len(errors) / len(b.rows):.3f}")
    for text, missed, extra in errors[: a.errors]:
        print(f"\n  {text}\n    missed: {missed}\n    extra:  {extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
