"""Extra truth-probe regularisation sweep on the CACHED sym embeddings (w9/emb/*.npz): truth_false / truth_three with C in (10, 100).
The harness default C=1 on unit-norm vectors is strongly regularised; this shows whether a looser probe changes the picture.
Usage: python -I csweep.py [<hf_id> ...]  (no model is loaded; sklearn only)"""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common')
import harness as H; H.set_threads(2)
import json, os, numpy as np
W = 'w9'; EMB = '/tmp/veridyct-emb/w9/emb'
rows, lex = H.load(); fall = H.page_folds(rows)
R = [json.loads(l) for l in open(H.results_path(W))]
writer = H.ResultWriter(H.results_path(W))
done = {(r['model'], r['task'], r['variant']) for r in R}
ids = sys.argv[1:] or sorted({r['model'] for r in R if r['task'] == 'speed'})
for mid in ids:
    f = f'{EMB}/{mid.replace("/", "__")}.npz'
    if not os.path.exists(f):
        print('no cache for', mid); continue
    X = np.load(f)['X_all']
    sp = next(r for r in R if r['model'] == mid and r['task'] == 'speed')
    ex = {k: sp[k] for k in ('params_m', 'disk_mb', 'dim', 'max_seq_length', 'sents_per_s') if k in sp}
    for C in (10.0, 100.0):
        v = f'LR_balanced_C{int(C)}'
        if (mid, 'truth_false', v) not in done:
            m, _ = H.run_probe_false(X, rows, fall, C=C)
            writer.add(W, mid, 'truth_false', v, m, n=len(rows), notes=f'page_folds(rows), false-vs-rest, C={C:g} (harness default is 1); cached sym embeddings', **ex)
            print(f'{mid} truth_false C={C:g}: auc={m["auc"]:.3f} ap={m["ap"]:.3f}', flush=True)
        if (mid, 'truth_three', v) not in done:
            m, _ = H.run_probe_three(X, rows, fall, C=C)
            writer.add(W, mid, 'truth_three', v, m, n=len(rows), notes=f'page_folds(rows), raw softmax, C={C:g} (harness default is 1); cached sym embeddings', **ex)
            print(f'{mid} truth_three C={C:g}: acc={m["acc"]:.3f} macro_f1={m["macro_f1"]:.3f} arena_best={m["arena_best"]:.3f}', flush=True)
