"""Worker w9 benchmark: ONE model per process.   Usage: python -I bench.py <hf_model_id> [--tasks a,b,c] [--no-extra]
Encodes once (the timed speed pass doubles as the embedding pass), then runs every task and appends each result to
/tmp/veridyct-emb/results/w9.jsonl through H.ResultWriter. Own HF cache: /tmp/veridyct-emb/w9/hf. Nothing is written elsewhere."""
import os, sys
os.environ['HF_HOME'] = '/tmp/veridyct-emb/w9/hf'          # BEFORE harness (it only setdefault()s HF_HOME)
sys.path.insert(0, '/tmp/veridyct-emb/common')
import harness as H; H.set_threads(2)
import torch; torch.set_num_threads(2)
import time, traceback, warnings, random
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression
warnings.filterwarnings('ignore')

W, OUT = 'w9', '/tmp/veridyct-emb/w9'
Q_RETR = 'Represent this sentence for searching relevant passages: '
ALL = ('speed', 'attr_zeroshot', 'key_retrieval', 'truth', 'attr_knn', 'attr_probe', 'attr_unseen')  # run order (cheap first)

# kwargs handed to SentenceTransformer.encode(): sym = every symmetric task (probe, kNN, retrieval, truth);
# q = zero-shot claim rows; d = zero-shot descriptions. `prompt=` keeps ST's include_prompt pooling semantics.
MODELS = {
 'MongoDB/mdbr-leaf-mt': dict(sym={}, q=dict(prompt_name='query'), d={},
        note="card: model.encode(queries, prompt_name='query') [= 'Represent this sentence for searching relevant passages: '], documents raw; sym=raw"),
 'avsolatorio/GIST-small-Embedding-v0': dict(sym={}, q={}, d={}, note='card: no instruction needed, queries encoded directly'),
 'prdev/mini-gte': dict(sym={}, q={}, d={}, note='card: no prompts (DistilBERT, distilled from GTE)'),
 'hotchpotch/bekko-static-embedding-v1': dict(sym={}, q={}, d={}, trc=True, note='card: no prefixes, queries and docs share encode(); static mean of token vectors'),
 'hotchpotch/bekko-embedding-v1-a8m': dict(sym={}, q={}, d={}, note='card: no prefixes or instructions'),
 'dmis-lab/UltraBERT-Embed-150M': dict(
        sym=dict(prompt='Instruct: Retrieve semantically similar text.\nQuery: '),
        q=dict(prompt='Instruct: Given a short claim about a company, retrieve the attribute it states\nQuery: '), d=dict(prompt='Label: '),
        note="card: 'Instruct: {task}\\nQuery: ' on queries, docs raw, label phrases take 'Label: '; symmetric tasks use the same instruction on both sides ('Instruct: Retrieve semantically similar text.\\nQuery: ')"),
 'WhereIsAI/UAE-Large-V1': dict(sym={}, q=dict(prompt=Q_RETR), d={},
        note="card: no prompt for non-retrieval tasks; Prompts.C = 'Represent this sentence for searching relevant passages: {text}' on the QUERY only for retrieval"),
 'jinaai/jina-embeddings-v5-text-nano': dict(sym=dict(task='text-matching'), q=dict(task='retrieval', prompt_name='query'),
        d=dict(task='retrieval', prompt_name='document'), trc=True, extra_sym=dict(task='classification'),
        note="CC-BY-NC-4.0 (ceiling only). card: task adapters retrieval/text-matching/clustering/classification; retrieval uses prompt_name query/document; sym tasks use task='text-matching'"),
 'jxm/cde-small-v2': dict(sym=dict(prompt_name='document'), q=dict(prompt_name='query'), d=dict(prompt_name='document'), trc=True, cde=True, offline=False, local='/tmp/veridyct-emb/w9/cde_local',
        note="card: prompt_name query/document ('search_query: ' / 'search_document: '); two-stage: 512 corpus docs embedded by the first stage -> dataset_embeddings; sym tasks use the document prompt"),
 'lightonai/DenseOn': dict(sym=dict(prompt='query: '), q=dict(prompt='query: '), d=dict(prompt='document: '),
        tasks=('speed', 'attr_zeroshot', 'key_retrieval'), extra_sym=dict(prompt='document: '),
        note="retrieval-only (brief). card prompts 'query: ' / 'document: ' (CLS pooling); key retrieval is symmetric so 'query: ' on both sides (variant: 'document: ' on both); zero-shot rows 'query: ', descriptions 'document: '"),
}

mid = sys.argv[1]
cfg = MODELS[mid]
tasks = set(ALL if '--tasks' not in sys.argv else sys.argv[sys.argv.index('--tasks') + 1].split(','))
if '--tasks' not in sys.argv and 'tasks' in cfg:
    tasks = set(cfg['tasks'])
tasks.add('speed') if 'speed' in tasks else None
if cfg.get('offline', True):
    os.environ['HF_HUB_OFFLINE'] = '1'
SYM, QK, DK = cfg['sym'], cfg['q'], cfg['d']
arg = lambda name, default=None: sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
NOPROMPT = '--noprompt' in sys.argv          # every encode with no prompt / instruction / task adapter kwargs at all
TRUNC = int(arg('--trunc', 0))               # MRL-style truncation of the leading K dims (re-normalised by the harness)
TAG = arg('--tag', ('noprompt' if NOPROMPT else '') + (f'd{TRUNC}' if TRUNC else ''))
if NOPROMPT:
    SYM, QK, DK = {}, {}, {}
    cfg = {**cfg, 'extra_sym': None}
t_start = time.time()

VN = lambda kw: '_'.join(f'{v}' for v in kw.values()).replace(' ', '').replace(':', '') + '_adapter_or_prompt'

def log_fail(label):
    s = traceback.format_exc()
    print(f'[{mid}] FAILED {label}:\n{s}', flush=True)
    with open(f'{OUT}/failures.log', 'a') as f:
        f.write(f'--- {mid} :: {label}\n{s}\n')

def disk_mb(path):  # weights only: safetensors win over .bin; skip foreign onnx/openvino copies
    skip = {'onnx', 'openvino', 'tf', 'flax', 'rust', 'coreml', 'tflite'}
    fs = [os.path.join(d, f) for d, ds, fn in os.walk(path, followlinks=True) for f in fn
          if not (set(os.path.relpath(d, path).split(os.sep)) & skip)]
    w = [f for f in fs if f.endswith('.safetensors')] or [f for f in fs if f.endswith('.bin')]
    return sum(os.path.getsize(os.path.realpath(f)) for f in w) / 2**20

def l2(X):
    X = np.asarray(X, dtype=np.float64)
    return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)

# ---------------------------------------------------------------- data + model
rows, lex = H.load(); sf = H.single_fact_rows(rows)
pos = [r['idx'] for r in sf]
fa, fall, fattr = H.page_folds(sf), H.page_folds(rows), H.attribute_folds(sf)
pairs = [(s, a) for s, d in lex['subjects'].items() for a in d['attributes']]
y_sf = np.array([r['facts'][0]['attribute'] for r in sf], dtype=object)

from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer
snap = (cfg.get('local') if '--shim' in sys.argv else None) or snapshot_download(mid, allow_patterns=['*.json', '*.txt', '*.safetensors', '*.model', '*.py', '*.jsonl'], local_files_only=cfg.get('offline', True))
t0 = time.time()
try:  # explicit fp32: ST 6.2 otherwise honours the checkpoint dtype (a8m is stored in bf16, bekko-static in fp16)
    try:
        model = SentenceTransformer(snap, device='cpu', trust_remote_code=cfg.get('trc', False), model_kwargs=({'dtype': torch.float32} if int(__import__('transformers').__version__.split('.')[0]) >= 5 else {'torch_dtype': torch.float32}))
    except TypeError:
        log_fail('load with dtype kwarg (retrying without)')
        model = SentenceTransformer(snap, device='cpu', trust_remote_code=cfg.get('trc', False))
except Exception:
    log_fail('load'); sys.exit(2)
try:
    model.float()
except Exception:
    pass
DTYPE = str(next(model.parameters()).dtype) if any(True for _ in model.parameters()) else 'n/a'
load_s = time.time() - t0
try:
    params_m = sum(p.numel() for p in model.parameters()) / 1e6
except Exception:
    params_m = float('nan')
try:
    dim = model.get_sentence_embedding_dimension()
except Exception:
    dim = None
max_seq, dmb = getattr(model, 'max_seq_length', None), disk_mb(snap)
print(f'[{mid}] dtype={DTYPE} loaded in {load_s:.1f}s params={params_m:.1f}M disk={dmb:.1f}MB dim={dim} max_seq={max_seq} prompts={getattr(model, "prompts", None)}', flush=True)

writer = H.ResultWriter(H.results_path(W))
base_notes = f'{cfg["note"]}; max_seq={max_seq}; dtype {DTYPE} CPU 2 threads, machine shared by 9 workers (speed pessimistic)'
EX = dict(params_m=round(params_m, 2), disk_mb=round(dmb, 1), dim=dim, max_seq_length=max_seq)
SHOW = ('acc_all', 'acc_ge5', 'acc_1to4', 'acc_unseen', 'auc', 'ap', 'recall_at_k', 'mrr', 'arena_best', 'acc', 'macro_f1', 'sentences_per_s')

def log(task, variant, metrics, n, notes='', **extra):
    variant = variant + (f'@{TAG}' if TAG else '')
    if '--dry' not in sys.argv: writer.add(W, mid, task, variant, metrics, n=n, notes=(notes + '; ' if notes else '') + base_notes, **{**EX, **extra})
    print(f'[{mid}] {task}/{variant}: ' + ', '.join(f'{k}={v:.3f}' for k, v in metrics.items() if isinstance(v, float) and v == v and k in SHOW), flush=True)

def timed(label, fn):
    t = time.time()
    try:
        out = fn()
    except Exception:
        log_fail(label); out = None
    print(f'[{mid}] {label} took {time.time() - t:.1f}s', flush=True)
    return out

DS = {}  # cde dataset embeddings (first stage), filled below
def enc(texts, kw, bs=64):
    kw = dict(kw)
    if cfg.get('cde'):
        kw['dataset_embeddings'] = DS['e']
    out = model.encode(list(texts), batch_size=min(bs, max(1, len(texts))), convert_to_numpy=True, show_progress_bar=False, **kw)
    return np.asarray(out, dtype=np.float32)

# ---------------------------------------------------------------- cde: first stage on 512 unlabeled claims (transductive context, no labels)
if cfg.get('cde'):
    n_ctx = model[0].config.transductive_corpus_size
    ctx = random.Random(0).sample([r['text'] for r in rows], n_ctx)
    t = time.time()
    DS['e'] = model.encode(ctx, prompt_name='document', convert_to_tensor=True, show_progress_bar=False, batch_size=32)
    print(f'[{mid}] cde first stage on {n_ctx} claims took {time.time() - t:.1f}s', flush=True)
    base_notes += f'; cde minicorpus = {n_ctx} random unlabeled claims (seed 0), first stage once'

# ---------------------------------------------------------------- encoding: the timed speed pass doubles as the embedding pass
texts = [r['text'] for r in rows]
texts_2000 = texts + texts[:103]
store = {}
def encode_fn(batch):
    out = enc(batch, SYM, bs=len(batch))
    for t, v in zip(batch, out):
        store[t] = v
    return out

sp = timed('speed/encode', lambda: H.encode_speed(encode_fn, texts_2000))
if sp is None:
    sys.exit(3)
X_all = np.stack([store[t] for t in texts])
if dim is None: dim = EX['dim'] = int(X_all.shape[1])  # custom modules (cde) do not expose the dimension
if TRUNC: X_all = X_all[:, :TRUNC]
X_sf = X_all[pos]
EX['sents_per_s'] = round(sp['sentences_per_s'], 2)
if not (TAG and '--with-speed' not in sys.argv): log('speed', f'bs{sp["bs"]}_2000texts', {k: sp[k] for k in ('sentences_per_s', 'est_sec_20k_x86', 'wall_s')}, n=sp['n'],
    notes=f'load_s={load_s:.1f}; loadavg1={os.getloadavg()[0]:.1f}; 1,897 rows + 103 repeats, longest first, bs 32, sym kwargs {SYM}')

# ---------------------------------------------------------------- zero-shot
S_zs = {}
if 'attr_zeroshot' in tasks:
    X_sfq = X_sf if QK == SYM else timed('encode zero-shot rows (query side)', lambda: enc([r['text'] for r in sf], QK))
    if TRUNC and QK != SYM: X_sfq = X_sfq[:, :TRUNC]
    D_cache = {}
    def desc_emb(descs):
        todo = [d for d in dict.fromkeys(descs) if d not in D_cache]
        if todo:
            D_cache.update(zip(todo, enc(todo, DK)[:, :TRUNC] if TRUNC else enc(todo, DK)))
        return np.stack([D_cache[d] for d in descs])
    def make_sim(Xrows, tag):
        Xn = l2(Xrows)
        def f(descs):
            S = Xn @ l2(desc_emb(descs)).T
            S_zs[tag] = S
            return S
        return f
    notes_zs = f'rows kwargs {QK}, descriptions kwargs {DK}, restricted to gold subject, no training'
    for tag, var, fn_ in (('describe', 'describe', H.describe), ('words', 'attr_words_only', lambda s, a: H.attr_words(a))):
        r = timed(f'zeroshot {var}', lambda: H.zeroshot_attr(make_sim(X_sfq, tag), sf, lex, desc_fn=fn_))
        if r: log('attr_zeroshot', var, r[0], len(sf), notes_zs)
    if QK != SYM:  # free extra: claims encoded symmetrically (no query side prompt), descriptions as before
        r = timed('zeroshot describe symrows', lambda: H.zeroshot_attr(make_sim(X_sf, 'describe_sym'), sf, lex))
        if r: log('attr_zeroshot', 'describe_rows_sym_encoding', r[0], len(sf), f'claims encoded with the sym kwargs {SYM} instead of the query kwargs; descriptions kwargs {DK}')

# ---------------------------------------------------------------- key retrieval
if 'key_retrieval' in tasks:
    m = timed('key_retrieval', lambda: H.key_retrieval(X_all, rows))
    if m: log('key_retrieval', 'cosine_k10', m, len(rows), f'all 1897 rows, sym kwargs {SYM}; tfidf_* keys are the harness char(3,5) reference')
    if cfg.get('extra_sym') and 'key_retrieval' in tasks and mid == 'lightonai/DenseOn':
        X2 = timed('encode extra_sym (all rows)', lambda: enc(texts, cfg['extra_sym']))
        if X2 is not None:
            m = timed('key_retrieval extra', lambda: H.key_retrieval(X2, rows))
            if m: log('key_retrieval', 'cosine_k10_document_prefix_both_sides', m, len(rows), f'all 1897 rows with kwargs {cfg["extra_sym"]} on both sides')

# ---------------------------------------------------------------- truth probes
if 'truth' in tasks:
    r = timed('truth_false', lambda: H.run_probe_false(X_all, rows, fall))
    if r: log('truth_false', 'LR_balanced_C1', r[0], len(rows), 'page_folds(rows), false-vs-rest')
    r = timed('truth_three', lambda: H.run_probe_three(X_all, rows, fall))
    if r: log('truth_three', 'LR_balanced_C1', r[0], len(rows), 'page_folds(rows), raw softmax')

# ---------------------------------------------------------------- kNN
if 'attr_knn' in tasks:
    r = timed('attr_knn', lambda: H.run_knn_attr(X_sf, sf, lex, fa))
    if r: log('attr_knn', 'k5', r[0], len(sf), 'page_folds(sf), restricted neighbour pool')

# ---------------------------------------------------------------- probe + hybrid + unseen (fitted fold models are recorded and reused)
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

subj_idx = defaultdict(list)
for j, (s, _) in enumerate(pairs): subj_idx[s].append(j)

def hybrid(models, folds, S, w=1.0):
    """z(probe log-proba over the SEEN gold-subject candidates) + w * z(zero-shot cosine over all candidates); unseen candidates get probe z = 0."""
    Xn, pred = l2(X_sf), np.empty(len(sf), dtype=object)
    for (tr, te), mdl in zip(folds, models):
        LP, cidx = mdl.predict_log_proba(Xn[te]), {c: i for i, c in enumerate(mdl.classes_)}
        for k, i in enumerate(te):
            P = subj_idx.get(sf[i]['facts'][0]['subject']) or list(range(len(pairs)))
            attrs = [pairs[j][1] for j in P]
            seen = [t for t, a in enumerate(attrs) if a in cidx]
            zp = np.zeros(len(P))
            if len(seen) > 1: zp[seen] = zs_z(LP[k, [cidx[attrs[t]] for t in seen]])
            pred[i] = attrs[int(np.argmax(zp + w * zs_z(S[i, P])))]
    return pred

HY = [('z_probe+z_zeroshot', 'describe', 1.0), ('z_probe+2*z_zeroshot', 'describe', 2.0), ('z_probe+z_zeroshot_words_only', 'words', 1.0)]
if 'attr_probe' in tasks:
    res = timed('attr_probe (page folds)', lambda: probe_recorded(fa))
    if res:
        (m, _), mods = res
        log('attr_probe', 'LR_C10', m, len(sf), 'page_folds(sf), restricted argmax')
        tc = H.train_counts(sf, fa)
        for name, tag, w in HY:
            if tag in S_zs:
                mh = H.attr_metrics(y_sf, hybrid(mods, fa, S_zs[tag], w), tc)
                log('attr_hybrid', name, mh, len(sf), f'page_folds(sf); z-scored over the gold subject candidates; unseen candidates probe z=0; zero-shot variant={tag}, weight {w:g}')

if 'attr_unseen' in tasks:
    res = timed('attr_unseen (attribute folds)', lambda: probe_recorded(fattr))
    if res:
        (m, _), mods = res
        log('attr_unseen', 'probe_alone_LR_C10', m, len(sf), 'attribute_folds(sf): every test attribute unseen, probe is 0 by construction')
        tc0 = H.train_counts(sf, fattr)
        for name, tag, w in HY:
            if tag in S_zs:
                mh = H.attr_metrics(y_sf, hybrid(mods, fattr, S_zs[tag], w), tc0)
                log('attr_unseen', 'hybrid_' + name, mh, len(sf), f'attribute_folds(sf); probe sees only OTHER attributes; unseen candidates probe z=0; zero-shot variant={tag}, weight {w:g}')
        if 'describe' in S_zs:
            mz = H.attr_metrics(y_sf, H.zeroshot_attr(lambda d: S_zs['describe'], sf, lex)[1], tc0)
            log('attr_unseen', 'zeroshot_alone_describe', mz, len(sf), 'zero-shot restricted argmax scored with the attribute_folds train_counts (all unseen)')

# ---------------------------------------------------------------- --selftest: hybrid() sanity (never writes with --dry)
if '--selftest' in sys.argv:
    (m_, _probe_pred), mods = probe_recorded(fa)
    S = S_zs['describe']
    pz = H.zeroshot_attr(lambda d: S, sf, lex)[1]
    assert list(hybrid(mods, fa, S, 1e6)) == list(pz), 'hybrid with a huge zero-shot weight must equal the zero-shot prediction'
    ph0, n_chk, ok_all = hybrid(mods, fa, S, 0.0), 0, True
    for (tr, te), mdl in zip(fa, mods):
        seen = set(mdl.classes_)
        for i in te:
            cand = H.candidates(lex, sf[i]['facts'][0]['subject'])
            if cand and all(c in seen for c in cand) and len(cand) > 1:
                n_chk += 1; ok_all &= (ph0[i] == _probe_pred[i])
    assert ok_all and n_chk > 500, (ok_all, n_chk)
    print(f'[{mid}] SELFTEST OK: w=inf equals zero-shot on all {len(sf)} rows; w=0 equals the probe on {n_chk} rows with all candidates seen', flush=True)

# ---------------------------------------------------------------- optional extra: classification-style embeddings for the probes (cfg extra_sym)
if cfg.get('extra_sym') and mid != 'lightonai/DenseOn' and '--no-extra' not in sys.argv and tasks & {'truth', 'attr_probe'}:
    kw2 = cfg['extra_sym']
    X2 = timed(f'encode extra {kw2}', lambda: enc(texts, kw2))
    if X2 is not None:
        X2sf = X2[pos]
        r = timed('extra attr_probe', lambda: H.run_probe_attr(X2sf, sf, lex, fa))
        if r: log('attr_probe', f'LR_C10_{VN(kw2)}', r[0], len(sf), f'page_folds(sf); embeddings with kwargs {kw2} instead of {SYM}')
        r = timed('extra truth_false', lambda: H.run_probe_false(X2, rows, fall))
        if r: log('truth_false', f'LR_balanced_C1_{VN(kw2)}', r[0], len(rows), f'embeddings with kwargs {kw2} instead of {SYM}')
        r = timed('extra truth_three', lambda: H.run_probe_three(X2, rows, fall))
        if r: log('truth_three', f'LR_balanced_C1_{VN(kw2)}', r[0], len(rows), f'embeddings with kwargs {kw2} instead of {SYM}')
        r = timed('extra key_retrieval', lambda: H.key_retrieval(X2, rows))
        if r: log('key_retrieval', f'cosine_k10_{VN(kw2)}', r, len(rows), f'embeddings with kwargs {kw2} instead of {SYM}')

np.savez_compressed(f'{OUT}/emb/{mid.replace("/", "__")}{"@" + TAG if TAG else ""}.npz', X_all=X_all)
print(f'[{mid}] ALL DONE in {time.time() - t_start:.0f}s', flush=True)
