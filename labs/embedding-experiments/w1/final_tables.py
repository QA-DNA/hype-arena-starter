"""Compact markdown tables for the final report.  python -I final_tables.py"""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common')
import json
R = [json.loads(l) for l in open('/tmp/veridyct-emb/results/w1.jsonl')]
REF = json.load(open('/tmp/veridyct-emb/w1/tfidf_ref.json'))
SHORT = {'all-MiniLM-L6-v2': 'MiniLM-L6', 'all-MiniLM-L12-v2': 'MiniLM-L12', 'all-mpnet-base-v2': 'mpnet-base', 'paraphrase-MiniLM-L3-v2': 'para-MiniLM-L3',
         'bge-small-en-v1.5': 'bge-small', 'bge-base-en-v1.5': 'bge-base', 'gte-small': 'gte-small', 'gte-base': 'gte-base', 'e5-small-v2': 'e5-small',
         'e5-base-v2': 'e5-base', 'snowflake-arctic-embed-s': 'arctic-s', 'snowflake-arctic-embed-m-v1.5': 'arctic-m-1.5', 'gte-base-en-v1.5': 'gte-base-1.5',
         'jina-embeddings-v2-small-en': 'jina-v2-small', 'mxbai-embed-xsmall-v1': 'mxbai-xs'}
sh = lambda m: SHORT[m.split('/')[-1]]
models = list(dict.fromkeys(r['model'] for r in R))
IDX = {}
for r in R: IDX[(r['model'], r['task'], r['variant'])] = r
def g(m, task, variant, key):
    r = IDX.get((m, task, variant)); v = None if r is None else r['metrics'].get(key)
    return v
f3 = lambda x: '-' if x is None else (f'{x:.3f}' if isinstance(x, float) else str(x))
def table(title, cols, fn, sort=0, ref=None, note=''):
    rows = [(m, fn(m)) for m in models]
    rows.sort(key=lambda t: -(t[1][sort] if t[1][sort] is not None else -1))
    print(f'\n**{title}**{note}\n\n| model | ' + ' | '.join(cols) + ' |\n|---|' + '---:|' * len(cols))
    if ref: print('| TF-IDF ref | ' + ' | '.join(ref) + ' |')
    for m, v in rows: print(f'| {sh(m)} | ' + ' | '.join(f3(x) for x in v) + ' |')
A, F = REF['attr'], REF['false']
table('attr_probe (LR C=10) + attr_knn (k=5), page folds', ['probe all', 'ge5', '1to4', 'kNN all'],
      lambda m: [g(m, 'attr_probe', 'LR_C10', 'acc_all'), g(m, 'attr_probe', 'LR_C10', 'acc_ge5'), g(m, 'attr_probe', 'LR_C10', 'acc_1to4'), g(m, 'attr_knn', 'k5', 'acc_all')],
      ref=[f3(A['acc_all']), f3(A['acc_ge5']), f3(A['acc_1to4']), '-'], note=' (unseen bucket = 0.000 for every model, n=76)')
table('attr_zeroshot (no training, acc on all 1,467)', ['describe', 'words only', 'describe, rows w/o query prefix'],
      lambda m: [g(m, 'attr_zeroshot', 'describe', 'acc_all'), g(m, 'attr_zeroshot', 'attr_words_only', 'acc_all'), g(m, 'attr_zeroshot', 'describe_rows_no_query_prefix', 'acc_all')])
table('attr_hybrid (z(probe logP) + z(cosine), 1:1), page folds', ['all', 'ge5', '1to4', 'unseen (76)'],
      lambda m: [g(m, 'attr_hybrid', 'z_probe+z_zeroshot', k) for k in ('acc_all', 'acc_ge5', 'acc_1to4', 'acc_unseen')], ref=[f3(A['acc_all']), f3(A['acc_ge5']), f3(A['acc_1to4']), f3(0.0)])
table('attr_unseen (leave-attribute-out, all 1,467 rows unseen; probe alone = 0.000 for every model)', ['zero-shot alone', 'hybrid w=1 (spec)', 'hybrid w=2', 'hybrid, unseen=max'],
      lambda m: [g(m, 'attr_unseen', 'zeroshot_alone', 'acc_all'), g(m, 'attr_unseen', 'hybrid_z_probe+z_zeroshot', 'acc_all'), g(m, 'attr_unseen', 'hybrid_z_probe+2*z_zeroshot', 'acc_all'), g(m, 'attr_unseen', 'hybrid_unseen_max', 'acc_all')], 0)
kr = g(models[0], 'key_retrieval', 'cosine_k10', 'tfidf_recall_at_k'), g(models[0], 'key_retrieval', 'cosine_k10', 'tfidf_hit_at_k'), g(models[0], 'key_retrieval', 'cosine_k10', 'tfidf_mrr')
table('key_retrieval (k=10, 1,897 rows)', ['recall@10', 'hit@10', 'mrr'], lambda m: [g(m, 'key_retrieval', 'cosine_k10', k) for k in ('recall_at_k', 'hit_at_k', 'mrr')], ref=[f3(x) for x in kr])
table('truth_false / truth_three (page folds)', ['false AUC', 'AP', 'f1_max', '3-class macro-F1', 'arena_best'],
      lambda m: [g(m, 'truth_false', 'LR_balanced_C1', k) for k in ('auc', 'ap', 'f1_max')] + [g(m, 'truth_three', 'LR_balanced_C1', k) for k in ('macro_f1', 'arena_best')],
      ref=[f3(F['auc']), f3(F['ap']), f3(F['f1_max']), '-', '-'], note=' (arena always-true bar = 0.687)')
def spd(m):
    r = IDX.get((m, 'speed', 'bs32_2000texts')); c = IDX.get((m, 'speed', 'bs32_2000texts_cpu_time'))
    return [r['params_m'], r['disk_mb'], r['dim'], r['metrics']['sentences_per_s'], r['metrics']['est_sec_20k_x86'], c['metrics']['sents_per_cpu_s'] if c else None]
table('speed / size (fp32, 2 threads, shared machine)', ['params M', 'disk MB', 'dim', 'sents/s (during run)', 'est 20k x86 s', 'sents per CPU-s (re-run)'], spd, 3)

# ---- extras: probe regularisation sweep (C is tuned on the test folds: optimistic by a few tenths of a point)
table('EXTRA C sweep (page folds): probe acc_all at C=1/10/100/1000, then C=100 probe ge5/1to4 and hybrid (w=1) all/unseen', ['C=1', 'C=10', 'C=100', 'C=1000', 'ge5@100', '1to4@100', 'hyb all@100', 'hyb unseen@100'],
      lambda m: [g(m, 'attr_probe', 'LR_C1', 'acc_all'), g(m, 'attr_probe', 'LR_C10', 'acc_all'), g(m, 'attr_probe', 'LR_C100', 'acc_all'), g(m, 'attr_probe', 'LR_C1000', 'acc_all'),
                 g(m, 'attr_probe', 'LR_C100', 'acc_ge5'), g(m, 'attr_probe', 'LR_C100', 'acc_1to4'), g(m, 'attr_hybrid', 'C100_z_probe+z_zeroshot', 'acc_all'), g(m, 'attr_hybrid', 'C100_z_probe+z_zeroshot', 'acc_unseen')], 2,
      ref=[f3(A['acc_all']), '', '', '', f3(A['acc_ge5']), f3(A['acc_1to4']), '', ''])
table('EXTRA hybrid acc_all by C (w=1, page folds, spec zero-imputation) and leave-attribute-out hybrid with unseen=max', ['hyb C=10', 'hyb C=100', 'hyb C=1000', 'hyb max-imp C=100', 'unseen-fold max-imp C=10', 'C=100', 'C=1000'],
      lambda m: [g(m, 'attr_hybrid', 'z_probe+z_zeroshot', 'acc_all'), g(m, 'attr_hybrid', 'C100_z_probe+z_zeroshot', 'acc_all'), g(m, 'attr_hybrid', 'C1000_z_probe+z_zeroshot', 'acc_all'),
                 g(m, 'attr_hybrid', 'C100_z_probe+z_zeroshot_unseen_max', 'acc_all'), g(m, 'attr_unseen', 'hybrid_unseen_max', 'acc_all'),
                 g(m, 'attr_unseen', 'C100_hybrid_z_probe+z_zeroshot_unseen_max', 'acc_all'), g(m, 'attr_unseen', 'C1000_hybrid_z_probe+z_zeroshot_unseen_max', 'acc_all')], 1)
