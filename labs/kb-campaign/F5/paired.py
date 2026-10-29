"""Paired, denoised comparison of F5 configs on practice only (overfitting guard, not the selection track).

Splits: P80 = GroupKFold(5) over pages repeated R times (rep 0 is the harness split, reps 1.. permute the page
ids first), P10 = seeds 0..S-1 (seeds 0..9 are the harness P10). Every config is scored on exactly the same splits,
so per-split differences are paired. Gold is read from the practice world exactly as world.load_track does and is
only used for scoring. Output: one JSON line per (config, split) in results/F5-paired.jsonl. A config with "_cls": "OnChain" runs
F5/onf2.py:OnChain (F5 layers on top of F2's Chain) instead of F5/f5v.py:Variant.

  python -I F5/paired.py --configs F5/cfg.json [--reps 5] [--seeds 30] [--jobs 8]
  python -I F5/paired.py --summary [--base NAME]
"""
import argparse
import json
import math
import multiprocessing as mp
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KBC = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(KBC, "harness"), HERE]
OUT = os.path.join(os.environ.get("KBC_RESULTS_DIR", os.path.join(KBC, "results")), "F5-paired.jsonl")


def splits(n_pages, reps, seeds):
    from sklearn.model_selection import GroupKFold
    import numpy as np
    out = []
    pages = np.arange(n_pages)
    for f, (_, te) in enumerate(GroupKFold(5).split(pages, groups=pages)):  # rep 0 = the harness P80 split
        lab = np.ones(n_pages, bool); lab[te] = False
        out.append((f"P80r0f{f}", lab))
    for r in range(1, reps):  # reps 1.. : random page-to-fold assignment (a GroupKFold over permuted ids is identical)
        perm = np.random.RandomState(100 + r).permutation(n_pages)
        for f in range(5):
            lab = np.ones(n_pages, bool); lab[perm[f::5]] = False
            out.append((f"P80R{r}f{f}", lab))
    for s in range(seeds):
        rng = random.Random(s)
        lab = np.zeros(n_pages, bool)
        lab[rng.sample(range(n_pages), max(1, round(0.1 * n_pages)))] = True
        out.append((f"P10s{s}", lab))
    return out


def job(args):
    name, params, sname, lab_pages = args
    import numpy as np
    import metrics as M
    import f5v
    from api import check_prediction, run_variant
    from world import practice_full
    _, base, gold = practice_full()
    lab = lab_pages[base.page]
    w = base.with_labels(lab, gold)
    sc = np.where(~lab)[0]
    kw = dict(params)
    if kw.pop("_cls", "f5v") == "OnChain":  # F5 layers on top of F2's Chain (F5/onf2.py)
        import onf2
        v = onf2.OnChain(**kw)
    else:
        v = f5v.Variant(**kw)
    p = check_prediction(w, run_variant(v, w))
    m = M.compute(gold[sc], p.labels[sc], p.conf[sc])
    return {"config": name, "params": params, "split": sname, "points": m["points_per_row"], "accuracy": m["accuracy"],
            "brier": m["brier"], "ece10": m["ece10"], "false_precision": m["false_precision"],
            "false_recall": m["false_recall"], "n": m["n"]}


def summary(base_name):
    import numpy as np
    R = {}
    for line in open(OUT):
        r = json.loads(line)
        R[(r["config"], r["split"])] = r
    cfgs = sorted({c for c, _ in R})
    for c in cfgs:
        rows = []
        for trk in ("P80", "P10"):
            sp = sorted(s for cc, s in R if cc == c and s.startswith(trk) and not re.match(r"P80r[1-9]", s))
            d = [R[(c, s)]["points"] - R[(base_name, s)]["points"] for s in sp if (base_name, s) in R]
            v = [R[(c, s)]["points"] for s in sp]
            b = [R[(c, s)]["brier"] - R[(base_name, s)]["brier"] for s in sp if (base_name, s) in R]
            if not d:
                continue
            se = np.std(d, ddof=1) / math.sqrt(len(d)) if len(d) > 1 else float("nan")
            rows.append(f"{trk} n={len(d):2d} pts {np.mean(v):.4f} d {np.mean(d):+.4f} se {se:.4f} wins {sum(x > 0 for x in d)}/{sum(x < 0 for x in d)}"
                        f" dBrier {np.mean(b):+.4f}")
        print(f"{c:28s} | " + " | ".join(rows))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--base", default="base")
    a = ap.parse_args()
    if a.summary:
        summary(a.base)
        sys.exit(0)
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(var, "1")
    from world import practice_full
    base = practice_full()[1]
    cfgs = json.load(open(a.configs))
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            r = json.loads(line); done.add((r["config"], json.dumps(r["params"], sort_keys=True), r["split"]))
    jobs = [(n, p, s, lab) for n, p in cfgs.items() for s, lab in splits(base.n_pages, a.reps, a.seeds)
            if (n, json.dumps(p, sort_keys=True), s) not in done]
    print(f"{len(jobs)} jobs", flush=True)
    fd = os.open(OUT, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    with mp.get_context("spawn").Pool(a.jobs) as pool:
        for rec in pool.imap_unordered(job, jobs, chunksize=4):
            os.write(fd, (json.dumps(rec) + "\n").encode())
    print("done", flush=True)
