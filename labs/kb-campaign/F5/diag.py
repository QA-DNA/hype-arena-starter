"""Per-row diagnostic on P80 (analysis only, gold read from the Track like run.py does; not a variant).

  python -I F5/diag.py '<f5v params json>' [ids,comma,separated]
Prints the predictions for the given ids and, per fingerprint rule, the label mix of the rows where it fires and
how the model labelled them (out-of-fold).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(os.path.dirname(HERE), "harness"), HERE]
import numpy as np  # noqa: E402

import f5v  # noqa: E402
import rules  # noqa: E402
from api import check_prediction, run_variant  # noqa: E402
from world import load_track  # noqa: E402

params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
ids = sys.argv[2].split(",") if len(sys.argv) > 2 else ["p-455", "p-466", "p-454", "p-499", "p-365"]
tr = load_track("P80")
G, P, C, F = [], [], [], {r: [] for r in rules.RULES}
for w, gold, sc in tr.folds:
    p = check_prediction(w, run_variant(f5v.Variant(**params), w))
    for k, i in enumerate(sc):
        if w.ids[i] in ids:
            print(w.ids[i], "gold", gold[k], "pred", p.labels[i], round(float(p.conf[i]), 3) if p.labels[i] != "unsure" else "", "|", w.text[i][:80])
    G += list(gold); P += list(p.labels[sc]); C += list(p.conf[sc])
    for r in rules.RULES:
        F[r] += list(rules.fires(w, r)[1][sc])
G, P = np.array(G), np.array(P)
print(f"points {np.mean(np.where(P == 'unsure', 0, np.where(P == G, 1, -1))):.4f}")
for r, f in F.items():
    f = np.array(f)
    if f.sum() == 0:
        continue
    g, pr = G[f], P[f]
    print(f"{r:40s} fires {f.sum():4d} gold T/F/U {np.sum(g == 'true'):4d}/{np.sum(g == 'false'):3d}/{np.sum(g == 'unsure'):2d}"
          f" | model F {np.sum(pr == 'false'):3d} (right {np.sum((pr == 'false') & (g == 'false')):3d}) U {np.sum(pr == 'unsure'):2d}"
          f" | model acc {np.mean(pr == g):.3f}")
