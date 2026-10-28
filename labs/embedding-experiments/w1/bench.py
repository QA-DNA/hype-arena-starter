"""Worker w1 benchmark: one model per process.  Usage: python -I bench.py <hf_model_id> [--force]
Encodes once (the timed speed pass doubles as the embedding pass), caches embeddings in emb/, then runs every task and
appends each result to /tmp/veridyct-emb/results/w1.jsonl through H.ResultWriter."""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); sys.path.insert(0, '/tmp/veridyct-emb/w1')
import harness as H; H.set_threads(2)
import os; os.environ['HF_HUB_OFFLINE'] = '1'
import torch; torch.set_num_threads(2)
import time, traceback, warnings
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
from models import MODELS
warnings.filterwarnings('ignore')

W, EMB = 'w1', '/tmp/veridyct-emb/w1/emb'
os.makedirs(EMB, exist_ok=True)
mid = sys.argv[1]
cfg = MODELS[mid]; SYM, QP, DP = cfg['sym'], cfg['q'], cfg['d']
if cfg['trc'] and 'veridyct-bench' in sys.prefix:  # remote code breaks on transformers 5; run these from /tmp/veridyct-emb/w1/.venv
    print('SKIP: trust_remote_code model needs the w1 venv (transformers 4.46)'); sys.exit(3)
safe = mid.replace('/', '__')
t_start = time.time()

def l2(X):
    X = np.asarray(X, dtype=np.float64)
    return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)

def disk_mb(path):  # weights only: top-level + module sub-folders; safetensors win over .bin; skip foreign onnx/openvino copies
    skip = {'onnx', 'openvino', 'tf', 'flax', 'rust', 'coreml', 'tflite'}
    fs = [os.path.join(d, f) for d, ds, fn in os.walk(path) for f in fn
          if not (set(os.path.relpath(d, path).split(os.sep)) & skip)]
    w = [f for f in fs if f.endswith('.safetensors')] or [f for f in fs if f.endswith('.bin')]
    return sum(os.path.getsize(f) for f in w) / 2**20

# ---------------------------------------------------------------- data + model
rows, lex = H.load(); sf = H.single_fact_rows(rows)
pos = [r['idx'] for r in sf]
fa, fall, fattr = H.page_folds(sf), H.page_folds(rows), H.attribute_folds(sf)
pairs = [(s, a) for s, d in lex['subjects'].items() for a in d['attributes']]

from huggingface_hub import try_to_load_from_cache
from sentence_transformers import SentenceTransformer
snap = os.path.dirname(try_to_load_from_cache(mid, 'config.json'))
t0 = time.time()
model = SentenceTransformer(mid, device='cpu', trust_remote_code=cfg['trc'])
load_s = time.time() - t0
stored_dtype = str(next(model.parameters()).dtype).replace('torch.', '')
model = model.float()  # transformers 5 keeps checkpoint dtype (fp16 for some repos) = slow on CPU; fp32 is the fair/shippable baseline
params_m = sum(p.numel() for p in model.parameters()) / 1e6
dim, max_seq, dmb = model.get_sentence_embedding_dimension(), model.max_seq_length, disk_mb(snap)
print(f'[{mid}] loaded in {load_s:.1f}s params={params_m:.1f}M disk={dmb:.1f}MB dim={dim} max_seq={max_seq}', flush=True)

writer = H.ResultWriter(H.results_path(W))
base_notes = f'prefix sym={SYM!r} query={QP!r} doc={DP!r}; max_seq={max_seq}; stored_dtype={stored_dtype}, run in fp32; 2 threads, shared machine'
EX = dict(params_m=round(params_m, 2), disk_mb=round(dmb, 1), dim=dim)

def log(task, variant, metrics, n, notes='', **extra):
    writer.add(W, mid, task, variant, metrics, n=n, notes=(notes + '; ' if notes else '') + base_notes, **{**EX, **extra})
    print(f'[{mid}] {task}/{variant}: ' + ', '.join(f'{k}={v:.3f}' for k, v in metrics.items() if isinstance(v, float) and v == v and k in
          ('acc_all', 'acc_ge5', 'acc_1to4', 'acc_unseen', 'auc', 'ap', 'recall_at_k', 'mrr', 'arena_best', 'acc', 'macro_f1', 'sentences_per_s')), flush=True)

def timed(label, fn):
    t = time.time()
    try:
        out = fn()
    except Exception:
        print(f'[{mid}] FAILED {label}:\n{traceback.format_exc()}', flush=True)
        open('/tmp/veridyct-emb/w1/failures.log', 'a').write(f'{mid} {label}\n{traceback.format_exc()}\n')
        out = None
    print(f'[{mid}] {label} took {time.time() - t:.1f}s', flush=True)
    return out

# ---------------------------------------------------------------- encoding (the speed pass doubles as the embedding pass)
texts = [r['text'] for r in rows]
texts_sym = [SYM + t for t in texts]
texts_2000 = texts_sym + texts_sym[:103]
cache_f = f'{EMB}/{safe}.npz'
store = {}
def encode_fn(batch):
    out = model.encode(batch, batch_size=len(batch), convert_to_numpy=True, show_progress_bar=False)
    for t, v in zip(batch, out):
        store[t] = v
    return out

runs = [timed(f'speed/encode pass{i}', lambda: H.encode_speed(encode_fn, texts_2000)) for i in range(3)]
runs = sorted(runs, key=lambda r: r['sentences_per_s']); sp = runs[1]  # median of three timed passes (store is filled by all)
X_all = np.stack([store[t] for t in texts_sym])
X_sf = X_all[pos]
loadavg = os.getloadavg()[0]
EX['sents_per_s'] = round(sp['sentences_per_s'], 2)
log('speed', f'bs{sp["bs"]}_2000texts', {k: sp[k] for k in ('sentences_per_s', 'est_sec_20k_x86', 'wall_s')}, n=sp['n'],
    notes=f'median of 3 timed passes, all sents/s={[round(r["sentences_per_s"], 1) for r in runs]}; load_s={load_s:.1f}; loadavg1={loadavg:.1f} (machine shared by 8 workers)')

def enc_texts(ts, prefix):  # short texts: single call, cached in `store`
    ts = list(dict.fromkeys(prefix + t for t in ts))
    todo = [t for t in ts if t not in store]
    if todo:
        out = model.encode(todo, batch_size=64, convert_to_numpy=True, show_progress_bar=False)
        for t, v in zip(todo, out):
            store[t] = v
    return ts

# rows with the query-side prefix (only differs from X_sf for bge / arctic / mxbai)
if QP == SYM:
    X_sfq = X_sf
else:
    X_sfq = model.encode([QP + r['text'] for r in sf], batch_size=32, convert_to_numpy=True, show_progress_bar=False)
D_cache = {}
def desc_emb(descs):  # document-side prefix, cached
    todo = [d for d in dict.fromkeys(descs) if d not in D_cache]
    if todo:
        out = model.encode([DP + d for d in todo], batch_size=64, convert_to_numpy=True, show_progress_bar=False)
        D_cache.update(zip(todo, out))
    return np.stack([D_cache[d] for d in descs])

# ---------------------------------------------------------------- zero-shot (rows: query prefix; descriptions: doc prefix)
last = {}
def make_sim(Xrows, tag):
    Xn = l2(Xrows)
    def f(descs):
        S = Xn @ l2(desc_emb(descs)).T
        last[tag] = S
        return S
    return f

notes_zs = 'rows with query prefix, descriptions with doc prefix, restricted to gold subject, no training'
m, _ = timed('zeroshot describe', lambda: H.zeroshot_attr(make_sim(X_sfq, 'describe'), sf, lex)) or (None, None)
if m: log('attr_zeroshot', 'describe', m, len(sf), notes_zs)
m, _ = timed('zeroshot words', lambda: H.zeroshot_attr(make_sim(X_sfq, 'words'), sf, lex, desc_fn=lambda s, a: H.attr_words(a))) or (None, None)
if m: log('attr_zeroshot', 'attr_words_only', m, len(sf), notes_zs)
if QP != SYM:  # free extra: rows WITHOUT the query instruction (symmetric encoding of the claim)
    m, _ = timed('zeroshot describe symrows', lambda: H.zeroshot_attr(make_sim(X_sf, 'describe_sym'), sf, lex)) or (None, None)
    if m: log('attr_zeroshot', 'describe_rows_no_query_prefix', m, len(sf), 'rows encoded with symmetric prefix (none), descriptions with doc prefix')
S_zs = last.get('describe')

# ---------------------------------------------------------------- retrieval + truth probes (all rows, symmetric prefix)
m = timed('key_retrieval', lambda: H.key_retrieval(X_all, rows))
if m: log('key_retrieval', 'cosine_k10', m, len(rows), 'all 1897 rows, symmetric prefix; tfidf_* keys are the char(3,5) reference')
r = timed('truth_false', lambda: H.run_probe_false(X_all, rows, fall))
if r: log('truth_false', 'LR_balanced_C1', r[0], len(rows), 'page_folds(rows), false-vs-rest')
r = timed('truth_three', lambda: H.run_probe_three(X_all, rows, fall))
if r: log('truth_three', 'LR_balanced_C1', r[0], len(rows), 'page_folds(rows), raw softmax')

# ---------------------------------------------------------------- kNN
r = timed('attr_knn', lambda: H.run_knn_attr(X_sf, sf, lex, fa))
if r: log('attr_knn', 'k5', r[0], len(sf), 'page_folds(sf), restricted neighbour pool')

# ---------------------------------------------------------------- probe (fitted models are recorded and reused by the hybrid)
class RecLR(LogisticRegression):
    store = []
    def fit(self, *a, **k):
        super().fit(*a, **k); RecLR.store.append(self); return self

def probe_recorded(folds):
    orig = H.LogisticRegression
    H.LogisticRegression, RecLR.store = RecLR, []
    try:
        res = H.run_probe_attr(X_sf, sf, lex, folds)
    finally:
        H.LogisticRegression = orig
    return res, list(RecLR.store)

def zs_z(v):
    sd = v.std()
    return (v - v.mean()) / sd if sd > 1e-9 else np.zeros_like(v)

def hybrid(models, folds, S, w=1.0, impute='zero'):
    """z(probe log-proba) + w * z(zero-shot cosine) over the gold subject's candidate set; unseen candidates get probe z = 0."""
    subj = defaultdict(list)
    for j, (s, _) in enumerate(pairs): subj[s].append(j)
    Xn, pred = l2(X_sf), np.empty(len(sf), dtype=object)
    for (tr, te), mdl in zip(folds, models):
        LP, cidx = mdl.predict_log_proba(Xn[te]), {c: i for i, c in enumerate(mdl.classes_)}
        for k, i in enumerate(te):
            P = subj.get(sf[i]['facts'][0]['subject']) or list(range(len(pairs)))
            attrs = [pairs[j][1] for j in P]
            seen = [t for t, a in enumerate(attrs) if a in cidx]
            zp = np.zeros(len(P))
            if len(seen) > 1: zp[seen] = zs_z(LP[k, [cidx[attrs[t]] for t in seen]])
            if impute == 'max' and seen and len(seen) < len(P): zp[[t for t in range(len(P)) if t not in seen]] = zp[seen].max()
            pred[i] = attrs[int(np.argmax(zp + w * zs_z(S[i, P])))]
    return pred

y_sf = np.array([r['facts'][0]['attribute'] for r in sf], dtype=object)
res = timed('attr_probe (page folds)', lambda: probe_recorded(fa))
if res:
    (m, p_page), mods_page = res
    log('attr_probe', 'LR_C10', m, len(sf), 'page_folds(sf), restricted argmax')
    if S_zs is not None:
        for w in (1.0, 2.0):
            pred = hybrid(mods_page, fa, S_zs, w)
            mh = H.attr_metrics(y_sf, pred, H.train_counts(sf, fa))
            log('attr_hybrid', f'z_probe+{w:g}*z_zeroshot' if w != 1.0 else 'z_probe+z_zeroshot', mh, len(sf),
                'page_folds(sf); z-scored over the gold subject candidate set; unseen candidates probe z=0' + ('' if w == 1.0 else '; extra variant, zero-shot weight 2'))
        mh = H.attr_metrics(y_sf, hybrid(mods_page, fa, S_zs, 1.0, 'max'), H.train_counts(sf, fa))
        log('attr_hybrid', 'z_probe+z_zeroshot_unseen_max', mh, len(sf), 'extra variant: candidates the probe never saw get the max probe z of the seen ones (neutral prior)')

# ---------------------------------------------------------------- unseen attributes (leave-attribute-out)
res = timed('attr_unseen (attribute folds)', lambda: probe_recorded(fattr))
if res:
    (m, _), mods_attr = res
    log('attr_unseen', 'probe_alone_LR_C10', m, len(sf), 'attribute_folds(sf): every test attribute unseen, probe is 0 by construction')
    if S_zs is not None:
        tc0 = H.train_counts(sf, fattr)
        mz = H.attr_metrics(y_sf, H.zeroshot_attr(lambda d: S_zs, sf, lex)[1], tc0)  # zero-shot alone, same S as attr_zeroshot/describe
        log('attr_unseen', 'zeroshot_alone', mz, len(sf), 'same predictions as attr_zeroshot/describe (no training), shown for comparison')
        mh = H.attr_metrics(y_sf, hybrid(mods_attr, fattr, S_zs, 1.0, 'max'), tc0)
        log('attr_unseen', 'hybrid_unseen_max', mh, len(sf), 'extra variant: candidates the probe never saw get the max probe z of the seen ones (neutral prior)')
        for w in (1.0, 2.0):
            pred = hybrid(mods_attr, fattr, S_zs, w)
            mh = H.attr_metrics(y_sf, pred, tc0)
            log('attr_unseen', f'hybrid_z_probe+{w:g}*z_zeroshot' if w != 1.0 else 'hybrid_z_probe+z_zeroshot', mh, len(sf),
                'attribute_folds(sf); probe sees only OTHER attributes; unseen candidates probe z=0' + ('' if w == 1.0 else '; extra variant, zero-shot weight 2'))

np.savez_compressed(cache_f, X_all=X_all, X_sfq=X_sfq)
print(f'[{mid}] ALL DONE in {time.time() - t_start:.0f}s', flush=True)
