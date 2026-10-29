"""w3 extra on CACHED embeddings: how much probe weight should the hybrid get?  python -I run_sweep.py <key> ...
score = w_probe * z(probe log-prob) + 1.0 * z(zero-shot cosine), unseen candidates neutral (z 0), zs=describe, raw embeddings.
Page folds (mostly seen attributes) and attribute folds (every test attribute unseen). w_probe=1 is the primary hybrid, not re-logged."""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/w3')
import run_model as R
from run_centered import speed_record
import time, traceback
import numpy as np
H = R.H
WEIGHTS = [0.0, 0.25, 0.5, 2.0]

def sweep(key):
    spec = R.SPECS[key]; MN = spec.get('name', spec['id']); sp = speed_record(MN)
    common = dict({k: sp[k] for k in ('tier', 'params_m', 'disk_mb', 'dim')}, sents_per_s=sp['sents_per_s'])
    z = np.load(f'{R.OUT}/emb/{key}.npz', allow_pickle=True)
    Xn = H._l2(z['X_all'][R.sf_pos]); S = Xn @ H._l2(z['D_describe']).T
    wr = H.ResultWriter(H.results_path(R.W)); notes0 = f"tier={spec['tier']}; hybrid probe-weight sweep, zero-shot weight 1, zs=describe, unseen=neutral, raw embeddings"
    for task, folds in (('attr_hybrid', H.page_folds(R.sf)), ('attr_unseen', H.attribute_folds(R.sf))):
        R.RecLR.log.clear(); H.run_probe_attr(z['X_all'][R.sf_pos], R.sf, R.lex, folds, C=10.0); models = list(R.RecLR.log); assert len(models) == len(folds)
        tc = H.train_counts(R.sf, folds)
        res = []
        for w in WEIGHTS:
            m = H.attr_metrics(R.y_sf, R.hybrid(models, folds, Xn, S, 'neutral', w_probe=w), tc)
            wr.add(R.W, MN, task, ('hybrid ' if task == 'attr_unseen' else '') + f'zs=describe;unseen=neutral;w_probe={w}', m, n=len(R.sf),
                   notes=notes0, **common)
            res.append(f'w={w}: {m["acc_all"]:.3f}')
        print(f'[{key}] {task}: ' + ' | '.join(res), flush=True)

if __name__ == '__main__':
    for k in sys.argv[1:]:
        try: sweep(k)
        except Exception: traceback.print_exc(); print(f'[{k}] SWEEP FAILED', flush=True)
