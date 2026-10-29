"""which models beat the TF-IDF references, and by how much (reads results/w2.jsonl, last record wins)"""
import json
R = {}
for line in open('/tmp/veridyct-emb/results/w2.jsonl'):
    r = json.loads(line); R[(r['model'], r['task'], r['variant'])] = r
S = lambda m: m.split('/')[-1]
def beats(name, task, variant, key, ref, higher=True):
    xs = sorted(((r['metrics'][key], S(m)) for (m, t, v), r in R.items() if t == task and v == variant and r['metrics'].get(key) is not None), reverse=True)
    win = [(n, round(x - ref, 3)) for x, n in xs if x > ref]
    print(f'{name}: ref {ref}; {len(win)}/{len(xs)} beat; best {xs[0][1]} {xs[0][0]:.3f} ({xs[0][0] - ref:+.3f}); winners {win}')
beats('probe C=10 all', 'attr_probe', 'C=10', 'acc_all', 0.873); beats('probe C=10 ge5', 'attr_probe', 'C=10', 'acc_ge5', 0.961)
beats('probe C=100 all', 'attr_probe', 'C=100', 'acc_all', 0.873); beats('probe C=100 ge5', 'attr_probe', 'C=100', 'acc_ge5', 0.961)
beats('knn all', 'attr_knn', 'k=5', 'acc_all', 0.873); beats('knn ge5', 'attr_knn', 'k=5', 'acc_ge5', 0.961)
beats('zeroshot describe (vs TF-IDF all)', 'attr_zeroshot', 'describe', 'acc_all', 0.873)
beats('hybrid 1:1 all', 'attr_hybrid', 'probe+zs w=1 (1:1)', 'acc_all', 0.873); beats('hybrid C=100 1:1 all', 'attr_hybrid', 'C=100 probe+zs w=1', 'acc_all', 0.873)
beats('hybrid 1:1 ge5', 'attr_hybrid', 'probe+zs w=1 (1:1)', 'acc_ge5', 0.961)
beats('hybrid 1:1 unseen (TF-IDF 0)', 'attr_hybrid', 'probe+zs w=1 (1:1)', 'acc_unseen', 0.0)
beats('truth_false AUC', 'truth_false', 'C=1', 'auc', 0.633); beats('truth_three arena_best', 'truth_three', 'C=1', 'arena_best', 0.687)
kr = {}
for (m, t, v), r in R.items():
    if t == 'key_retrieval': kr.setdefault(S(m), []).append((round(r['metrics']['recall_at_k'], 3), v))
print('key_retrieval ref 0.666:', {m: sorted(v, reverse=True) for m, v in kr.items()})
