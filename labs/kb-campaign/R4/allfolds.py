"""Per-fold predictions of one config on P80 (5 folds) and P10 (10 seeds): out/af-<n>.npz (labels/conf per fold)."""
import json, os, sys
import numpy as np
KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KBC, "harness"))
from api import check_prediction, resolve, run_variant
from world import load_track
spec, params, out = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
cls, _ = resolve(spec, "Variant")
res = {}
for tn in ("P80", "P10"):
    t = load_track(tn)
    for k, (w, gold, sc) in enumerate(t.folds):
        p = check_prediction(w, run_variant(cls(**params), w, None))
        res[f"{tn}_{k}_lab"] = p.labels.astype(str); res[f"{tn}_{k}_conf"] = p.conf
np.savez(out, spec=spec, params=json.dumps(params), **res)
