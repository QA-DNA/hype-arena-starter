"""markdown tables from results/w2.jsonl (last record per model/task/variant wins). usage: summarize.py"""
import json, collections
R = collections.OrderedDict()
for line in open('/tmp/veridyct-emb/results/w2.jsonl'):
    r = json.loads(line); R[(r['model'], r['task'], r['variant'])] = r
models = list(dict.fromkeys(m for m, _, _ in R))
short = lambda m: m.split('/')[-1]
def g(m, t, v, k, d=3):
    r = R.get((m, t, v)); x = r['metrics'].get(k) if r else None
    return '-' if x is None else (f'{x:.{d}f}' if isinstance(x, float) else str(x))
def variants(m, t): return [v for (mm, tt, v) in R if mm == m and tt == t]
def table(title, cols, sortcol=0):
    print(f'\n### {title}\n| model | ' + ' | '.join(c[0] for c in cols) + ' |\n|---|' + '---|' * len(cols))
    out = [(short(m), [g(m, *c[1:]) for c in cols]) for m in models]
    out.sort(key=lambda x: -(float(x[1][sortcol]) if x[1][sortcol] != '-' else -1))
    for m, vals in out: print(f'| {m} | ' + ' | '.join(vals) + ' |')
P = lambda v, k: ('attr_probe', v, k)
table('attr_probe (page folds; TF-IDF ref 0.873 / ge5 0.961)', [('C=10 all', *P('C=10', 'acc_all')), ('ge5', *P('C=10', 'acc_ge5')), ('1to4', *P('C=10', 'acc_1to4')), ('C=100 all', *P('C=100', 'acc_all')), ('C=100 ge5', *P('C=100', 'acc_ge5'))])
table('attr_knn k=5', [('all', 'attr_knn', 'k=5', 'acc_all'), ('ge5', 'attr_knn', 'k=5', 'acc_ge5'), ('1to4', 'attr_knn', 'k=5', 'acc_1to4')])
Z = lambda v: ('attr_zeroshot', v, 'acc_all')
table('attr_zeroshot (acc_all = acc_unseen)', [('describe', *Z('describe')), ('attr_words_only', *Z('attr_words_only')), ('describe, q no prefix', *Z('describe+q_probe_view')), ('describe, d_alt', *Z('describe+d_alt')), ('words, d_alt', *Z('attr_words_only+d_alt'))])
h = lambda w, k: ('attr_hybrid', f'probe+zs w={w}' + (' (1:1)' if w == '1' else ''), k)
table('attr_hybrid (page folds; spec = 1:1; unseen bucket n=76)', [('1:1 all', *h('1', 'acc_all')), ('1:1 ge5', *h('1', 'acc_ge5')), ('1:1 1to4', *h('1', 'acc_1to4')), ('1:1 unseen', *h('1', 'acc_unseen')), ('w2 all', *h('2', 'acc_all')), ('w2 unseen', *h('2', 'acc_unseen')), ('w4 all', *h('4', 'acc_all')), ('w4 unseen', *h('4', 'acc_unseen')), ('C100 1:1 all', 'attr_hybrid', 'C=100 probe+zs w=1', 'acc_all'), ('C100 1:1 unseen', 'attr_hybrid', 'C=100 probe+zs w=1', 'acc_unseen')])
u = lambda w: ('attr_unseen', f'hybrid w={w}' + (' (1:1)' if w == '1' else ''), 'acc_all')
table('attr_unseen (leave-attribute-out, n=1467; probe alone = 0 by construction)', [('hybrid 1:1', *u('1')), ('hybrid w2', *u('2')), ('hybrid w4', *u('4')), ('probe only', 'attr_unseen', 'probe_only', 'acc_all'), ('zero-shot only', 'attr_zeroshot', 'describe', 'acc_all')])
print('\n### key_retrieval (n_queries = ' + str(next((r['metrics']['n_queries'] for (m, t, v), r in R.items() if t == 'key_retrieval'), '?')) + '; TF-IDF char recall@10 = ' + str(next((round(r['metrics']['tfidf_recall_at_k'], 3) for (m, t, v), r in R.items() if t == 'key_retrieval'), '?')) + ')\n| model | variant | recall@10 | hit@10 | mrr |\n|---|---|---|---|---|')
kr = [(short(m), v, r['metrics']) for (m, t, v), r in R.items() if t == 'key_retrieval']
for m, v, x in sorted(kr, key=lambda z: -z[2]['recall_at_k']): print(f"| {m} | {v} | {x['recall_at_k']:.3f} | {x['hit_at_k']:.3f} | {x['mrr']:.3f} |")
table('truth_false (false-vs-rest; TF-IDF ref AUC 0.633)', [('AUC', 'truth_false', 'C=1', 'auc'), ('AP', 'truth_false', 'C=1', 'ap'), ('F1max', 'truth_false', 'C=1', 'f1_max')])
table('truth_three (arena_always_true = 0.687)', [('arena_best', 'truth_three', 'C=1', 'arena_best'), ('acc', 'truth_three', 'C=1', 'acc'), ('macro_f1', 'truth_three', 'C=1', 'macro_f1'), ('false_recall', 'truth_three', 'C=1', 'false_recall'), ('ece', 'truth_three', 'C=1', 'ece')])
print('\n### speed (2 threads, shared machine, bs 32, 2000 texts)\n| model | params M | disk MB | dim | max_seq | sents/s | est 20k x86 s |\n|---|---|---|---|---|---|---|')
for m in models:
    r = R.get((m, 'speed', 'bs32_2threads_2000texts'))
    if r: x = r['metrics']; print(f"| {short(m)} | {r['params_m']:.0f} | {r['disk_mb']:.0f} | {r['dim']} | {r.get('max_seq_length')} | {x['sentences_per_s']:.1f} | {x['est_sec_20k_x86']:.0f} |")
