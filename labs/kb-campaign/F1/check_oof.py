"""Self-check: a labelled row's out-of-fold score (used to fit calibration and the decision rule) and its
plugin features never depend on its own label or its page's labels. Flips the labels of one page and checks
that the page's OOF row scores and plugin columns are bit-identical. python -I check_oof.py"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness")); sys.path.insert(0, HERE)
import numpy as np
import f1var, plugins
from world import load_track

w = load_track("P80").folds[0][0]
q = int(w.page[np.flatnonzero(w.labelled & (w.label == "true"))[0]])
flip = w.label.copy()
on = (w.page == q) & w.labelled
flip[on] = np.where(flip[on] == "true", "false", "true")
w2 = w.with_labels(w.labelled, flip)
for m in ("dynworld", "accu", "truthfinder", "ds", "crh"):
    v = f1var.Variant(method=m)
    a, _ = f1var.oof_rows(w, v.scores); b, _ = f1var.oof_rows(w2, v.scores)
    assert np.array_equal(a[on], b[on]), m
    assert not np.array_equal(a, b), m  # other rows do see the flipped labels (sanity: the flip did something)
X1 = plugins.td_all(w); X2 = plugins.td_all(w2)
fo = on[w.frow]
assert np.array_equal(X1[fo], X2[fo]) and not np.array_equal(X1, X2)
print("oof self-check ok: page", q, "rows", int(on.sum()))
