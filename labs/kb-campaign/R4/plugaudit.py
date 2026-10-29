"""Own-page test for feature plugins: on a P10 fold world, derange the labels of one labelled page at a time
(fresh copies of a pristine world, so no cache carries over) and measure how much that page's OWN facts' plugin
values move. A plugin that keeps a labelled fact's own label/page out of its evidence shows 0 own-page change.
Usage: plugaudit.py REF [REF ...]   (run from $KBC)"""
import os, sys, time, json, importlib
import numpy as np
KBC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KBC, "harness"))
from api import feature_block
from world import load_track
D = {"true": "false", "false": "true", "unsure": "false"}
w0 = load_track("P10").folds[0][0]
lp = np.unique(w0.page[w0.labelled])
rng = np.random.RandomState(1)
pages = rng.choice(lp, 4, replace=False)
for ref in sys.argv[1:]:
    t = time.time()
    try:
        base = feature_block(w0.with_labels(w0.labelled, w0.label), ref)
        own, oth = [], []
        for p in pages:
            L = w0.label.copy()
            m = (w0.page == p) & w0.labelled
            L[m] = [D[x] for x in L[m]]
            X = feature_block(w0.with_labels(w0.labelled, L), ref)
            fo = (w0.page[w0.frow] == p)
            own.append(float(np.nanmax(np.abs(X[fo] - base[fo]))) if fo.any() else 0.0)
            oth.append(float(np.nanmax(np.abs(X[~fo] - base[~fo]))))
        print(json.dumps({"ref": ref, "k": base.shape[1], "own_page_max_change": max(own),
                          "other_facts_max_change": max(oth), "s": round(time.time() - t, 1)}), flush=True)
    except Exception as e:
        print(json.dumps({"ref": ref, "error": f"{type(e).__name__}: {e}"[:200]}), flush=True)
