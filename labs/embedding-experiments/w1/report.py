"""Markdown tables from /tmp/veridyct-emb/results/w1.jsonl (+ TF-IDF reference).  python -I report.py"""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common')
import harness as H; H.set_threads(2)
import json, os
R = [json.loads(l) for l in open('/tmp/veridyct-emb/results/w1.jsonl')]
ref_f = '/tmp/veridyct-emb/w1/tfidf_ref.json'
if not os.path.exists(ref_f):
    rows, lex = H.load(); B = H.tfidf_baseline(rows, lex); json.dump(B, open(ref_f, 'w'), default=float)
REF = json.load(open(ref_f))
short = lambda m: m.split('/')[-1]
models = list(dict.fromkeys(r['model'] for r in R))
def get(model, task, variant=None):
    for r in R:
        if r['model'] == model and r['task'] == task and (variant is None or r['variant'] == variant):
            return r
f3 = lambda x: '-' if x is None else f'{x:.3f}'
def table(title, cols, rows_fn, sort_key=None, ref=None):
    out = []
    for m in models:
        v = rows_fn(m)
        if v is not None: out.append((m, v))
    if sort_key is not None: out.sort(key=lambda t: -(t[1][sort_key] or -1))
    print(f'\n### {title}\n| model | ' + ' | '.join(cols) + ' |\n|---|' + '---|' * len(cols))
    if ref: print(f'| TF-IDF ref | ' + ' | '.join(ref) + ' |')
    for m, v in out: print(f'| {short(m)} | ' + ' | '.join(f3(x) for x in v) + ' |')
    return out

def mt(model, task, variant, *keys):
    r = get(model, task, variant)
    return None if r is None else [r['metrics'].get(k) for k in keys]

print('TF-IDF ref', REF)
A = REF['attr']; Fz = REF['false']
top = {}
top['attr_probe'] = table('attr_probe (LR C=10, page folds)', ['acc_all', 'ge5', '1to4', 'unseen'], lambda m: mt(m, 'attr_probe', 'LR_C10', 'acc_all', 'acc_ge5', 'acc_1to4', 'acc_unseen'), 0,
      ref=[f3(A['acc_all']), f3(A['acc_ge5']), f3(A['acc_1to4']), f3(A['acc_unseen'])])
top['attr_knn'] = table('attr_knn (k=5)', ['acc_all', 'ge5', '1to4'], lambda m: mt(m, 'attr_knn', 'k5', 'acc_all', 'acc_ge5', 'acc_1to4'), 0)
top['attr_zeroshot'] = table('attr_zeroshot', ['describe', 'words_only', 'describe_rows_no_qprefix'],
      lambda m: [(get(m, 'attr_zeroshot', v) or {'metrics': {}})['metrics'].get('acc_all') for v in ('describe', 'attr_words_only', 'describe_rows_no_query_prefix')], 0)
top['attr_hybrid'] = table('attr_hybrid (page folds)', ['acc_all', 'ge5', '1to4', 'unseen(76)', 'w2 all', 'w2 unseen', 'max-imp all', 'max-imp unseen'],
      lambda m: (mt(m, 'attr_hybrid', 'z_probe+z_zeroshot', 'acc_all', 'acc_ge5', 'acc_1to4', 'acc_unseen') or []) + (mt(m, 'attr_hybrid', 'z_probe+2*z_zeroshot', 'acc_all', 'acc_unseen') or []) + (mt(m, 'attr_hybrid', 'z_probe+z_zeroshot_unseen_max', 'acc_all', 'acc_unseen') or []), 0)
top['attr_unseen'] = table('attr_unseen (attribute folds, all 1467 rows unseen)', ['probe_alone', 'zeroshot_alone', 'hybrid w1', 'hybrid w2', 'hybrid max-imp'],
      lambda m: [(mt(m, 'attr_unseen', v, 'acc_all') or [None])[0] for v in ('probe_alone_LR_C10', 'zeroshot_alone', 'hybrid_z_probe+z_zeroshot', 'hybrid_z_probe+2*z_zeroshot', 'hybrid_unseen_max')], 2)
kr = get(models[0], 'key_retrieval')['metrics']
top['key_retrieval'] = table('key_retrieval (k=10)', ['recall@10', 'hit@10', 'mrr'], lambda m: mt(m, 'key_retrieval', None, 'recall_at_k', 'hit_at_k', 'mrr'), 0,
      ref=[f3(kr['tfidf_recall_at_k']), f3(kr['tfidf_hit_at_k']), f3(kr['tfidf_mrr'])])
top['truth_false'] = table('truth_false (false vs rest)', ['auc', 'ap', 'f1_max'], lambda m: mt(m, 'truth_false', None, 'auc', 'ap', 'f1_max'), 0,
      ref=[f3(Fz['auc']), f3(Fz['ap']), f3(Fz['f1_max'])])
top['truth_three'] = table('truth_three', ['acc', 'macro_f1', 'false_recall', 'false_prec', 'arena_best', 'arena_at_05'], lambda m: mt(m, 'truth_three', None, 'acc', 'macro_f1', 'false_recall', 'false_precision', 'arena_best', 'arena_at_05'), 4)
print('arena_always_true =', f3(get(models[0], 'truth_three')['metrics']['arena_always_true']))
def spd(m):
    r = get(m, 'speed', 'bs32_2000texts'); c = get(m, 'speed', 'bs32_2000texts_cpu_time')
    return None if r is None else [r['params_m'], r['disk_mb'], r['dim'], r['metrics']['sentences_per_s'], r['metrics']['est_sec_20k_x86'],
                                   c['metrics']['sents_per_cpu_s'] if c else None, c['metrics']['sentences_per_s'] if c else None]
top['speed'] = table('speed/size', ['params_M', 'disk_MB', 'dim', 'sents/s', 'est_20k_x86_s', 'sents/cpu-s (re-run)', 'sents/s (re-run)'], spd, 3)
# C sweep (extras)
def sweep(m):
    pr = {C: (get(m, 'attr_probe', f'LR_C{C}') or {'metrics': {}})['metrics'].get('acc_all') for C in ('1', '10', '100', '1000')}
    if pr['1'] is None: return None
    hy = {C: (get(m, 'attr_hybrid', v) or {'metrics': {}})['metrics'].get('acc_all') for C, v in (('10', 'z_probe+z_zeroshot'), ('100', 'C100_z_probe+z_zeroshot'), ('1000', 'C1000_z_probe+z_zeroshot'))}
    un = {C: (get(m, 'attr_unseen', v) or {'metrics': {}})['metrics'].get('acc_all') for C, v in (('10', 'hybrid_unseen_max'), ('100', 'C100_hybrid_z_probe+z_zeroshot_unseen_max'), ('1000', 'C1000_hybrid_z_probe+z_zeroshot_unseen_max'))}
    return [pr['1'], pr['10'], pr['100'], pr['1000'], hy['10'], hy['100'], hy['1000'], un['10'], un['100'], un['1000']]
table('C sweep: probe acc_all C=1/10/100/1000 | hybrid(w1) acc_all C=10/100/1000 | unseen hybrid(max-imp) C=10/100/1000', ['p1', 'p10', 'p100', 'p1000', 'h10', 'h100', 'h1000', 'u10', 'u100', 'u1000'], sweep, 1)
print('\nTOP3')
for t, out in top.items():
    key = {'attr_unseen': 2}.get(t, 0 if t != 'truth_three' and t != 'speed' else (4 if t == 'truth_three' else 3))
    print(t, [(short(m), round(v[key], 3)) for m, v in out[:3]])
