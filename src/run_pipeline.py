"""
Glue: runs Layers 1-4 and prints a report you can show the mentors.

  python run_pipeline.py --lexicon data/lexicon.json --kb data/practice.csv \
         --eval data/practice.csv --cv 5            # honest k-fold on real data
  python run_pipeline.py --lexicon data/lexicon.json --kb data/practice.csv \
         --eval data/synthetic_validation.csv       # stress test on Step-5 data

NOTE: the eval file must have a `form` column. The real /universe/universe.csv
has none -> a text-to-form parser (Layer 0) still has to be built.
"""
import argparse
import csv
import json
import os
import random
import sys
import time
from collections import Counter

# Ensure current directory is in path for module resolution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from layer1_entity_resolution import EntityResolver
from layer2_temporal_kb import TemporalKB
from layer3_constraint_engine import ConstraintEngine
from layer4_bayesian_scoring import BayesianScorer


def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(kb_rows, eval_rows, resolver, train_rows=None):
    kb = TemporalKB()
    kb.load_rows(kb_rows, resolver)
    kb.build()
    engine = ConstraintEngine(kb, resolver)
    scorer = BayesianScorer()
    if train_rows:   # learn LRs on rows checked against a KB that excludes them
        pairs = [(engine.check(json.loads(r["form"]), r["date"]), r["label"]) for r in train_rows]
        scorer.fit(pairs).fit_temperature(pairs).tune_tau(pairs)
    out = []
    for r in eval_rows:
        res = engine.check(json.loads(r["form"]), r["date"])
        label, conf, p = scorer.score(res)
        out.append((r, label, conf, res))
    return out


def report(out, title):
    gold = Counter(r["label"] for r, *_ in out)
    conf_m = Counter((r["label"], lab) for r, lab, *_ in out)
    acc = sum(r["label"] == lab for r, lab, *_ in out) / max(len(out), 1)
    print(f"\n=== {title}: {len(out)} rows, accuracy {acc:.3f}")
    print("gold:", dict(gold))
    labs = ["true", "false", "unsure"]
    print("gold\\pred " + " ".join(f"{l:>7}" for l in labs))
    for g in labs:
        print(f"{g:>9} " + " ".join(f"{conf_m[(g, p)]:>7}" for p in labs))
    if "mutation_type" in out[0][0]:
        for m in sorted({r["mutation_type"] for r, *_ in out}):
            sub = [(r, l) for r, l, *_ in out if r["mutation_type"] == m]
            print(f"  {m:<20} acc {sum(r['label'] == l for r, l in sub) / len(sub):.3f}"
                  f"  pred {dict(Counter(l for _, l in sub))}")
    reasons = Counter(a.reason for *_, res in out for a in res.atoms)
    print("atom evidence:", dict(reasons))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lexicon", default="data/lexicon.json")
    ap.add_argument("--kb", default="data/practice.csv")
    ap.add_argument("--eval", default="data/practice.csv")
    ap.add_argument("--cv", type=int, default=0, help="k-fold over --eval (when eval == kb)")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    resolver = EntityResolver.from_file(a.lexicon)
    kb_rows, ev = read(a.kb), read(a.eval)
    t0 = time.time()
    if a.cv:
        random.seed(0)
        random.shuffle(ev)
        folds = [ev[i::a.cv] for i in range(a.cv)]
        out = []
        for i, test in enumerate(folds):
            rest = [r for j, f in enumerate(folds) if j != i for r in f]
            half = len(rest) // 2   # KB from one half, calibrate on the other
            calib_kb = rest[:half]
            kb = TemporalKB(); kb.load_rows(calib_kb, resolver); kb.build()
            eng = ConstraintEngine(kb, resolver)
            pairs = [(eng.check(json.loads(r["form"]), r["date"]), r["label"]) for r in rest[half:]]
            scorer = BayesianScorer().fit(pairs).fit_temperature(pairs).tune_tau(pairs)
            kb = TemporalKB(); kb.load_rows(rest, resolver); kb.build()
            eng = ConstraintEngine(kb, resolver)
            for r in test:
                res = eng.check(json.loads(r["form"]), r["date"])
                lab, conf, _ = scorer.score(res)
                out.append((r, lab, conf, res))
        report(out, f"{a.cv}-fold CV on {a.eval}")
    else:
        out = run(kb_rows, ev, resolver)
        report(out, f"eval {a.eval} (KB {a.kb})")
    print(f"time: {time.time() - t0:.2f}s")
    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "type", "text", "form", "label", "confidence"])
            for r, lab, conf, _ in out:
                w.writerow([r["id"], "", "", "", lab, "" if conf is None else conf])


if __name__ == "__main__":
    main()
