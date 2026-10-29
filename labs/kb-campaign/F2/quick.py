"""Dev driver (not for reported numbers): python -I quick.py TRACK 'Class' '{"param": 1}' ..."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness"))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import metrics as M  # noqa: E402
from api import check_prediction, run_variant  # noqa: E402
from world import load_track  # noqa: E402
import f2var  # noqa: E402

track = load_track(sys.argv[1])
for a in range(2, len(sys.argv), 2):
    cls = getattr(f2var, sys.argv[a]); params = json.loads(sys.argv[a + 1])
    t0 = time.time(); per = []; G = []; P = []; Cc = []
    for w, gold, sc in track.folds:
        v = cls(**params)
        p = check_prediction(w, run_variant(v, w, track.train))
        per.append(M.compute(gold, p.labels[sc], p.conf[sc]))
        G.append(gold); P.append(p.labels[sc]); Cc.append(p.conf[sc])
    if track.kind == "seeds":
        m = M.mean_std(per)[0]
    else:
        m = M.compute(np.concatenate(G), np.concatenate(P), np.concatenate(Cc))
    print(f"{sys.argv[1]} {sys.argv[a]} {sys.argv[a+1]}: pts={m['points_per_row']:.4f} acc={m['accuracy']:.4f} "
          f"ece={m['ece10'] or 0:.4f} fP={m['false_precision']:.3f} fR={m['false_recall']:.3f} cov={m['coverage']:.3f} "
          f"{time.time()-t0:.1f}s chosen={getattr(v, 'chosen', '')}", flush=True)
