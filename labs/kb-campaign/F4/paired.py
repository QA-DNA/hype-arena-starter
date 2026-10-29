"""Paired per-fold / per-seed comparison on P80 (5 folds) and P10 (10 seeds): arena points per row of each config,
differences against the first config, and the count of folds/seeds where the config wins.
usage: python -I F4/paired.py '<spec>=<params json>' ... (run from $KBC)"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "harness"))
import numpy as np  # noqa: E402
import metrics as M  # noqa: E402
from api import check_prediction, resolve, run_variant  # noqa: E402
from world import load_track  # noqa: E402

cfgs = [(a.split("=", 1)[0], json.loads(a.split("=", 1)[1]) if "=" in a else {}) for a in sys.argv[1:]]
res = {}
for tn in ("P80", "P10"):
    tr = load_track(tn)
    for spec, prm in cfgs:
        cls, _ = resolve(spec, "Variant")
        pts = []
        for w, gold, sc in tr.folds:
            p = check_prediction(w, run_variant(cls(**prm), w, None))
            pts.append(M.compute(gold, p.labels[sc], p.conf[sc])["points_per_row"])
        res[(tn, spec, json.dumps(prm))] = np.array(pts)
for tn in ("P80", "P10"):
    base = res[(tn, cfgs[0][0], json.dumps(cfgs[0][1]))]
    print(tn, "base", cfgs[0][0], json.dumps(cfgs[0][1]), "mean", round(base.mean(), 4))
    for spec, prm in cfgs[1:]:
        x = res[(tn, spec, json.dumps(prm))]
        d = x - base
        print(f"  {spec} {json.dumps(prm)[:110]}: mean {x.mean():.4f} diff {d.mean():+.4f} "
              f"(sd {d.std(ddof=1):.4f}) wins {int((d > 0).sum())}/{len(d)} ties {int((d == 0).sum())}")
