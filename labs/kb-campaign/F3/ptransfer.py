"""Practice-only transfer check (no suite data): split practice pages in two halves A / B (seeded). Train world =
A rows only, every row labelled. Target world = B rows only, `frac` of B's pages labelled (anchors), scored on
B's other rows. Compares transfer (fit A, predict B) with refit on B's own labels. One JSON line per
(config, split) to F3/ptransfer.jsonl, plus a mean line per config.
Run from $KBC: .venv/bin/python -I F3/ptransfer.py '<json list of fusion params>' [frac] [n_splits]"""
import json
import os
import random
import sys
import time

import numpy as np

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KBC, "harness")); sys.path.insert(0, os.path.join(KBC, "F3"))
import metrics as M  # noqa: E402
from world import World, practice_full  # noqa: E402

import fusion  # noqa: E402


def subworld(base, rows, labelled, gold, name):
    rows = np.asarray(rows)
    pg = base.page[rows]; _, newpg = np.unique(pg, return_inverse=True)
    return World(name, name + "-" + str(hash(tuple(rows.tolist())) & 0xFFFF), [base.ids[i] for i in rows],
                 [base.text[i] for i in rows], base.date[rows], [None] * len(rows), [base.facts[i] for i in rows],
                 base.lexicon, labelled, gold[rows], newpg, {})


def splits(base, n_splits, frac):
    for s in range(n_splits):
        rng = random.Random(500 + s)
        pages = list(range(base.n_pages)); rng.shuffle(pages)
        A = set(pages[: len(pages) // 2])
        ra = np.flatnonzero(np.isin(base.page, list(A))); rb = np.flatnonzero(~np.isin(base.page, list(A)))
        pb = sorted(set(base.page[rb].tolist()))
        lab_p = set(rng.sample(pb, max(1, round(frac * len(pb)))))
        lab_b = np.isin(base.page[rb], list(lab_p))
        yield s, ra, rb, lab_b


def main():
    cfgs = json.loads(sys.argv[1]); frac = float(sys.argv[2]) if len(sys.argv) > 2 else 0.1
    ns = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    _, base, gold = practice_full()
    out = open(os.path.join(KBC, "F3", "ptransfer.jsonl"), "a")
    for cfg in cfgs:
        mode = cfg.pop("mode", "t")
        per = []
        for s, ra, rb, lab_b in splits(base, ns, frac):
            wa = subworld(base, ra, np.ones(len(ra), bool), gold, "pA")
            wb = subworld(base, rb, lab_b, gold, "pB")
            v = fusion.Variant(**cfg)
            t0 = time.perf_counter()
            pred = v.fit(wa).predict(wb) if mode == "t" else v.run(wb)
            sc = np.flatnonzero(~lab_b)
            m = M.compute(gold[rb][sc], np.asarray(pred[0])[sc], np.asarray(pred[1])[sc])
            per.append(m)
            out.write(json.dumps({"cfg": cfg, "mode": mode, "frac": frac, "split": s, "metrics": m,
                                  "runtime_s": round(time.perf_counter() - t0, 2)}) + "\n"); out.flush()
        mean, sd = M.mean_std(per)
        out.write(json.dumps({"cfg": cfg, "mode": mode, "frac": frac, "split": "mean", "n_splits": ns, "metrics": mean,
                              "metrics_std": sd}) + "\n"); out.flush()
        print(f"{mode} {json.dumps(cfg)} frac={frac}: pts={mean['points_per_row']:.4f} (sd {sd['points_per_row']:.4f}) "
              f"acc={mean['accuracy']:.4f} ece={mean['ece10']:.4f} brier={mean['brier']:.4f}", flush=True)


if __name__ == "__main__":
    main()
