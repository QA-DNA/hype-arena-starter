"""w10 extra (no model compute): re-score the saved conflict probs against a CLEAN target that drops 'different' pairs whose gold values are
actually compatible (same number differing only in op, bound satisfied by the other exact value, date at different granularity)."""
import sys, os, json, collections; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H
import numpy as np
rows, lex = H.load(); PR = H.same_key_pairs(rows)
def num(v): return v['value'] if isinstance(v.get('value'), (int, float)) and not isinstance(v.get('value'), bool) else None
def sat(op, bound, x):
    return {'le': x <= bound, 'lt': x < bound, 'ge': x >= bound, 'gt': x > bound}.get(op, False)
def compatible(v1, v2):
    """True when two gold values differ but do not contradict each other."""
    if v1.get('kind') != v2.get('kind'): return False
    if v1['kind'] == 'date':
        a, b = str(v1['value']), str(v2['value']); return a != b and (a.startswith(b) or b.startswith(a))
    n1, n2 = num(v1), num(v2)
    if n1 is None or n2 is None: return False
    o1, o2 = v1.get('op'), v2.get('op')
    if n1 == n2: return o1 != o2                      # same number, different op
    if o1 and not o2: return sat(o1, n1, n2)           # 'over 25' vs exactly 31
    if o2 and not o1: return sat(o2, n2, n1)
    return False
diff = [(k, not s) for k, (i, j, s) in enumerate(PR)]
comp = np.array([(not s) and compatible(rows[i]['facts'][0]['value'], rows[j]['facts'][0]['value']) for i, j, s in PR])
y = np.array([0 if s else 1 for _, _, s in PR]); keep = ~comp
ops = collections.Counter(r['facts'][0]['value'].get('op') for r in rows if len(r['facts']) == 1)
print('ops', dict(ops)); print(f'pairs {len(PR)}, different {int(y.sum())}, compatible-different {int(comp.sum())} -> clean n {int(keep.sum())} (pos {int(y[keep].sum())})')
if len(sys.argv) > 1 and sys.argv[1] == 'write':
    W = H.ResultWriter(H.results_path('w10'))
    for f in sorted(os.listdir('/tmp/veridyct-emb/w10')):
        if not f.startswith('probs_conflict_') or f.endswith('_swap.npy'): continue
        key = f[len('probs_conflict_'):-4]; P = np.load('/tmp/veridyct-emb/w10/' + f)
        recs = [json.loads(l) for l in open('/tmp/veridyct-emb/results/w10.jsonl')]
        rec = next(r for r in recs if r['task'] == 'nli_conflict' and r['variant'] == 'p_contra(i->j)' and r['model'].split('/')[-1].replace('nli-', '').replace('finecat-', 'finecat-') and key.replace('finecat-', '') in r['model'].replace('finecat-nli-', '').replace('tasksource/ModernBERT-base-nli', 'modernbert-nli').replace('tals/albert-base-vitaminc-mnli', 'albert-vitaminc'))
        pc = P[:, 2] if 'albert' not in key else P[:, 1]
        m = H.binary_metrics(y[keep], pc[keep]); print(key, rec['model'], f'clean auc {m["auc"]:.3f} (orig {rec["metrics"]["auc"]:.3f})')
        W.add('w10', rec['model'], 'nli_conflict', 'p_contra(i->j) CLEAN target (drops compatible-different pairs)', m, n=int(keep.sum()), notes=f'extra: {int(comp.sum())} of the {int(y.sum())} "different" pairs dropped because the gold values are compatible (op-only, bound satisfied, date granularity)', params_m=rec['params_m'], disk_mb=rec['disk_mb'])
if len(sys.argv) > 1 and sys.argv[1] == 'fn':
    import random
    key = sys.argv[2]; P = np.load(f'/tmp/veridyct-emb/w10/probs_conflict_{key}.npy'); pc = P[:, 2]
    fn = [k for k in range(len(PR)) if y[k] == 1 and not comp[k] and pc[k] < 0.3]
    print(len(fn), 'non-compatible FNs with pc<0.3 of', int(y.sum()), '; by kind:', collections.Counter(rows[PR[k][0]]['facts'][0]['value']['kind'] for k in fn))
    for k in random.Random(1).sample(fn, 10):
        i, j, _ = PR[k]; print(f'pc={pc[k]:.3f} {rows[i]["facts"][0]["attribute"]}\n   i: {rows[i]["text"]} [{rows[i]["facts"][0]["value"]}]\n   j: {rows[j]["text"]} [{rows[j]["facts"][0]["value"]}]')
