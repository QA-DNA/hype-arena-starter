"""Per-fold arena points (P80 folds, P10 seeds) for a list of configs, and paired deltas vs the first config.
Same harness calls as run.py (load_track, run_variant, check_prediction, metrics.compute). Writes one JSON line per
config to F3/paired.jsonl. Run from $KBC: .venv/bin/python -I F3/paired.py '[["spec", {params}], ...]'"""
import json
import math
import os
import sys

import numpy as np

KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KBC, "harness"))
import metrics as M  # noqa: E402
from api import check_prediction, resolve, run_variant  # noqa: E402
from world import load_track  # noqa: E402


def per_fold(spec, params, track):
    t = load_track(track)
    cls, _ = resolve(spec, "Variant")
    out = []
    for world, gold, sc in t.folds:
        p = check_prediction(world, run_variant(cls(**params), world, t.train))
        out.append(M.compute(gold, p.labels[sc], p.conf[sc])["points"] / len(gold))
    return out


def main():
    cfgs = json.loads(sys.argv[1])
    res = {}
    with open(os.path.join(KBC, "F3", "paired.jsonl"), "a") as f:
        for spec, prm in cfgs:
            r = {tr: per_fold(spec, prm, tr) for tr in ("P80", "P10")}
            res[json.dumps([spec, prm])] = r
            f.write(json.dumps({"spec": spec, "params": prm, "per_fold": r}) + "\n")
    keys = list(res)
    ref = res[keys[0]]
    print("reference:", keys[0])
    for k in keys:
        line = []
        for tr in ("P80", "P10"):
            d = np.array(res[k][tr]) - np.array(ref[tr])
            se = d.std(ddof=1) / math.sqrt(len(d)) if len(d) > 1 else float("nan")
            line.append(f"{tr} mean {np.mean(res[k][tr]):.4f} delta {d.mean():+.4f} se {se:.4f} wins {int((d > 0).sum())}/{len(d)}")
        print(" | ".join(line), "|", k)


if __name__ == "__main__":
    main()
