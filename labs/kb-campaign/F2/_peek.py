import sys, collections as C, numpy as np
sys.path.insert(0, sys.argv[1])
from world import load_track
for name in sys.argv[2:]:
    t = load_track(name)
    w = t.folds[0][0]
    nobs = [len(v) for v in w.obs_typed.values()]
    print(name, 'n', w.n, 'facts', w.n_facts, 'pages', w.n_pages, 'labelled', int(w.labelled.sum()), 'okeys', len(w.obs_typed),
          'obs/key mean', np.mean(nobs), 'median', np.median(nobs), 'max', max(nobs))
    print(' label counts', C.Counter(w.label[w.labelled]))
    print(' kinds', C.Counter(f.kind for f in w.flat), 'ops', C.Counter(f.op for f in w.flat))
    print(' intervals', sum(iv is not None for iv in w.interval), 'dates', min(w.date), max(w.date))
    print(' facts/row', C.Counter(len(f) for f in w.facts).most_common(5))
    print(' stats', w.stats)
    print(' scored gold', C.Counter(t.folds[0][1]))
    nv = [len({w.flat[w.fstart[i] + j].canon for i, j in v}) for v in w.obs_typed.values()]
    print(' distinct values per key mean', np.mean(nv), 'max', max(nv))
