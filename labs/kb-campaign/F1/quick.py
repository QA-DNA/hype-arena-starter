"""Quick in-process scorer for F1 configs on P80/P10 (Mac smoke only; real results go through harness/run.py)."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness")); sys.path.insert(0, HERE)
import numpy as np
import metrics as M
from api import check_prediction, run_variant
from world import load_track
import f1var

def score(params, tracks=("P80", "P10")):
    out = {}
    for tn in tracks:
        tr = load_track(tn); per = []; G = []; P = []; C = []
        t0 = time.time()
        for w, gold, sc in tr.folds:
            v = f1var.Variant(**params)
            p = check_prediction(w, run_variant(v, w, tr.train))
            m = M.compute(gold, p.labels[sc], p.conf[sc]); per.append(m)
            G.append(gold); P.append(p.labels[sc]); C.append(p.conf[sc])
        if tr.kind == "seeds":
            m = M.mean_std(per)[0]
        else:
            m = M.compute(np.concatenate(G), np.concatenate(P), np.concatenate(C))
        out[tn] = (round(m["points_per_row"], 4), round(m["accuracy"], 4), m["ece10"] and round(m["ece10"], 3),
                   round(m["false_precision"] or 0, 3), round(m["false_recall"] or 0, 3), round(time.time() - t0, 1))
    return out

if __name__ == "__main__":
    for a in sys.argv[1:]:
        p = json.loads(a)
        r = score(p)
        print(json.dumps(p), r, "sel=%.4f" % np.mean([r[t][0] for t in r]), flush=True)
