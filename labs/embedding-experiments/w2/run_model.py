"""w2 embedding benchmark. usage: run_model.py <key> [--stages embed,cheap,lr]
embed: load model, timed speed pass (also the probe-view embeddings), other prefix views, description embeddings -> emb/<key>.npz
cheap: key_retrieval, attr_zeroshot, attr_knn, truth_false, truth_three (numpy/sklearn only)
lr:    attr_probe, attr_hybrid, attr_unseen (2 LR fits: page folds + attribute folds, shared by probe and hybrid)"""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(2)
import torch; torch.set_num_threads(2)
import json, os, time
import numpy as np
from sklearn.linear_model import LogisticRegression

OUT = '/tmp/veridyct-emb/w2'
BGE = 'Represent this sentence for searching relevant passages: '
S2P = 'Instruct: Given a web search query, retrieve relevant passages that answer the query.\nQuery: '
def V(p='', **kw): return dict(p=p, kw=kw)
def allv(**o): return {**dict(probe=V(), sym=V(), q=V(), d=V()), **o}
NOMICV = dict(probe=V('classification: '), sym=V('search_query: '), q=V('search_query: '), d=V('search_document: '))
CFG = {
 'granite-small': dict(id='ibm-granite/granite-embedding-small-english-r2', views=allv()),
 'nomic-v1.5': dict(id='nomic-ai/nomic-embed-text-v1.5', trc=True, views=NOMICV),
 'modernbert-embed': dict(id='nomic-ai/modernbert-embed-base', views=NOMICV),
 'gte-modernbert': dict(id='Alibaba-NLP/gte-modernbert-base', views=allv()),
 'granite-r2': dict(id='ibm-granite/granite-embedding-english-r2', views=allv()),
 'bge-large': dict(id='BAAI/bge-large-en-v1.5', views=allv(q=V(BGE))),
 'e5-large': dict(id='intfloat/e5-large-v2', views=allv(probe=V('query: '), sym=V('query: '), q=V('query: '), d=V('passage: '), d_alt=V('query: '))),
 'gte-large': dict(id='thenlper/gte-large', views=allv()),
 'mxbai-large': dict(id='mixedbread-ai/mxbai-embed-large-v1', views=allv(q=V(BGE))),
 'stella-400m': dict(id='NovaSearch/stella_en_400M_v5', trc=True, config_kwargs={'use_memory_efficient_attention': False, 'unpad_inputs': False},
                     views=allv(q=V(S2P))),
 'arctic-l-v2': dict(id='Snowflake/snowflake-arctic-embed-l-v2.0', views=allv(q=V('query: '))),
 'bge-m3': dict(id='BAAI/bge-m3', views=allv()),
 'jina-v3': dict(id='jinaai/jina-embeddings-v3', trc=True,
                 views=dict(probe=V(task='classification', prompt_name='classification'), sym=V(task='text-matching', prompt_name='text-matching'),
                            q=V(task='retrieval.query', prompt_name='retrieval.query'), d=V(task='retrieval.passage', prompt_name='retrieval.passage'),
                            d_alt=V(task='text-matching', prompt_name='text-matching'))),
}
rows, lex = H.load(); sf = H.single_fact_rows(rows); SF = np.array([r['idx'] for r in sf])
texts = [r['text'] for r in rows]; texts2000 = texts + texts[:103]
PAIRS = [(s, a) for s, d in lex['subjects'].items() for a in d['attributes']]
PS, PA = np.array([s for s, _ in PAIRS]), np.array([a for _, a in PAIRS], dtype=object)
DESC = {'desc': [H.describe(s, a) for s, a in PAIRS], 'words': [H.attr_words(a) for _, a in PAIRS]}
WR = H.ResultWriter(H.results_path('w2'))
t00 = time.time()
def log(*a): print(f'[{time.time() - t00:6.0f}s]', *a, flush=True)
def vnote(cfg): return '; '.join(f"{k}={v['p']!r}{v['kw'] or ''}" for k, v in cfg['views'].items())

def enc(model, ts, view, bs=32):
    return model.encode([view['p'] + t for t in ts], batch_size=bs, convert_to_numpy=True, normalize_embeddings=False,
                        show_progress_bar=False, **view['kw']).astype(np.float32)

# ------------------------------------------------------------------ embed
def load_model(key):
    from huggingface_hub import snapshot_download
    from sentence_transformers import SentenceTransformer
    cfg = CFG[key]; mid = cfg['id']
    kw = dict(trust_remote_code=cfg.get('trc', False), device='cpu', model_kwargs={'dtype': torch.float32})  # fp32 everywhere (ST 6 would load bf16 checkpoints in bf16)
    if 'config_kwargs' in cfg: kw['config_kwargs'] = cfg['config_kwargs']
    model = SentenceTransformer(mid, **kw)
    native = model.max_seq_length
    if native and native > 512: model.max_seq_length = 512
    params_m = sum(p.numel() for p in model.parameters()) / 1e6
    dim = model.get_sentence_embedding_dimension()
    import glob  # not snapshot_download(local_files_only): it raises IncompleteSnapshotError when some repo files were deliberately not fetched
    snap = sorted(glob.glob(os.path.join(os.environ['HF_HOME'], 'hub', 'models--' + mid.replace('/', '--'), 'snapshots', '*')))[-1]
    disk_mb = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(snap) for f in fs
                  if f.endswith(('.safetensors', '.bin', '.pt'))) / 1e6
    log(f'loaded {mid}: {params_m:.0f}M params, dim {dim}, max_seq {native}, weights {disk_mb:.0f} MB, dtype {next(model.parameters()).dtype}')
    return model, native, params_m, dim, disk_mb

def stage_speed2(key):
    """best of two further timed passes (the machine is shared; the first pass in stage_embed may have been contended)"""
    cfg = CFG[key]; model, native, params_m, dim, disk_mb = load_model(key)
    runs = [H.encode_speed(lambda b: enc(model, b, cfg['views']['probe']), texts2000) for _ in range(2)]
    sp = max(runs, key=lambda r: r['sentences_per_s']); sp['all_runs_sents_per_s'] = [r['sentences_per_s'] for r in runs]
    log(f"speed2: {[round(r['sentences_per_s'], 1) for r in runs]} sents/s")
    WR.add('w2', cfg['id'], 'speed', 'best_of_2_later', sp, n=2000, notes=f'second measurement, best of 2 passes; prefixes: {vnote(cfg)}',
           params_m=params_m, disk_mb=disk_mb, dim=dim, max_seq_length=native, sents_per_s=sp['sentences_per_s'])

def stage_embed(key):
    cfg = CFG[key]; mid = cfg['id']; V_ = cfg['views']
    if os.path.exists(f'{OUT}/emb/{key}.npz'): return log('embed cached')
    model, native, params_m, dim, disk_mb = load_model(key)
    store = {}
    def encp(batch):
        E = enc(model, batch, V_['probe']); store.update(zip(batch, E)); return E
    sp = H.encode_speed(encp, texts2000)
    log(f"speed pass done: {sp['sentences_per_s']:.1f} sents/s (wall {sp['wall_s']:.0f}s)")
    arrs = dict(Xp=np.stack([store[t] for t in texts]))
    if V_['sym'] != V_['probe']:
        arrs['Xs'] = enc(model, texts, V_['sym']); log('sym view done')
    if V_['q'] != V_['probe'] and V_['q'] != V_['sym']:
        arrs['Xq'] = enc(model, [texts[i] for i in SF], V_['q']); log('q view (single-fact rows) done')
    for dn in [n for n in ('d', 'd_alt') if n in V_]:
        for vn, descs in DESC.items():
            arrs[f'D_{dn}_{vn}'] = enc(model, descs, V_[dn])
    log('descriptions done')
    meta = dict(id=mid, params_m=params_m, dim=dim, disk_mb=disk_mb, max_seq_length=native, speed=sp, views=V_)
    json.dump(meta, open(f'{OUT}/emb/{key}.meta.json', 'w'), default=str)
    np.savez(f'{OUT}/emb/{key}.npz', **arrs)
    WR.add('w2', mid, 'speed', 'bs32_2threads_2000texts', sp, n=2000, notes=f'shared machine (8 workers), probe view; prefixes: {vnote(cfg)}',
           params_m=params_m, disk_mb=disk_mb, dim=dim, max_seq_length=native, sents_per_s=sp['sentences_per_s'])

# ------------------------------------------------------------------ shared
def load_emb(key):
    meta = json.load(open(f'{OUT}/emb/{key}.meta.json')); Z = dict(np.load(f'{OUT}/emb/{key}.npz'))
    cfg = CFG[key]; V_ = cfg['views']
    Xp = Z['Xp']; Xs = Z.get('Xs', Xp)
    Xq_sf = Z['Xq'] if 'Xq' in Z else (Xp if V_['q'] == V_['probe'] else Xs)[SF] if 'Xq' not in Z else None
    return meta, Z, Xp, Xs, Xq_sf

def make_rec(key, meta):
    cfg = CFG[key]; ex = dict(params_m=meta['params_m'], disk_mb=meta['disk_mb'], dim=meta['dim'])
    def add(task, variant, metrics, n, notes=''):
        WR.add('w2', cfg['id'], task, variant, metrics, n=n, notes=(notes + ' | ' if notes else '') + 'prefixes: ' + vnote(cfg), **ex)
        brief = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in metrics.items() if k in
                 ('acc_all', 'acc_ge5', 'acc_1to4', 'acc_unseen', 'auc', 'ap', 'recall_at_k', 'hit_at_k', 'mrr', 'macro_f1', 'arena_best', 'acc', 'tfidf_recall_at_k')}
        log(f'{task:14s} {variant:28s} {brief}')
    return add

def l2(X): return H._l2(X)

# ------------------------------------------------------------------ cheap
def stage_cheap(key):
    meta, Z, Xp, Xs, Xq_sf = load_emb(key); cfg = CFG[key]; V_ = cfg['views']; add = make_rec(key, meta)
    # key retrieval: primary = symmetric view; the probe view too when it differs
    m = H.key_retrieval(Xs, rows); add('key_retrieval', 'sym:' + V_['sym']['p'].strip(' :') if V_['sym']['p'] else 'sym:noprefix', m, len(rows), 'symmetric prefixes both sides')
    if V_['sym'] != V_['probe']:
        m = H.key_retrieval(Xp, rows); add('key_retrieval', 'probe_view', m, len(rows), 'probe-view embeddings both sides')
    # zero-shot
    Qn = l2(Xq_sf)
    for dn in [n for n in ('d', 'd_alt') if n in V_]:
        for vn, fn in (('desc', H.describe), ('words', lambda s, a: H.attr_words(a))):
            D = l2(Z[f'D_{dn}_{vn}'])
            m, _ = H.zeroshot_attr(lambda descs, D=D, vn=vn: (descs == DESC[vn]) and Qn @ D.T, sf, lex, desc_fn=fn)
            add('attr_zeroshot', ('describe' if vn == 'desc' else 'attr_words_only') + ('' if dn == 'd' else '+d_alt'), m, len(sf),
                'q=row text (query side), d=description (doc side)' + (' ; d_alt = query-style prefix on descriptions' if dn == 'd_alt' else ''))
    if V_['q'] != V_['probe'] and 'd' in V_:   # effect of the query-side prefix: probe-view row embeddings against the same descriptions
        m, _ = H.zeroshot_attr(lambda descs: l2(Xp[SF]) @ l2(Z['D_d_desc']).T, sf, lex)
        add('attr_zeroshot', 'describe+q_probe_view', m, len(sf), 'row embeddings from the probe view (no query-side prefix) vs the same descriptions')
    # kNN
    m, _ = H.run_knn_attr(Xp[SF], sf, lex, H.page_folds(sf), k=5); add('attr_knn', 'k=5', m, len(sf))
    # truth
    ft = H.page_folds(rows)
    m, _ = H.run_probe_false(Xp, rows, ft, C=1.0); add('truth_false', 'C=1', m, len(rows))
    m, _ = H.run_probe_three(Xp, rows, ft, C=1.0); add('truth_three', 'C=1', m, len(rows))

# ------------------------------------------------------------------ lr (probe, hybrid, unseen)
def fold_fits(X, folds, C=10.0):
    X, y = l2(X), H._attrs(sf); out = []
    for tr, te in folds:
        m = LogisticRegression(C=C, max_iter=3000).fit(X[tr], y[tr])
        out.append((te, m.classes_, m.predict_log_proba(X[te]), m.decision_function(X[te])))
    return out

def probe_pred(fits):
    pred = np.empty(len(sf), dtype=object)
    for te, cls, _, dec in fits: pred[te] = H._restricted_argmax(dec, cls, [sf[i] for i in te], lex)
    return pred

def zs(v): sd = v.std(); return (v - v.mean()) / (sd if sd > 1e-9 else 1.0)

def hybrid_pred(fits, S, w=1.0):
    """per row: candidate set = gold subject's lexicon attributes; probe log-prob (unseen candidates get the mean of the seen
    ones = neutral) and zero-shot cosine are each z-scored over the set, summed (1 : w); argmax."""
    pred = np.empty(len(sf), dtype=object)
    for te, cls, LP, _ in fits:
        cidx = {a: j for j, a in enumerate(cls)}
        for r_, i in enumerate(te):
            cols = np.flatnonzero(PS == sf[i]['facts'][0]['subject'])
            if cols.size == 0: cols = np.arange(len(PA))
            cand = PA[cols]
            pr = np.array([LP[r_, cidx[a]] if a in cidx else np.nan for a in cand], float); ok = ~np.isnan(pr)
            pr[~ok] = pr[ok].mean() if ok.any() else 0.0
            pred[i] = cand[int(np.argmax(zs(pr) + w * zs(S[i, cols])))]
    return pred

def stage_lr(key, verify=False):
    meta, Z, Xp, Xs, Xq_sf = load_emb(key); cfg = CFG[key]; V_ = cfg['views']; add = make_rec(key, meta)
    S = l2(Xq_sf) @ l2(Z['D_d_desc']).T   # (1467, 514) zero-shot cosines, primary description variant
    y = H._attrs(sf); fa, fu = H.page_folds(sf), H.attribute_folds(sf); X = Xp[SF]
    t0 = time.time(); fits = fold_fits(X, fa); log(f'LR fit (page folds) {time.time() - t0:.0f}s')
    pp = probe_pred(fits); tc = H.train_counts(sf, fa)
    if verify:
        m0, p0 = H.run_probe_attr(X, sf, lex, fa); assert list(pp) == list(p0), 'own probe fit differs from H.run_probe_attr'
        log('verified: own fit == H.run_probe_attr predictions')
    add('attr_probe', 'C=10', H.attr_metrics(y, pp, tc), len(sf), 'LR C=10 on probe view; derived from the fold fits shared with the hybrid (identical to H.run_probe_attr)')
    for w in (1.0, 2.0, 4.0):
        add('attr_hybrid', f'probe+zs w={w:g}' + (' (1:1)' if w == 1 else ''), H.attr_metrics(y, hybrid_pred(fits, S, w), tc), len(sf),
            'page folds; z(probe logP) + w*z(zs cosine) over gold-subject candidates; unseen candidates get mean probe logP')
    t0 = time.time(); fits100 = fold_fits(X, fa, C=100.0); log(f'LR fit C=100 {time.time() - t0:.0f}s')
    add('attr_probe', 'C=100', H.attr_metrics(y, probe_pred(fits100), tc), len(sf), 'extra variant, weaker regularisation (the spec probe is C=10)')
    for w in (1.0, 2.0):
        add('attr_hybrid', f'C=100 probe+zs w={w:g}', H.attr_metrics(y, hybrid_pred(fits100, S, w), tc), len(sf), 'page folds; hybrid built on the C=100 probe (extra variant)')
    t0 = time.time(); fitu = fold_fits(X, fu); log(f'LR fit (attribute folds) {time.time() - t0:.0f}s'); tu = H.train_counts(sf, fu)
    assert (tu == 0).all()
    add('attr_unseen', 'probe_only', H.attr_metrics(y, probe_pred(fitu), tu), len(sf), 'leave-attribute-out; 0 by construction')
    for w in (1.0, 2.0, 4.0):
        add('attr_unseen', f'hybrid w={w:g}' + (' (1:1)' if w == 1 else ''), H.attr_metrics(y, hybrid_pred(fitu, S, w), tu), len(sf), 'leave-attribute-out')

if __name__ == '__main__':
    key = sys.argv[1]; stages = (sys.argv[sys.argv.index('--stages') + 1] if '--stages' in sys.argv else 'embed,cheap,lr').split(',')
    for st in stages:
        t0 = time.time(); log(f'== {key} stage {st}')
        {'embed': stage_embed, 'speed2': stage_speed2, 'cheap': stage_cheap, 'lr': lambda k: stage_lr(k, verify='verify' in sys.argv)}[st](key)
        log(f'== {key} stage {st} took {time.time() - t0:.0f}s')
