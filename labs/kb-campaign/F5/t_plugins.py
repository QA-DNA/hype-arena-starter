import sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'harness'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from world import load_track
import fp
tr = load_track(sys.argv[1] if len(sys.argv) > 1 else 'P80')
w, gold, sc = tr.folds[0]
print(w.name, w.n, w.n_facts, w.labelled.sum())
for name in fp.PLUGINS:
    t = time.perf_counter(); X = getattr(fp, name)(w); dt = time.perf_counter() - t
    assert X.shape == (w.n_facts, len(fp.COLS[name])), (name, X.shape)
    assert np.isfinite(X).all(), name
    print(f'{name:12s} {X.shape} {dt:.2f}s mean={np.round(X.mean(0), 3).tolist()}')
