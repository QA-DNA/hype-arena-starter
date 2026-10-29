"""Compact markdown tables (primary variants + the few extras quoted in the report) from the w9 results file. Read-only."""
import json
R = [json.loads(l) for l in open('/tmp/veridyct-emb/results/w9.jsonl')]
ORDER = ['mdbr-leaf-mt', 'GIST-small-Embedding-v0', 'mini-gte', 'bekko-static-embedding-v1', 'bekko-embedding-v1-a8m', 'UltraBERT-Embed-150M',
         'UAE-Large-V1', 'jina-embeddings-v5-text-nano', 'DenseOn']
NAME = {'GIST-small-Embedding-v0': 'GIST-small', 'bekko-static-embedding-v1': 'bekko-static', 'bekko-embedding-v1-a8m': 'bekko-a8m',
        'UltraBERT-Embed-150M': 'UltraBERT', 'UAE-Large-V1': 'UAE-Large', 'jina-embeddings-v5-text-nano': 'jina-v5-nano'}
def g(model, task, variant, *keys):
    for r in R:
        if r['model'].split('/')[-1] == model and r['task'] == task and r['variant'] == variant:
            return [r['metrics'].get(k) if k in r['metrics'] else r.get(k) for k in keys]
    return [None] * len(keys)
f = lambda v, d=3: '-' if v is None else f'{v:.{d}f}'
def tab(title, header, spec, models=ORDER):
    print(f'\n**{title}**\n\n| model | ' + ' | '.join(header) + ' |\n|' + '---|' * (len(header) + 1))
    for m in models:
        vals = []
        for task, variant, key, d in spec:
            vals.append(f(g(m, task, variant, key)[0], d))
        if all(v == '-' for v in vals): continue
        print(f'| {NAME.get(m, m)} | ' + ' | '.join(vals) + ' |')
M9 = ORDER[:-1]
tab('attr_probe (LR C=10; TF-IDF ref 0.873 / ge5 0.961 / 1to4 0.883)', ['all', 'ge5', '1to4'], [('attr_probe', 'LR_C10', k, 3) for k in ('acc_all', 'acc_ge5', 'acc_1to4')], M9)
tab('attr_knn (k=5)', ['all', 'ge5', '1to4'], [('attr_knn', 'k5', k, 3) for k in ('acc_all', 'acc_ge5', 'acc_1to4')], M9)
tab('attr_zeroshot (no training; acc_unseen = acc_all)', ['describe', 'words only', 'rows sym-encoded'],
    [('attr_zeroshot', 'describe', 'acc_all', 3), ('attr_zeroshot', 'attr_words_only', 'acc_all', 3), ('attr_zeroshot', 'describe_rows_sym_encoding', 'acc_all', 3)])
tab('attr_hybrid (page folds; 1:1 spec, 2:1 extra)', ['1:1 all', 'ge5', '1to4', 'unseen (n=76)', '2:1 all', '2:1 unseen'],
    [('attr_hybrid', 'z_probe+z_zeroshot', k, 3) for k in ('acc_all', 'acc_ge5', 'acc_1to4', 'acc_unseen')] + [('attr_hybrid', 'z_probe+2*z_zeroshot', k, 3) for k in ('acc_all', 'acc_unseen')], M9)
tab('attr_unseen (attribute folds, every row unseen; probe alone = 0.000 for all)', ['hybrid 1:1', 'hybrid 2:1', 'zero-shot alone'],
    [('attr_unseen', 'hybrid_z_probe+z_zeroshot', 'acc_all', 3), ('attr_unseen', 'hybrid_z_probe+2*z_zeroshot', 'acc_all', 3), ('attr_unseen', 'zeroshot_alone_describe', 'acc_all', 3)], M9)
tab('key_retrieval (TF-IDF ref recall@10 0.666, hit 0.964, MRR 0.865)', ['recall@10', 'hit@10', 'MRR'], [('key_retrieval', 'cosine_k10', k, 3) for k in ('recall_at_k', 'hit_at_k', 'mrr')])
tab('truth_false (TF-IDF ref AUC 0.633, AP 0.241)', ['AUC C=1', 'AP', 'AUC C=10', 'AUC C=100'],
    [('truth_false', 'LR_balanced_C1', 'auc', 3), ('truth_false', 'LR_balanced_C1', 'ap', 3), ('truth_false', 'LR_balanced_C10', 'auc', 3), ('truth_false', 'LR_balanced_C100', 'auc', 3)], M9)
tab('truth_three (always-true arena 0.687)', ['acc', 'macro-F1', 'arena C=1', 'acc C=100', 'arena C=100'],
    [('truth_three', 'LR_balanced_C1', 'acc', 3), ('truth_three', 'LR_balanced_C1', 'macro_f1', 3), ('truth_three', 'LR_balanced_C1', 'arena_best', 3),
     ('truth_three', 'LR_balanced_C100', 'acc', 3), ('truth_three', 'LR_balanced_C100', 'arena_best', 3)], M9)
tab('speed / size (2 threads, shared machine, loadavg ~10)', ['sents/s', 's per 20k x86', 'params M', 'disk MB', 'dim', 'max_seq'],
    [('speed', 'bs32_2000texts', 'sentences_per_s', 1), ('speed', 'bs32_2000texts', 'est_sec_20k_x86', 0), ('speed', 'bs32_2000texts', 'params_m', 1),
     ('speed', 'bs32_2000texts', 'disk_mb', 0), ('speed', 'bs32_2000texts', 'dim', 0), ('speed', 'bs32_2000texts', 'max_seq_length', 0)])
print('\n**extras**\n')
for m, t, v, ks in [('bekko-static-embedding-v1', 'attr_probe', 'LR_C10@d256', ('acc_all',)), ('bekko-static-embedding-v1', 'attr_probe', 'LR_C10@d128', ('acc_all',)),
                    ('bekko-static-embedding-v1', 'attr_probe', 'LR_C10@d64', ('acc_all',)),
                    ('bekko-static-embedding-v1', 'attr_hybrid', 'z_probe+z_zeroshot@d256', ('acc_all',)), ('bekko-static-embedding-v1', 'attr_hybrid', 'z_probe+z_zeroshot@d128', ('acc_all',)),
                    ('bekko-static-embedding-v1', 'attr_hybrid', 'z_probe+z_zeroshot@d64', ('acc_all',)), ('bekko-static-embedding-v1', 'key_retrieval', 'cosine_k10@d256', ('recall_at_k',)),
                    ('mdbr-leaf-mt', 'attr_probe', 'LR_C10@d256', ('acc_all',)), ('mdbr-leaf-mt', 'attr_hybrid', 'z_probe+z_zeroshot@d256', ('acc_all',)), ('mdbr-leaf-mt', 'key_retrieval', 'cosine_k10@d256', ('recall_at_k',)),
                    ('UltraBERT-Embed-150M', 'attr_probe', 'LR_C10@noprompt', ('acc_all',)), ('UltraBERT-Embed-150M', 'attr_zeroshot', 'describe@noprompt', ('acc_all',)),
                    ('UltraBERT-Embed-150M', 'attr_hybrid', 'z_probe+z_zeroshot@noprompt', ('acc_all',)), ('UltraBERT-Embed-150M', 'key_retrieval', 'cosine_k10@noprompt', ('recall_at_k',)),
                    ('jina-embeddings-v5-text-nano', 'attr_probe', 'LR_C10@classification_adapter', ('acc_all',)), ('jina-embeddings-v5-text-nano', 'key_retrieval', 'cosine_k10@classification_adapter', ('recall_at_k',)),
                    ('DenseOn', 'key_retrieval', 'cosine_k10@document_prefix_both_sides', ('recall_at_k',))]:
    print(f'{m} {t} {v}: ' + ', '.join(f(g(m, t, v, k)[0]) for k in ks))
