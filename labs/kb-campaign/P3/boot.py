"""Page-cluster bootstrap (R4/boot.py's method) on the FRESH splits (results/P3-denoise2.jsonl: 15 permuted P80 folds,
P10 seeds 10..29). Selection = (P80 pooled points + mean over P10 seeds) / 2 with page weights; B = 2000, seed 0.
  python -I P3/boot.py CONFIGS.json   (first config = the reference)"""
import json
import os
import sys

import numpy as np

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfgs = json.load(open(sys.argv[1]))
key = lambda s, p: (s, json.dumps(p, sort_keys=True))  # noqa: E731
want = [key(*c) for c in cfgs]
D = {}
for line in open(os.path.join(KBC, "results", "P3-denoise2.jsonl")):
    r = json.loads(line)
    k = key(r["variant"], r["params"])
    if k in want:
        D.setdefault(k, {})[r["split"]] = (np.array(r["row_points"], float), np.array(r["row_page"], int))
splits = sorted(set.intersection(*[set(D.get(k, {})) for k in want]))
p80 = [s for s in splits if s.startswith("P80")]; p10 = [s for s in splits if s.startswith("P10")]
npg = 1 + max(int(pg.max()) for d in D.values() for _, pg in d.values())


def sel(k, w):
    d = D[k]
    a = sum((w[d[s][1]] * d[s][0]).sum() for s in p80) / sum(w[d[s][1]].sum() for s in p80)
    b = np.mean([(w[d[s][1]] * d[s][0]).sum() / w[d[s][1]].sum() for s in p10])
    return (a + b) / 2, a, b


rng = np.random.RandomState(0)
W = [np.bincount(rng.randint(0, npg, npg), minlength=npg).astype(float) for _ in range(2000)]
one = np.ones(npg)
ref = want[0]
SB = {k: np.array([sel(k, w) for w in W]) for k in want}
print(f"fresh splits: P80 {len(p80)} folds, P10 {len(p10)} seeds, pages {npg}, B 2000")
for (s, p), k in zip(cfgs, want):
    s0 = sel(k, one); r0 = sel(ref, one)
    d = SB[k] - SB[ref]
    lo, hi = np.percentile(d[:, 0], [2.5, 97.5])
    print(f"sel {s0[0]:.4f} (P80 {s0[1]:.4f} P10 {s0[2]:.4f}) diff {s0[0] - r0[0]:+.4f} boot SE {d[:, 0].std():.4f} "
          f"CI [{lo:+.4f}, {hi:+.4f}] | P80 {s0[1] - r0[1]:+.4f} +- {d[:, 1].std():.4f} P10 {s0[2] - r0[2]:+.4f} +- "
          f"{d[:, 2].std():.4f} | {s} {json.dumps(p, sort_keys=True)}")
