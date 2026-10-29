"""In-process runtime check on a 20,000-row world (run under /usr/bin/time -l with 2 BLAS threads).
  python -I P3/bench20k.py SPEC PARAMS_JSON TRACK      e.g. Ssyn-jt (fit on practice, predict syn) or Ssyn-jr
Prints world size, fit / predict seconds, the label counts, and the confidence-range check."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KBC = os.path.dirname(HERE)
os.chdir(KBC)
sys.path.insert(0, os.path.join(KBC, "harness"))
import numpy as np  # noqa: E402
from api import check_prediction, resolve  # noqa: E402
from world import load_track  # noqa: E402

spec, params, tname = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
t0 = time.perf_counter()
t = load_track(tname)
w, gold, sc = t.folds[0]
t1 = time.perf_counter()
v = resolve(spec, "Variant")[0](**params)
v.fit(t.train if t.train is not None else w)
t2 = time.perf_counter()
p = check_prediction(w, v.predict(w))
t3 = time.perf_counter()
lab, conf = np.asarray(p.labels), np.asarray(p.conf)
dec = lab != "unsure"
print(f"world {w.name} rows {w.n} facts {w.n_facts} labelled {int(w.labelled.sum())}")
print(f"load {t1 - t0:.1f}s fit {t2 - t1:.1f}s predict {t3 - t2:.1f}s total {t3 - t0:.1f}s")
print("labels", {k: int((lab == k).sum()) for k in ("true", "false", "unsure")})
print(f"decided conf min {conf[dec].min():.4f} max {conf[dec].max():.4f}; below 0.5: {int((conf[dec] < 0.5).sum())}; "
      f"unsure conf all NaN: {bool(np.isnan(conf[~dec]).all())}; chosen {getattr(v, 'chosen', None)}")
rc = getattr(v, "rc", None)
if rc is not None and rc.rule == "arena":
    print(f"RowCal arena: u={rc.u:.4f}, lower bound of a decided confidence (1+u)/2 = {(1 + rc.u) / 2:.4f}")
