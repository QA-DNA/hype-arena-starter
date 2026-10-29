import os, sys, time, json, resource
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness")); sys.path.insert(0, HERE)
import numpy as np, td
from world import load_track
w = load_track(sys.argv[1]).folds[0][0]
t0 = time.time(); td.graph(w); print("graph %.1fs edges %d" % (time.time() - t0, len(td.graph(w)["N"])), flush=True)
for a in sys.argv[2:]:
    p = json.loads(a); m = p.pop("method")
    t0 = time.time(); pf, rel, ex = td.run_method(w, m, **p)
    print(m, p, "%.1fs" % (time.time() - t0), "rss %.0fMB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20), "mean pf %.3f" % np.nanmean(pf), flush=True)
