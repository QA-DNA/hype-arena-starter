"""w3 runner, ONE model per process:  python -I run_model.py <key>   (keys in SPECS).
Runs speed (capturing the embeddings in the timed pass), then every task, appending to /tmp/veridyct-emb/results/w3.jsonl
through the harness ResultWriter. Embeddings are cached in /tmp/veridyct-emb/w3/emb/<key>.npz."""
import os; os.environ['HF_HOME'] = '/tmp/veridyct-emb/w3/hf'  # w3's own cache, set before set_threads' setdefault
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H; H.set_threads(2)
import torch; torch.set_num_threads(2)
import json, time, traceback, warnings
import numpy as np
from sklearn.linear_model import LogisticRegression
warnings.filterwarnings('ignore')

W, OUT = 'w3', '/tmp/veridyct-emb/w3'
INSTR = 'Instruct: Given a sentence about a company, retrieve the attribute it states\nQuery: '
ST = 'sentence-transformers/'
QKW = dict(model_kwargs=dict(dtype=torch.float32), tokenizer_kwargs=dict(padding_side='left'))
SPECS = {  # key -> spec; tier = legal-risk tier from the brief
    'potion-base-8M': dict(id='minishlab/potion-base-8M', kind='m2v', tier='SAFE'),
    'potion-base-32M': dict(id='minishlab/potion-base-32M', kind='m2v', tier='SAFE'),
    'potion-retrieval-32M': dict(id='minishlab/potion-retrieval-32M', kind='m2v', tier='SAFE'),
    'static-retrieval-mrl-en-v1': dict(id=ST + 'static-retrieval-mrl-en-v1', kind='st', tier='SAFE'),
    'static-similarity-mrl-multilingual-v1': dict(id=ST + 'static-similarity-mrl-multilingual-v1', kind='st', tier='SAFE'),
    'glove-6B-300d': dict(id=ST + 'average_word_embeddings_glove.6B.300d', kind='st', tier='SAFE'),
    'tfidf-lsa300': dict(id='tfidf-char_wb2-5+word1-2->TruncatedSVD300', kind='lsa', tier='SAFE (non-neural reference)'),
    'tfidf-rp512': dict(id='tfidf-char_wb2-5+word1-2->SparseRandomProjection512', kind='rp', tier='SAFE (non-neural reference)'),
    'multilingual-e5-small': dict(id='intfloat/multilingual-e5-small', kind='st', tier='GREY', row_prefix='query: ',
                                  desc_prefix='query: ', alt_desc_prefix='passage: '),
    'paraphrase-multilingual-MiniLM-L12-v2': dict(id=ST + 'paraphrase-multilingual-MiniLM-L12-v2', kind='st', tier='GREY'),
    'Qwen3-Embedding-0.6B': dict(id='Qwen/Qwen3-Embedding-0.6B', kind='st', tier='RISKY', row_prompt=INSTR, bs=16, st_kwargs=QKW),
    'Qwen3-Embedding-0.6B-noprompt': dict(id='Qwen/Qwen3-Embedding-0.6B', name='Qwen/Qwen3-Embedding-0.6B (no instruction)', kind='st',
                                          tier='RISKY', bs=16, st_kwargs=QKW),
    'embeddinggemma-300m': dict(id='google/embeddinggemma-300m', kind='st', tier='RISKY'),
    'nomic-embed-text-v2-moe': dict(id='nomic-ai/nomic-embed-text-v2-moe', kind='st', tier='RISKY', row_prefix='search_query: ',
                                    desc_prefix='search_document: ', alt_desc_prefix='search_query: ',
                                    st_kwargs=dict(trust_remote_code=True), shim_ext_mask=True),
}

# ---------------------------------------------------------------- data
rows, lex = H.load(); sf = H.single_fact_rows(rows)
texts_all, texts_sf = [r['text'] for r in rows], [r['text'] for r in sf]
sf_pos = [r['idx'] for r in sf]                       # idx == position in rows
texts_2000 = texts_all + texts_all[:103]              # 1,897 texts + 103 repeats
pairs = [(s, a) for s, d in lex['subjects'].items() for a in d['attributes']]
ps, pa = np.array([s for s, _ in pairs]), np.array([a for _, a in pairs], dtype=object)
y_sf = np.array([r['facts'][0]['attribute'] for r in sf], dtype=object)
assert all(r['facts'][0]['subject'] in lex['subjects'] for r in sf)
sub_cols = {s: np.flatnonzero(ps == s) for s in lex['subjects']}

# ---------------------------------------------------------------- model loading
def snapshot_mb(model_id):
    """Size of the weights + tokenizer + config actually needed at runtime: onnx/openvino variants were not downloaded, and a
    duplicate pytorch_model.bin next to model.safetensors is not counted."""
    base = f"{os.environ['HF_HOME']}/hub/models--{model_id.replace('/', '--')}/snapshots"
    p = os.path.join(base, sorted(os.listdir(base))[-1]); tot = 0
    for d, _, fs in os.walk(p):
        for f in fs:
            if f.startswith('.') or f == 'README.md' or (f == 'pytorch_model.bin' and 'model.safetensors' in fs): continue
            tot += os.path.getsize(os.path.realpath(os.path.join(d, f)))
    return tot / 1e6

def load_model(key, spec):
    """-> (enc_rows, enc_desc, enc_desc_alt|None, info). enc_* take list[str] -> ndarray."""
    kind, bs = spec['kind'], spec.get('bs', 32)
    rp, dp, ap = spec.get('row_prefix', ''), spec.get('desc_prefix', ''), spec.get('alt_desc_prefix')
    if kind == 'm2v':
        from model2vec import StaticModel
        m = StaticModel.from_pretrained(spec['id'])
        raw = lambda t, prompt=None: np.asarray(m.encode(list(t), show_progress_bar=False), dtype=np.float32)
        emb = m.embedding
        info = dict(params_m=(emb.size + (m.weights.size if getattr(m, 'weights', None) is not None else 0)) / 1e6,
                    dim=int(emb.shape[1]), max_seq_length=512, vocab=int(emb.shape[0]), tokenizer_vocab=len(m.tokenizer.get_vocab()),
                    disk_mb=snapshot_mb(spec['id']))
    elif kind == 'st':
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(spec['id'], device='cpu', **spec.get('st_kwargs', {}))
        raw = lambda t, prompt=None: m.encode(list(t), batch_size=bs, show_progress_bar=False, convert_to_numpy=True,
                                              **({'prompt': prompt} if prompt else {}))
        if spec.get('shim_ext_mask'):  # transformers 5 dropped PreTrainedModel.get_extended_attention_mask; nomic's remote code still calls it
            def _ext(self, attention_mask, input_shape, device=None, dtype=None):  # the 4.x non-decoder behaviour: additive (b,1,1,s) mask
                dt = dtype or self.dtype
                return (1.0 - attention_mask[:, None, None, :].to(dt)) * torch.finfo(dt).min
            type(m[0].model).get_extended_attention_mask = _ext
            t1 = 'search_query: Holdan started at Hooly on 12 January 2026.'
            a, b = m.encode([t1])[0], m.encode([t1, 'search_query: ' + 'a much longer padding sentence ' * 10])[0]
            cos = float(a @ b / np.linalg.norm(a) / np.linalg.norm(b)); print(f'[{key}] shim padding check cos={cos:.6f}', flush=True)
            assert cos > 0.999, f'shim changes the embedding when padded: cos={cos}'
        first = m[0]
        voc = getattr(getattr(first, 'embedding', None), 'num_embeddings', None) or getattr(getattr(first, 'emb_layer', None), 'num_embeddings', None)
        info = dict(params_m=sum(p.numel() for p in m.parameters()) / 1e6, dim=int(m.get_sentence_embedding_dimension()),
                    max_seq_length=int(m.max_seq_length) if m.max_seq_length and np.isfinite(m.max_seq_length) else None, disk_mb=snapshot_mb(spec['id']),
                    dtype=str(next(m.parameters()).dtype).replace('torch.', ''), n_modules=len(m))
        if voc: info['vocab'] = int(voc)
    else:  # non-neural references: unsupervised TF-IDF (+ SVD / random projection) fitted on the 1,897 texts, label-free
        import joblib
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import make_union
        from sklearn.decomposition import TruncatedSVD
        from sklearn.random_projection import SparseRandomProjection
        vec = make_union(TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5)), TfidfVectorizer(ngram_range=(1, 2)))
        T = vec.fit_transform(texts_all)
        red = (TruncatedSVD(300, random_state=0) if kind == 'lsa' else SparseRandomProjection(512, dense_output=True, random_state=0)).fit(T)
        raw = lambda t, prompt=None: np.asarray(red.transform(vec.transform(list(t))), dtype=np.float32)
        os.makedirs(f'{OUT}/emb', exist_ok=True); joblib.dump((vec, red), f'{OUT}/emb/{key}.joblib')
        comp = red.components_.size if kind == 'lsa' else red.components_.shape[0] * red.components_.shape[1]
        info = dict(params_m=comp / 1e6, dim=raw(texts_all[:2]).shape[1], max_seq_length=None, vocab=int(T.shape[1]),
                    disk_mb=os.path.getsize(f'{OUT}/emb/{key}.joblib') / 1e6)
    enc_rows = lambda t: raw([rp + x for x in t], prompt=spec.get('row_prompt'))
    enc_desc = lambda t: raw([dp + x for x in t])
    enc_alt = (lambda t: raw([ap + x for x in t])) if ap is not None else None
    return enc_rows, enc_desc, enc_alt, info

# ---------------------------------------------------------------- probe recording + hybrid
class RecLR(LogisticRegression):
    """Identical to LogisticRegression; remembers every fitted instance so the hybrid reuses the harness's own fits."""
    log = []
    def fit(self, X, y, *a, **k):
        r = super().fit(X, y, *a, **k); RecLR.log.append(self); return r
H.LogisticRegression = RecLR

def zstd(v):
    """Standardise over the finite entries (population std); NaN -> 0; <2 finite or zero spread -> all 0."""
    v = np.asarray(v, float); f = np.isfinite(v); out = np.zeros(len(v))
    if f.sum() > 1 and v[f].std() > 1e-9: out[f] = (v[f] - v[f].mean()) / v[f].std()
    return out

def hybrid(models, folds, Xn, S, unseen='neutral', w_probe=1.0, w_zs=1.0):
    """Per fold: z(probe log-prob) + z(zero-shot cosine) over the gold subject's lexicon attributes, restricted argmax.
    A candidate the fold's probe never saw has no log-prob: 'neutral' = z 0 (probe has no opinion; standardised over the seen
    candidates only), 'veto' = the row's lowest log-prob over ALL the probe's classes (the probe treats it as impossible)."""
    pred = np.empty(len(sf), dtype=object)
    for m, (tr, te) in zip(models, folds):
        assert set(m.classes_) == set(y_sf[tr]), 'recorded LR does not match the fold'
        LP, ci = m.predict_log_proba(Xn[te]), {c: j for j, c in enumerate(m.classes_)}
        for k, i in enumerate(te):
            cols = sub_cols[sf[i]['facts'][0]['subject']]; attrs = pa[cols]
            lp = np.array([LP[k, ci[a]] if a in ci else np.nan for a in attrs])
            if unseen == 'veto': lp[~np.isfinite(lp)] = LP[k].min()
            pred[i] = attrs[int(np.argmax(w_probe * zstd(lp) + w_zs * zstd(S[i, cols])))]
    return pred

def lr_iters(models): return int(max(int(np.max(m.n_iter_)) for m in models))

# ---------------------------------------------------------------- main
def main(key):
    spec, t00 = SPECS[key], time.time()
    MN = spec.get('name', spec['id'])  # name in the results file (== HF id unless a variant of the same checkpoint)
    wr = H.ResultWriter(H.results_path(W))
    tier = spec['tier']
    rp, dp = spec.get('row_prefix', ''), spec.get('desc_prefix', '')
    pref = f"rows prompt={spec['row_prompt']!r}" if spec.get('row_prompt') else f'rows prefix={rp!r}'
    notes0 = f"tier={tier}; prefixes={pref}, descs prefix={dp!r}"
    try:
        enc_rows, enc_desc, enc_alt, info = load_model(key, spec)
    except Exception as e:
        traceback.print_exc()
        wr.add(W, MN, 'speed', 'load_failed', {'error': f'{type(e).__name__}: {str(e)[:300]}'}, notes=f'FAILED to load; {notes0}',
               tier=tier, status='failed')
        print(f'[{key}] LOAD FAILED', flush=True); return
    print(f'[{key}] loaded in {time.time() - t00:.1f}s info={info}', flush=True)
    base = dict(tier=tier, params_m=info['params_m'], disk_mb=info['disk_mb'], dim=info['dim'])
    cache = f'{OUT}/emb/{key}.npz'; os.makedirs(f'{OUT}/emb', exist_ok=True)
    # ---- embeddings + speed in ONE timed pass: encode_fn stores each text's vector, the pass is the harness's own
    if os.path.exists(cache):
        z = np.load(cache, allow_pickle=True); X_all, D = z['X_all'], {k: z[k] for k in z.files if k.startswith('D_')}
        sents = float(z['sents_per_s']); print(f'[{key}] embeddings from cache', flush=True)
    else:
        store, nb, tb = {}, [0], time.time()
        def cap(batch):
            E = enc_rows(batch)
            for t, e in zip(batch, E): store[t] = e
            nb[0] += 1
            if nb[0] % 10 == 0 and time.time() - tb > 20: print(f'[{key}] speed-pass batch {nb[0]} elapsed {time.time() - tb:.0f}s', flush=True)
            return E
        bs = spec.get('bs', 32)
        sp = H.encode_speed(cap, texts_2000, bs=bs)
        passes = [sp]
        if sp['wall_s'] < 5:  # fast model: median of 3 passes (a single sub-second pass is noise on a shared machine)
            passes += [H.encode_speed(cap, texts_2000, bs=bs) for _ in range(2)]
            sp = sorted(passes, key=lambda p: p['wall_s'])[1]
        sents = sp['sentences_per_s']
        X_all = np.stack([store[t] for t in texts_all]).astype(np.float64)
        speed_notes = f"{notes0}; bs={bs}; 2,000 texts (1,897 + 103 repeats) longest first, one warm-up batch; rows encoded " \
                      f"{'WITH the instruction prompt' if spec.get('row_prompt') else 'as the row encoder'}; passes={len(passes)} (median)"
        extra = {k: v for k, v in info.items() if k not in base}
        wr.add(W, MN, 'speed', f'bs={bs}', sp, n=len(texts_2000), notes=speed_notes, sents_per_s=sents, **base, **extra)
        print(f'[{key}] speed {sents:.1f} sents/s ({sp["wall_s"]:.1f}s wall)', flush=True)
        pairs_desc = [H.describe(s, a) for s, a in pairs]; words = [H.attr_words(a) for _, a in pairs]
        D = {}
        for name, enc, tt in (('D_describe', enc_desc, pairs_desc), ('D_words', enc_desc, words), ('D_describe_alt', enc_alt, pairs_desc),
                              ('D_words_alt', enc_alt, words)):
            if enc is None: continue
            u = list(dict.fromkeys(tt)); E = dict(zip(u, enc(u))); D[name] = np.stack([E[t] for t in tt]).astype(np.float64)
        np.savez(cache, X_all=X_all, sents_per_s=sents, **D)
        print(f'[{key}] embeddings cached ({time.time() - t00:.0f}s since start)', flush=True)
    common = dict(base, sents_per_s=sents)
    X_sf = X_all[sf_pos]; Xn_sf = H._l2(X_sf); Xrow_n = Xn_sf
    fa = H.page_folds(sf); fall = H.page_folds(rows); fat = H.attribute_folds(sf)

    def log(task, variant, m, n, notes='', t0=None, **ex):
        wr.add(W, MN, task, variant, m, n=n, notes=f'{notes0}{"; " + notes if notes else ""}',
               **({'secs': round(time.time() - t0, 1)} if t0 else {}), **common, **ex)

    # ---- attr_zeroshot (keeps S for the hybrid)
    S, zs_acc = {}, {}
    for name, dkey, desc_fn in (('describe', 'D_describe', H.describe), ('attr_words_only', 'D_words', lambda s, a: H.attr_words(a)),
                                ('describe|desc=alt_prefix', 'D_describe_alt', H.describe),
                                ('attr_words_only|desc=alt_prefix', 'D_words_alt', lambda s, a: H.attr_words(a))):
        if dkey not in D: continue
        t0 = time.time(); Dn = H._l2(D[dkey])
        def sim(descs, Dn=Dn, name=name):
            assert len(descs) == len(Dn); S[name] = Xrow_n @ Dn.T; return S[name]
        m, zp = H.zeroshot_attr(sim, sf, lex, desc_fn=desc_fn)
        zs_acc[name] = m['acc_all']
        log('attr_zeroshot', name, m, len(sf), 'cosine(row, description) restricted to the gold subject', t0)
        print(f'[{key}] zeroshot {name}: acc={m["acc_all"]:.3f}', flush=True)
    # ---- attr_knn
    t0 = time.time(); m, _ = H.run_knn_attr(X_sf, sf, lex, fa, k=5); log('attr_knn', 'k=5', m, len(sf), t0=t0)
    print(f'[{key}] knn acc={m["acc_all"]:.3f} ge5={m["acc_ge5"]:.3f}', flush=True)
    # ---- key_retrieval
    t0 = time.time(); m = H.key_retrieval(X_all, rows); log('key_retrieval', 'cosine,k=10', m, len(rows), t0=t0)
    print(f'[{key}] retrieval recall@10={m["recall_at_k"]:.3f} (tfidf {m["tfidf_recall_at_k"]:.3f}) mrr={m["mrr"]:.3f}', flush=True)
    # ---- truth probes
    t0 = time.time(); m, _ = H.run_probe_false(X_all, rows, fall); log('truth_false', 'C=1', m, len(rows), t0=t0)
    print(f'[{key}] false-vs-rest auc={m["auc"]:.3f} ap={m["ap"]:.3f}', flush=True)
    t0 = time.time(); m, _ = H.run_probe_three(X_all, rows, fall); log('truth_three', 'C=1', m, len(rows), t0=t0)
    print(f'[{key}] three-class acc={m["acc"]:.3f} macro_f1={m["macro_f1"]:.3f} arena_best={m["arena_best"]:.3f}', flush=True)
    # ---- attr_probe (page folds) + hybrid, reusing the probe's own fits
    t0 = time.time(); RecLR.log.clear()
    m, probe_pred = H.run_probe_attr(X_sf, sf, lex, fa, C=10.0); models = list(RecLR.log); assert len(models) == len(fa)
    log('attr_probe', 'C=10', m, len(sf), f'LR lbfgs max n_iter used={lr_iters(models)}/3000', t0, lr_max_iter_used=lr_iters(models))
    print(f'[{key}] probe acc={m["acc_all"]:.3f} ge5={m["acc_ge5"]:.3f} 1to4={m["acc_1to4"]:.3f} ({time.time() - t0:.0f}s, iters={lr_iters(models)})', flush=True)
    tc = H.train_counts(sf, fa)
    hyb = [('zs=describe;unseen=neutral', 'describe', 'neutral'), ('zs=describe;unseen=veto', 'describe', 'veto'),
           ('zs=attr_words_only;unseen=neutral', 'attr_words_only', 'neutral')]
    if 'describe|desc=alt_prefix' in S: hyb.append(('zs=describe|desc=alt_prefix;unseen=neutral', 'describe|desc=alt_prefix', 'neutral'))
    for name, sk, un in hyb:
        t0 = time.time(); pred = hybrid(models, fa, Xn_sf, S[sk], un)
        mm = H.attr_metrics(y_sf, pred, tc)
        log('attr_hybrid', name, mm, len(sf), 'z(probe logp)+z(zero-shot cos) over the gold subject candidates, page folds', t0)
        print(f'[{key}] hybrid {name}: all={mm["acc_all"]:.3f} ge5={mm["acc_ge5"]:.3f} 1to4={mm["acc_1to4"]:.3f} unseen={mm["acc_unseen"]:.3f}', flush=True)
    # one-off consistency checks (cheap): probe weight 0 == zero-shot; zero-shot weight 0 + veto == probe alone, on every row
    # that has at least one candidate the fold's probe has seen (otherwise H's probe falls back to an unrestricted argmax)
    p0 = hybrid(models, fa, Xn_sf, S['describe'], 'neutral', w_probe=0.0)
    p1 = hybrid(models, fa, Xn_sf, S['describe'], 'veto', w_zs=0.0)
    zs_pred = H.zeroshot_attr(lambda d: S['describe'], sf, lex)[1]
    seen_any = np.zeros(len(sf), bool)
    for m_, (_, te_) in zip(models, fa):
        cs = set(m_.classes_)
        for i in te_: seen_any[i] = any(a in cs for a in pa[sub_cols[sf[i]['facts'][0]['subject']]])
    chk = dict(hybrid_w_probe0_eq_zeroshot=float(np.mean(p0 == np.array(zs_pred, dtype=object))),
               hybrid_veto_w_zs0_eq_probe_on_seen_rows=float(np.mean((p1 == np.array(probe_pred, dtype=object))[seen_any])),
               rows_without_seen_candidate=int((~seen_any).sum()))
    print(f'[{key}] consistency {chk}', flush=True)
    assert chk['hybrid_w_probe0_eq_zeroshot'] > 0.99 and chk['hybrid_veto_w_zs0_eq_probe_on_seen_rows'] > 0.99, chk
    # ---- attr_unseen: leave-attribute-out
    t0 = time.time(); RecLR.log.clear()
    m, _ = H.run_probe_attr(X_sf, sf, lex, fat, C=10.0); models_t = list(RecLR.log); assert len(models_t) == len(fat)
    log('attr_unseen', 'probe_alone', m, len(sf), f'attribute_folds; 0 by construction; LR max n_iter={lr_iters(models_t)}', t0)
    tct = H.train_counts(sf, fat); assert not tct.any()
    for name, sk, un in hyb:
        pred = hybrid(models_t, fat, Xn_sf, S[sk], un); mm = H.attr_metrics(y_sf, pred, tct)
        log('attr_unseen', 'hybrid ' + name, mm, len(sf), 'attribute_folds (leave-attribute-out)')
        print(f'[{key}] UNSEEN hybrid {name}: acc={mm["acc_all"]:.3f}', flush=True)
    print(f'[{key}] DONE in {time.time() - t00:.0f}s', flush=True)

if __name__ == '__main__':
    for k in sys.argv[1:]:
        try: main(k)
        except Exception:
            traceback.print_exc()
            try: H.ResultWriter(H.results_path(W)).add(W, SPECS[k].get('name', SPECS[k]['id']), 'speed', 'run_failed', {'error': traceback.format_exc()[-400:]},
                                                      notes=f'FAILED mid-run; tier={SPECS[k]["tier"]}', status='failed')
            except Exception: pass
