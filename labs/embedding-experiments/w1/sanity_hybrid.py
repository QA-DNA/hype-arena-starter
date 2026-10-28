import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(1)
import numpy as np, warnings; warnings.filterwarnings('ignore')
from collections import defaultdict
from sklearn.linear_model import LogisticRegression
Z = np.load('/tmp/veridyct-emb/w1/emb/sentence-transformers__all-MiniLM-L6-v2.npz'); X_all = Z['X_all']
rows, lex = H.load(); sf = H.single_fact_rows(rows); X_sf = X_all[[r['idx'] for r in sf]]; fa = H.page_folds(sf)
pairs = [(s, a) for s, d in lex['subjects'].items() for a in d['attributes']]
l2 = lambda X: X / np.linalg.norm(X, axis=1, keepdims=True)
class RecLR(LogisticRegression):
    store = []
    def fit(self, *a, **k): super().fit(*a, **k); RecLR.store.append(self); return self
H.LogisticRegression = RecLR
m, p = H.run_probe_attr(X_sf, sf, lex, fa)
subj = defaultdict(list)
for j, (s, _) in enumerate(pairs): subj[s].append(j)
z = lambda v: (v - v.mean()) / v.std() if v.std() > 1e-9 else np.zeros_like(v)
pred = np.empty(len(sf), dtype=object); Xn = l2(X_sf); rng = np.random.default_rng(0)
S = rng.normal(size=(len(sf), len(pairs)))  # random zero-shot scores; weight 1e-9 -> must not change anything but ties
for (tr, te), mdl in zip(fa, RecLR.store):
    LP, cidx = mdl.predict_log_proba(Xn[te]), {c: i for i, c in enumerate(mdl.classes_)}
    for k, i in enumerate(te):
        P = subj[sf[i]['facts'][0]['subject']]; attrs = [pairs[j][1] for j in P]
        seen = [t for t, a in enumerate(attrs) if a in cidx]; zp = np.zeros(len(P))
        if len(seen) > 1: zp[seen] = z(LP[k, [cidx[attrs[t]] for t in seen]])
        pred[i] = attrs[int(np.argmax(zp + 1e-9 * z(S[i, P])))]
agree = np.mean([a == b for a, b in zip(pred, p)])
print('probe acc_all', round(m['acc_all'], 4), 'hybrid(w~0) acc', round(np.mean(pred == np.array([r['facts'][0]['attribute'] for r in sf], dtype=object)), 4), 'prediction agreement', round(agree, 4))
# why do the 1.6% differ?  expect: only rows whose gold-subject candidate set has <=1 attribute seen in the fold's training data
bad = [i for i in range(len(sf)) if pred[i] != p[i]]
nseen = {}
for (tr, te), mdl in zip(fa, RecLR.store):
    cidx = set(mdl.classes_)
    for i in te:
        P = subj[sf[i]['facts'][0]['subject']]; nseen[i] = (sum(pairs[j][1] in cidx for j in P), len(P))
print('disagreements', len(bad), 'all have <=1 seen candidate:', all(nseen[i][0] <= 1 for i in bad), sorted({nseen[i] for i in bad}))
