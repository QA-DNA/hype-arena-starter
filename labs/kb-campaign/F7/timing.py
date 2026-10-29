"""Runtime of one F7 configuration on a 20,000-row world with torch limited to F7_THREADS (default 2).
  python -I F7/timing.py 'F7/gnn.py:Variant' '{"seeds": 3}' [world track, default Sdev-jr] [refit|transfer|both]
Prints one JSON line: refit run(world) seconds, transfer fit(practice) and predict(world) seconds, peak RSS."""
import json
import os
import resource
import socket
import sys
import time

os.environ.setdefault("F7_THREADS", "2")
for v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(v, os.environ["F7_THREADS"])
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "harness"))
from api import resolve  # noqa: E402
from world import load_track, practice_full  # noqa: E402

spec, params = sys.argv[1], json.loads(sys.argv[2] if len(sys.argv) > 2 else "{}")
track = sys.argv[3] if len(sys.argv) > 3 else "Sdev-jr"
mode = sys.argv[4] if len(sys.argv) > 4 else "both"
cls, _ = resolve(spec, "Variant")
w = load_track(track).folds[0][0]
out = dict(spec=spec, params=params, track=track, rows=w.n, facts=w.n_facts, labelled=int(w.labelled.sum()),
           threads=int(os.environ["F7_THREADS"]), host=socket.gethostname())
if mode in ("refit", "both"):
    t = time.perf_counter(); cls(**params).run(w); out["refit_s"] = round(time.perf_counter() - t, 1)
if mode in ("transfer", "both"):
    v = cls(**params)
    t = time.perf_counter(); v.fit(practice_full()[0]); out["fit_practice_s"] = round(time.perf_counter() - t, 1)
    t = time.perf_counter(); v.predict(w); out["predict_s"] = round(time.perf_counter() - t, 1)
r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
out["peak_rss_mb"] = round(r / 2**20 if sys.platform == "darwin" else r / 1024, 1)
print(json.dumps(out), flush=True)
