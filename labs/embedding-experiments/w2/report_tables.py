"""compact best-first markdown tables for the write-up (short model labels). reads results/w2.jsonl, last record wins."""
import json, collections
R = {}
for line in open('/tmp/veridyct-emb/results/w2.jsonl'):
    r = json.loads(line); R[(r['model'], r['task'], r['variant'])] = r
LAB = {'Snowflake/snowflake-arctic-embed-l-v2.0': 'arctic-l-v2', 'NovaSearch/stella_en_400M_v5': 'stella-400m', 'BAAI/bge-m3': 'bge-m3',
       'BAAI/bge-large-en-v1.5': 'bge-large', 'mixedbread-ai/mxbai-embed-large-v1': 'mxbai-large', 'nomic-ai/modernbert-embed-base': 'modernbert-embed',
       'nomic-ai/nomic-embed-text-v1.5': 'nomic-v1.5', 'Alibaba-NLP/gte-modernbert-base': 'gte-modernbert', 'intfloat/e5-large-v2': 'e5-large',
       'thenlper/gte-large': 'gte-large', 'ibm-granite/granite-embedding-english-r2': 'granite-r2', 'ibm-granite/granite-embedding-small-english-r2': 'granite-small',
       'jinaai/jina-embeddings-v3': 'jina-v3'}
models = [m for m in LAB if any(k[0] == m for k in R)]
def g(m, t, v, k, d=3):
    r = R.get((m, t, v)); x = r['metrics'].get(k) if r else None
    return float('nan') if x is None else x
def tab(title, cols, key=0, fmt='{:.3f}'):
    rows = sorted(models, key=lambda m: -(g(m, *cols[key][1:]) if g(m, *cols[key][1:]) == g(m, *cols[key][1:]) else -1))
    print(f'\n**{title}**\n| model | ' + ' | '.join(c[0] for c in cols) + ' |\n|---|' + '---|' * len(cols))
    for m in rows: print(f'| {LAB[m]} | ' + ' | '.join('-' if g(m, *c[1:]) != g(m, *c[1:]) else fmt.format(g(m, *c[1:])) for c in cols) + ' |')
tab('attr_probe (TF-IDF 0.873 all / 0.961 ge5)', [('C=10 all', 'attr_probe', 'C=10', 'acc_all'), ('ge5', 'attr_probe', 'C=10', 'acc_ge5'), ('1-4', 'attr_probe', 'C=10', 'acc_1to4'), ('C=100 all', 'attr_probe', 'C=100', 'acc_all')])
tab('attr_knn k=5', [('all', 'attr_knn', 'k=5', 'acc_all'), ('ge5', 'attr_knn', 'k=5', 'acc_ge5')])
tab('attr_zeroshot (no training; TF-IDF unseen = 0)', [('describe', 'attr_zeroshot', 'describe', 'acc_all'), ('words only', 'attr_zeroshot', 'attr_words_only', 'acc_all'), ('describe, no q-prefix', 'attr_zeroshot', 'describe+q_probe_view', 'acc_all')])
tab('attr_hybrid (page folds, 1:1; unseen n=76)', [('all', 'attr_hybrid', 'probe+zs w=1 (1:1)', 'acc_all'), ('ge5', 'attr_hybrid', 'probe+zs w=1 (1:1)', 'acc_ge5'), ('unseen', 'attr_hybrid', 'probe+zs w=1 (1:1)', 'acc_unseen'), ('w4 unseen', 'attr_hybrid', 'probe+zs w=4', 'acc_unseen'), ('C=100 all', 'attr_hybrid', 'C=100 probe+zs w=1', 'acc_all')])
tab('attr_unseen (leave-attribute-out, n=1467)', [('hybrid 1:1', 'attr_unseen', 'hybrid w=1 (1:1)', 'acc_all'), ('hybrid w4', 'attr_unseen', 'hybrid w=4', 'acc_all'), ('zero-shot only', 'attr_zeroshot', 'describe', 'acc_all'), ('probe only', 'attr_unseen', 'probe_only', 'acc_all')], key=1)
kr = {}
for (m, t, v), r in R.items():
    if t == 'key_retrieval' and (m not in kr or r['metrics']['recall_at_k'] > kr[m][1]['recall_at_k']): kr[m] = (v, r['metrics'])
print('\n**key_retrieval (n_queries 1844; TF-IDF recall@10 0.666; best variant per model)**\n| model | variant | recall@10 | hit@10 | mrr |\n|---|---|---|---|---|')
for m, (v, x) in sorted(kr.items(), key=lambda z: -z[1][1]['recall_at_k']): print(f"| {LAB[m]} | {v} | {x['recall_at_k']:.3f} | {x['hit_at_k']:.3f} | {x['mrr']:.3f} |")
tab('truth_false (TF-IDF AUC 0.633)', [('AUC', 'truth_false', 'C=1', 'auc'), ('AP', 'truth_false', 'C=1', 'ap')])
tab('truth_three (always-true arena 0.687)', [('arena_best', 'truth_three', 'C=1', 'arena_best'), ('acc', 'truth_three', 'C=1', 'acc'), ('false_recall', 'truth_three', 'C=1', 'false_recall')])
print('\n**speed (2 threads, shared machine, fp32, bs 32, 2000 texts)**\n| model | params M | disk MB | dim | max_seq | sents/s | est. 20k x86 s |\n|---|---|---|---|---|---|---|')
sp = [(m, R[(m, 'speed', 'bs32_2threads_2000texts')]) for m in models if (m, 'speed', 'bs32_2threads_2000texts') in R]
for m, r in sorted(sp, key=lambda z: -z[1]['metrics']['sentences_per_s']): print(f"| {LAB[m]} | {r['params_m']:.0f} | {r['disk_mb']:.0f} | {r['dim']} | {r['max_seq_length']} | {r['metrics']['sentences_per_s']:.1f} | {r['metrics']['est_sec_20k_x86']:.0f} |")
