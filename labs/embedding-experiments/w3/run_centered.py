"""w3 extra pass on CACHED embeddings (no model is loaded): the same tasks with the mean embedding removed first.
    python -I run_centered.py <key> [<key> ...]
Why: anisotropic encoders (all cosines 0.7-1.0) make the harness's L2-normalised, C=10 logistic probe under-fit; subtracting the
mean vector (rows by the rows' mean, descriptions by the descriptions' mean; label-free, fitted on all 1,897 texts) tests that.
Variants are logged with the suffix ';centered'. Reuses the helpers of run_model.py (hybrid, RecLR, zstd) unchanged."""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/w3')
import run_model as R
import json, time, traceback
import numpy as np
H = R.H
SUF = ';centered'

def speed_record(model_id):
    recs = [json.loads(l) for l in open(H.results_path(R.W))]
    return [r for r in recs if r['model'] == model_id and r['task'] == 'speed' and str(r['variant']).startswith('bs=')][-1]

def centered(key):
    spec, t00 = R.SPECS[key], time.time()
    MN = spec.get('name', spec['id'])
    sp = speed_record(MN); base = {k: sp[k] for k in ('tier', 'params_m', 'disk_mb', 'dim')}
    common = dict(base, sents_per_s=sp['sents_per_s'])
    z = np.load(f'{R.OUT}/emb/{key}.npz', allow_pickle=True)
    X_all, D = z['X_all'], {k: z[k] for k in z.files if k.startswith('D_')}
    Xc, Dc = X_all - X_all.mean(0), {k: v - v.mean(0) for k, v in D.items()}
    rp, dp = spec.get('row_prefix', ''), spec.get('desc_prefix', '')
    pref = f"rows prompt={spec['row_prompt']!r}" if spec.get('row_prompt') else f'rows prefix={rp!r}'
    notes0 = f"tier={spec['tier']}; prefixes={pref}, descs prefix={dp!r}; embeddings mean-centered before the harness L2-normalises"
    wr = H.ResultWriter(H.results_path(R.W))
    log = lambda task, variant, m, n, notes='', t0=None, **ex: wr.add(
        R.W, MN, task, variant + SUF, m, n=n, notes=notes0 + (f'; {notes}' if notes else ''),
        **({'secs': round(time.time() - t0, 1)} if t0 else {}), **common, **ex)
    sf, lex, rows = R.sf, R.lex, R.rows
    X_sf = Xc[R.sf_pos]; Xn_sf = H._l2(X_sf)
    fa, fall, fat = H.page_folds(sf), H.page_folds(rows), H.attribute_folds(sf)
    S = {}
    for name, dkey, desc_fn in (('describe', 'D_describe', H.describe), ('attr_words_only', 'D_words', lambda s, a: H.attr_words(a))):
        Dn = H._l2(Dc[dkey])
        def sim(descs, Dn=Dn, name=name): S[name] = Xn_sf @ Dn.T; return S[name]
        m, _ = H.zeroshot_attr(sim, sf, lex, desc_fn=desc_fn); log('attr_zeroshot', name, m, len(sf))
        print(f'[{key}{SUF}] zeroshot {name}: acc={m["acc_all"]:.3f}', flush=True)
    m, _ = H.run_knn_attr(X_sf, sf, lex, fa, k=5); log('attr_knn', 'k=5', m, len(sf))
    print(f'[{key}{SUF}] knn acc={m["acc_all"]:.3f} ge5={m["acc_ge5"]:.3f}', flush=True)
    m = H.key_retrieval(Xc, rows); log('key_retrieval', 'cosine,k=10', m, len(rows))
    print(f'[{key}{SUF}] retrieval recall@10={m["recall_at_k"]:.3f} mrr={m["mrr"]:.3f}', flush=True)
    m, _ = H.run_probe_false(Xc, rows, fall); log('truth_false', 'C=1', m, len(rows)); print(f'[{key}{SUF}] false auc={m["auc"]:.3f}', flush=True)
    m, _ = H.run_probe_three(Xc, rows, fall); log('truth_three', 'C=1', m, len(rows))
    print(f'[{key}{SUF}] three acc={m["acc"]:.3f} arena_best={m["arena_best"]:.3f}', flush=True)
    t0 = time.time(); R.RecLR.log.clear()
    m, _ = H.run_probe_attr(X_sf, sf, lex, fa, C=10.0); models = list(R.RecLR.log); assert len(models) == len(fa)
    log('attr_probe', 'C=10', m, len(sf), f'LR max n_iter={R.lr_iters(models)}/3000', t0, lr_max_iter_used=R.lr_iters(models))
    print(f'[{key}{SUF}] probe acc={m["acc_all"]:.3f} ge5={m["acc_ge5"]:.3f} 1to4={m["acc_1to4"]:.3f} iters={R.lr_iters(models)}', flush=True)
    tc = H.train_counts(sf, fa)
    hyb = [('zs=describe;unseen=neutral', 'describe'), ('zs=attr_words_only;unseen=neutral', 'attr_words_only')]
    for name, sk in hyb:
        mm = H.attr_metrics(R.y_sf, R.hybrid(models, fa, Xn_sf, S[sk], 'neutral'), tc); log('attr_hybrid', name, mm, len(sf))
        print(f'[{key}{SUF}] hybrid {name}: all={mm["acc_all"]:.3f} ge5={mm["acc_ge5"]:.3f} 1to4={mm["acc_1to4"]:.3f} unseen={mm["acc_unseen"]:.3f}', flush=True)
    R.RecLR.log.clear()
    m, _ = H.run_probe_attr(X_sf, sf, lex, fat, C=10.0); models_t = list(R.RecLR.log); assert len(models_t) == len(fat)
    log('attr_unseen', 'probe_alone', m, len(sf), 'attribute_folds; 0 by construction')
    tct = H.train_counts(sf, fat); assert not tct.any()
    for name, sk in hyb:
        mm = H.attr_metrics(R.y_sf, R.hybrid(models_t, fat, Xn_sf, S[sk], 'neutral'), tct); log('attr_unseen', 'hybrid ' + name, mm, len(sf))
        print(f'[{key}{SUF}] UNSEEN hybrid {name}: acc={mm["acc_all"]:.3f}', flush=True)
    print(f'[{key}{SUF}] DONE in {time.time() - t00:.0f}s', flush=True)

if __name__ == '__main__':
    for k in sys.argv[1:]:
        try: centered(k)
        except Exception: traceback.print_exc(); print(f'[{k}{SUF}] FAILED', flush=True)
