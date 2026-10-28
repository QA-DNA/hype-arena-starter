"""Interleaved speed recheck: all fast/mid models loaded at once, 2 round-robin rounds over the SAME 480 (text, other text) pairs,
bs 32, longest first, 1 warm-up batch per pass, 2 threads. Removes the run-to-run load drift of the in-sweep speed records."""
import sys, os, time, numpy as np
sys.path.insert(0, '/tmp/veridyct-emb/w4/scripts'); import nli_run as N
H = N.H
KEYS = ['ce-xsmall', 'ce-distilroberta', 'ce-minilm2-l6-h768', 'ce-small', 'ts-deberta-small-long-nli', 'ml-modernbert-base-zeroshot2',
        'ml-base-mnli-fever-anli', 'ml-base-zeroshot2', 'ce-base']
rows, lex = H.load(); P = H.same_key_pairs(rows)
ix = np.random.default_rng(7).choice(len(P), 480, replace=False)
A = [rows[P[k][0]]['text'] for k in ix]; B = [rows[P[k][1]]['text'] for k in ix]
S = {k: N.Scorer(k) for k in KEYS}
res = {k: [] for k in KEYS}; load = {k: [] for k in KEYS}
for rnd in range(2):
    for k in KEYS:
        _, wall = S[k].timed(A, B); res[k].append(len(A) / wall); load[k].append(os.getloadavg()[0])
        print(rnd, k, f'{len(A) / wall:.1f}', f'load {load[k][-1]:.1f}', flush=True)
wr = H.ResultWriter(H.results_path('w4'))
for k in KEYS:
    v = float(np.median(res[k]))
    wr.add('w4', k, 'speed', 'bs32-2threads-pairs-recheck-interleaved', dict(pairs_per_s=v, rounds=res[k], n_pairs=len(A), est_sec_20k_pairs_x86=20000 / v * 2.0), n=len(A),
           notes=f'interleaved round-robin recheck over {len(A)} seeded conflict pairs, 2 rounds (median), bs 32, longest first, 1 warm-up batch/pass, fp32 2 threads, mean load avg {np.mean(load[k]):.1f}',
           pairs_per_s=v, params_m=round(S[k].params_m, 2), disk_mb=round(S[k].disk_mb, 1))
print('RECHECK DONE', flush=True)
