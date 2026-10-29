"""R4 adversarial probes (read-only on everything outside R4/).

  probe.py fold SPEC PARAMS TRACK K OUT.npz [--shuffle SEED]
      run fold K of TRACK through the harness calls (load_track, run_variant, check_prediction) and save
      labels/conf for every row, scored idx, gold of scored rows. --shuffle permutes labels among the
      fold's labelled rows (training labels only) before the variant sees the world.
  probe.py score OUT1.npz [OUT2.npz ...]   independent scorer (own code, not metrics.py): points, acc, ECE, mF1
  probe.py csv OUT.npz PRED.csv            prediction CSV (id,label,confidence) of the scored rows for A/score.py
  probe.py attrs TRACK K                   pickle digest of the fold world + attribute names (for perturbation diffs)
"""
import hashlib
import json
import os
import pickle
import sys

import numpy as np

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KBC, "harness"))


def fold(spec, params, track, k, out, shuffle=None):
    from api import check_prediction, resolve, run_variant
    from world import load_track
    t = load_track(track)
    w, gold, sc = t.folds[int(k)]
    if shuffle is not None:
        lab = np.flatnonzero(w.labelled)
        perm = np.random.RandomState(int(shuffle)).permutation(lab)
        L = w.label.copy()
        L[lab] = w.label[perm]
        w = w.with_labels(w.labelled, L)
    cls, _ = resolve(spec, "Variant")
    v = cls(**json.loads(params))
    p = check_prediction(w, run_variant(v, w, t.train))
    np.savez(out, labels=p.labels.astype(str), conf=p.conf, sc=sc, gold=np.asarray(gold).astype(str),
             ids=np.array(w.ids), chosen=json.dumps(getattr(v, "chosen", []), default=str))


def my_metrics(g, p, c):
    g, p = np.asarray(g, str), np.asarray(p, str)
    pts = np.where(p == g, 1, np.where(p != "unsure", -1, 0)).sum()
    dec = (p != "unsure") & ~np.isnan(c)
    cc, ok = c[dec], (p == g)[dec]
    b = np.minimum((cc * 10).astype(int), 9)
    ece = sum(abs(ok[b == i].sum() - cc[b == i].sum()) for i in range(10)) / max(dec.sum(), 1)
    f1 = []
    for cl in ("true", "false", "unsure"):
        tp = ((p == cl) & (g == cl)).sum(); npred = (p == cl).sum(); ng = (g == cl).sum()
        pr = tp / npred if npred else 0.0; rc = tp / ng if ng else 0.0
        f1.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return dict(n=len(g), points_per_row=pts / len(g), accuracy=float((p == g).mean()), ece10=float(ece),
                macro_f1=float(np.mean(f1)), coverage=float((p != "unsure").mean()))


def score(paths):
    per, G, P, Cf = [], [], [], []
    for f in paths:
        d = np.load(f)
        sc = d["sc"]
        g, p, c = d["gold"], d["labels"][sc], d["conf"][sc]
        per.append(my_metrics(g, p, c)); G.append(g); P.append(p); Cf.append(c)
    pooled = my_metrics(np.concatenate(G), np.concatenate(P), np.concatenate(Cf))
    mean = {k: float(np.mean([m[k] for m in per])) for k in per[0]}
    print(json.dumps({"pooled": pooled, "mean_over_folds": mean,
                      "fold_points": [round(m["points_per_row"], 4) for m in per]}))


def to_csv(f, out):
    d = np.load(f)
    with open(out, "w") as fh:
        fh.write("id,label,confidence\n")
        for i in d["sc"]:
            lab = d["labels"][i]
            c = "" if lab == "unsure" else repr(float(d["conf"][i]))
            fh.write(f"{d['ids'][i]},{lab},{c}\n")


def attrs(track, k):
    from world import load_track
    w = load_track(track).folds[int(k)][0]
    print(sorted(w.__dict__), hashlib.sha256(pickle.dumps(w.__dict__, protocol=4)).hexdigest()[:16])


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "fold":
        sh = int(a[a.index("--shuffle") + 1]) if "--shuffle" in a else None
        fold(*a[1:6], shuffle=sh)
    elif a[0] == "score":
        score(a[1:])
    elif a[0] == "csv":
        to_csv(a[1], a[2])
    elif a[0] == "attrs":
        attrs(a[1], a[2])
