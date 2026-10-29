"""Extra sweeps on cached embeddings: probe C in {1,100,1000} + hybrids (zero / max imputation).  python -I extras.py <model>"""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); sys.path.insert(0, '/tmp/veridyct-emb/w1')
import harness as H; H.set_threads(2)
import os; os.environ['HF_HUB_OFFLINE'] = '1'
import torch; torch.set_num_threads(2)
import time, warnings
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
from models import MODELS
warnings.filterwarnings('ignore')
mid = sys.argv[1]; cfg = MODELS[mid]; SYM, QP, DP = cfg['sym'], cfg['q'], cfg['d']
if cfg['trc'] and 'veridyct-bench' in sys.prefix: sys.exit('trc model: use the w1 venv')
Z = np.load(f'/tmp/veridyct-emb/w1/emb/{mid.replace("/", "__")}.npz'); X_all, X_sfq = Z['X_all'], Z['X_sfq']
rows, lex = H.load(); sf = H.single_fact_rows(rows); pos = [r['idx'] for r in sf]; X_sf = X_all[pos]
fa, fattr = H.page_folds(sf), H.attribute_folds(sf)
pairs = [(s, a) for s, d in lex['subjects'].items() for a in d['attributes']]
l2 = lambda X: np.asarray(X, float) / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)
from sentence_transformers import SentenceTransformer
model = SentenceTransformer(mid, device='cpu', trust_remote_code=cfg['trc']).float()
D = model.encode([DP + H.describe(s, a) for s, a in pairs], batch_size=64, convert_to_numpy=True, show_progress_bar=False)
S_zs = l2(X_sfq) @ l2(D).T
EX = dict(params_m=None)
writer = H.ResultWriter(H.results_path('w1'))
def log(task, variant, m, notes):
    writer.add('w1', mid, task, variant, m, n=len(sf), notes='EXTRA sweep (not the spec default); ' + notes)
    print(f'[{mid}] {task}/{variant}: acc_all={m["acc_all"]:.3f} ge5={m["acc_ge5"]:.3f} 1to4={m["acc_1to4"]:.3f} unseen={m["acc_unseen"]:.3f}', flush=True)

class RecLR(LogisticRegression):
    store = []
    def fit(self, *a, **k):
        super().fit(*a, **k); RecLR.store.append(self); return self
def probe_recorded(folds, C):
    orig = H.LogisticRegression; H.LogisticRegression, RecLR.store = RecLR, []
    try: res = H.run_probe_attr(X_sf, sf, lex, folds, C=C)
    finally: H.LogisticRegression = orig
    return res, list(RecLR.store)
def zs_z(v):
    sd = v.std(); return (v - v.mean()) / sd if sd > 1e-9 else np.zeros_like(v)
def hybrid(models, folds, S, w=1.0, impute='zero'):
    subj = defaultdict(list)
    for j, (s, _) in enumerate(pairs): subj[s].append(j)
    Xn, pred = l2(X_sf), np.empty(len(sf), dtype=object)
    for (tr, te), mdl in zip(folds, models):
        LP, cidx = mdl.predict_log_proba(Xn[te]), {c: i for i, c in enumerate(mdl.classes_)}
        for k, i in enumerate(te):
            P = subj.get(sf[i]['facts'][0]['subject']) or list(range(len(pairs)))
            attrs = [pairs[j][1] for j in P]; seen = [t for t, a in enumerate(attrs) if a in cidx]; zp = np.zeros(len(P))
            if len(seen) > 1: zp[seen] = zs_z(LP[k, [cidx[attrs[t]] for t in seen]])
            if impute == 'max' and seen and len(seen) < len(P): zp[[t for t in range(len(P)) if t not in seen]] = zp[seen].max()
            pred[i] = attrs[int(np.argmax(zp + w * zs_z(S[i, P])))]
    return pred
y_sf = np.array([r['facts'][0]['attribute'] for r in sf], dtype=object)
tcp, tca = H.train_counts(sf, fa), H.train_counts(sf, fattr)
for C in (1.0, 100.0, 1000.0):
    (m, _), mp = probe_recorded(fa, C)
    log('attr_probe', f'LR_C{C:g}', m, 'page_folds(sf)')
    for imp in ('zero', 'max'):
        log('attr_hybrid', f'C{C:g}_z_probe+z_zeroshot' + ('_unseen_max' if imp == 'max' else ''), H.attr_metrics(y_sf, hybrid(mp, fa, S_zs, 1.0, imp), tcp), 'page_folds(sf), w=1')
    (m, _), ma = probe_recorded(fattr, C)
    for imp in ('zero', 'max'):
        log('attr_unseen', f'C{C:g}_hybrid_z_probe+z_zeroshot' + ('' if imp == 'zero' else '_unseen_max').replace('_unseen_max', '_unseen_max'), H.attr_metrics(y_sf, hybrid(ma, fattr, S_zs, 1.0, imp), tca), 'attribute_folds(sf), w=1')
print(f'[{mid}] EXTRAS DONE', flush=True)
