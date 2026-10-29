import sys, os, time, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath('.')), 'harness')); sys.path.insert(0, '.')
from world import load_track
import f2var, f2feat, f2core as K
t = load_track(sys.argv[1]); w = t.folds[0][0]
t0 = time.time(); K.keys_of(w); print('keys', time.time() - t0)
for name in sys.argv[2:]:
    t0 = time.time()
    if name.startswith('feat:'):
        X = getattr(f2feat, name[5:])(w); print(name, X.shape, 'nan', np.isnan(X).sum(), '%.1fs' % (time.time() - t0))
    else:
        eng = name
        v = f2var.Chain(engine=eng); v.prep(w); s = v.scores(w); print(name, '%.1fs' % (time.time() - t0))
