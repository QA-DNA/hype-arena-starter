"""Trimmed tables for the final report.  python -I final_tables2.py"""
import json
R = [json.loads(l) for l in open('/tmp/veridyct-emb/results/w1.jsonl')]
REF = json.load(open('/tmp/veridyct-emb/w1/tfidf_ref.json')); A, F = REF['attr'], REF['false']
SHORT = {'all-MiniLM-L6-v2': 'MiniLM-L6', 'all-MiniLM-L12-v2': 'MiniLM-L12', 'all-mpnet-base-v2': 'mpnet-base', 'paraphrase-MiniLM-L3-v2': 'para-MiniLM-L3',
         'bge-small-en-v1.5': 'bge-small', 'bge-base-en-v1.5': 'bge-base', 'gte-small': 'gte-small', 'gte-base': 'gte-base', 'e5-small-v2': 'e5-small',
         'e5-base-v2': 'e5-base', 'snowflake-arctic-embed-s': 'arctic-s', 'snowflake-arctic-embed-m-v1.5': 'arctic-m', 'gte-base-en-v1.5': 'gte-base-1.5',
         'jina-embeddings-v2-small-en': 'jina-v2-small', 'mxbai-embed-xsmall-v1': 'mxbai-xs'}
sh = lambda m: SHORT[m.split('/')[-1]]
models = list(dict.fromkeys(r['model'] for r in R)); IDX = {(r['model'], r['task'], r['variant']): r for r in R}
def g(m, t, v, k):
    r = IDX.get((m, t, v)); return None if r is None else r['metrics'].get(k)
f3 = lambda x: '-' if x is None else (f'{x:.3f}' if isinstance(x, float) else str(x))
def table(title, cols, fn, sort=0, ref=None):
    rows = sorted([(m, fn(m)) for m in models], key=lambda t: -(t[1][sort] if t[1][sort] is not None else -1))
    print(f'\n**{title}**\n\n| model | ' + ' | '.join(cols) + ' |\n|---|' + '---:|' * len(cols))
    if ref: print('| TF-IDF | ' + ' | '.join(ref) + ' |')
    for m, v in rows: print(f'| {sh(m)} | ' + ' | '.join(f3(x) for x in v) + ' |')
table('attr_probe (LR C=10) and attr_knn (k=5)', ['probe all', 'ge5', '1to4', 'kNN all'],
      lambda m: [g(m, 'attr_probe', 'LR_C10', k) for k in ('acc_all', 'acc_ge5', 'acc_1to4')] + [g(m, 'attr_knn', 'k5', 'acc_all')], ref=[f3(A['acc_all']), f3(A['acc_ge5']), f3(A['acc_1to4']), '-'])
table('attr_zeroshot (acc, all 1,467 rows)', ['describe', 'words only'], lambda m: [g(m, 'attr_zeroshot', 'describe', 'acc_all'), g(m, 'attr_zeroshot', 'attr_words_only', 'acc_all')])
table('attr_hybrid (spec: C=10, 1:1)', ['all', 'ge5', '1to4', 'unseen (n=76)'], lambda m: [g(m, 'attr_hybrid', 'z_probe+z_zeroshot', k) for k in ('acc_all', 'acc_ge5', 'acc_1to4', 'acc_unseen')], ref=[f3(A['acc_all']), f3(A['acc_ge5']), f3(A['acc_1to4']), '0.000'])
table('attr_unseen (leave-attribute-out; probe alone 0.000 everywhere)', ['zero-shot alone', 'hybrid 1:1 (spec)', 'hybrid, unseen=max'],
      lambda m: [g(m, 'attr_unseen', v, 'acc_all') for v in ('zeroshot_alone', 'hybrid_z_probe+z_zeroshot', 'hybrid_unseen_max')])
kk = [g(models[0], 'key_retrieval', 'cosine_k10', 'tfidf_' + k) for k in ('recall_at_k', 'mrr')]
table('key_retrieval (k=10)', ['recall@10', 'mrr'], lambda m: [g(m, 'key_retrieval', 'cosine_k10', k) for k in ('recall_at_k', 'mrr')], ref=[f3(x) for x in kk])
table('truth_false / truth_three', ['false AUC', '3-class macro-F1', 'arena_best'], lambda m: [g(m, 'truth_false', 'LR_balanced_C1', 'auc'), g(m, 'truth_three', 'LR_balanced_C1', 'macro_f1'), g(m, 'truth_three', 'LR_balanced_C1', 'arena_best')], ref=[f3(F['auc']), '-', '0.687 (always true)'])
def spd(m):
    r = IDX[(m, 'speed', 'bs32_2000texts')]; c = IDX.get((m, 'speed', 'bs32_2000texts_cpu_time'))
    return [r['params_m'], r['disk_mb'], r['dim'], c['metrics']['sents_per_cpu_s'] if c else None, r['metrics']['sentences_per_s']]
def f1(x): return x
table('speed / size', ['params M', 'disk MB', 'dim', 'sents per CPU-s', 'sents/s (wall, in-run)'], spd, 3)
table('EXTRA: probe acc_all by C, and hybrid (1:1) acc_all by C', ['probe C=10', 'C=100', 'C=1000', 'hybrid C=10', 'C=100', 'C=1000'],
      lambda m: [g(m, 'attr_probe', v, 'acc_all') for v in ('LR_C10', 'LR_C100', 'LR_C1000')] + [g(m, 'attr_hybrid', v, 'acc_all') for v in ('z_probe+z_zeroshot', 'C100_z_probe+z_zeroshot', 'C1000_z_probe+z_zeroshot')], 2, ref=[f3(A['acc_all']), '', '', '', '', ''])
