"""Markdown tables from /tmp/veridyct-emb/results/w3.jsonl (latest record per model/task/variant wins).  python -I report.py"""
import json, sys
from collections import OrderedDict

recs = [json.loads(l) for l in open('/tmp/veridyct-emb/results/w3.jsonl')]
R = OrderedDict()
for r in recs: R[(r['model'], r['task'], r['variant'])] = r
ok_models = {m for (m, t, v), r in R.items() if t == 'speed' and v.startswith('bs=')}
NAMES = {'minishlab/potion-base-8M': 'potion-8M', 'minishlab/potion-base-32M': 'potion-32M', 'minishlab/potion-retrieval-32M': 'potion-retr-32M',
         'sentence-transformers/static-retrieval-mrl-en-v1': 'static-retr-en', 'sentence-transformers/static-similarity-mrl-multilingual-v1': 'static-sim-multi',
         'sentence-transformers/average_word_embeddings_glove.6B.300d': 'glove-300d', 'tfidf-char_wb2-5+word1-2->TruncatedSVD300': 'LSA-300 (ref)',
         'tfidf-char_wb2-5+word1-2->SparseRandomProjection512': 'RP-512 (ref)', 'intfloat/multilingual-e5-small': 'e5-small-ml',
         'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2': 'para-ml-MiniLM', 'Qwen/Qwen3-Embedding-0.6B': 'Qwen3-0.6B (instr)',
         'Qwen/Qwen3-Embedding-0.6B (no instruction)': 'Qwen3-0.6B (no instr)', 'nomic-ai/nomic-embed-text-v2-moe': 'nomic-v2-moe',
         'google/embeddinggemma-300m': 'embeddinggemma (gated)'}
SHORT = lambda m: NAMES.get(m, m)
TIER = {m: r['tier'] for (m, t, v), r in R.items() if 'tier' in r}
order = []
for (m, t, v) in R:
    if m not in order: order.append(m)
f3 = lambda x: '-' if x is None else (f'{x:.3f}' if isinstance(x, float) else str(x))

def get(m, t, v, k):
    r = R.get((m, t, v)); return None if r is None else r['metrics'].get(k)

def table(title, cols, sort_by=None, models=None):
    """cols: [(header, fn(model)->value)]; sorted descending by column index sort_by."""
    models = [m for m in (models or order) if m in ok_models or True]
    lines = [f'\n### {title}\n', '| model | tier | ' + ' | '.join(h for h, _ in cols) + ' |', '|' + '---|' * (len(cols) + 2)]
    data = []
    for m in models:
        vals = [fn(m) for _, fn in cols]
        if all(v is None for v in vals): continue
        data.append((m, vals))
    if sort_by is not None: data.sort(key=lambda d: -(d[1][sort_by] if d[1][sort_by] is not None else -1))
    for m, vals in data: lines.append(f'| {SHORT(m)} | {TIER.get(m, "?").split(" ")[0]} | ' + ' | '.join(f3(v) for v in vals) + ' |')
    print('\n'.join(lines))
    return data

A = lambda t, v, k: (lambda m: get(m, t, v, k))
for suf, name in (('', 'RAW (harness defaults)'), (';centered', 'MEAN-CENTERED extra')):
    print(f'\n## {name}')
    table('attr_probe (LR C=10, page folds, n=1467)', [('acc_all', A('attr_probe', 'C=10' + suf, 'acc_all')), ('acc_ge5', A('attr_probe', 'C=10' + suf, 'acc_ge5')),
          ('acc_1to4', A('attr_probe', 'C=10' + suf, 'acc_1to4'))], sort_by=0)
    table('attr_knn (k=5)', [('acc_all', A('attr_knn', 'k=5' + suf, 'acc_all')), ('acc_ge5', A('attr_knn', 'k=5' + suf, 'acc_ge5')),
          ('acc_1to4', A('attr_knn', 'k=5' + suf, 'acc_1to4'))], sort_by=0)
    table('attr_zeroshot (acc; no training)', [('describe', A('attr_zeroshot', 'describe' + suf, 'acc_all')),
          ('words_only', A('attr_zeroshot', 'attr_words_only' + suf, 'acc_all')),
          ('describe, alt prefix', A('attr_zeroshot', 'describe|desc=alt_prefix' + suf, 'acc_all')),
          ('words, alt prefix', A('attr_zeroshot', 'attr_words_only|desc=alt_prefix' + suf, 'acc_all'))], sort_by=0)
    hv = lambda v: [('all', A('attr_hybrid', v + suf, 'acc_all')), ('ge5', A('attr_hybrid', v + suf, 'acc_ge5')),
                    ('1to4', A('attr_hybrid', v + suf, 'acc_1to4')), ('unseen(76)', A('attr_hybrid', v + suf, 'acc_unseen'))]
    table('attr_hybrid zs=describe, unseen=neutral (page folds)', hv('zs=describe;unseen=neutral'), sort_by=0)
    table('attr_hybrid zs=attr_words_only, unseen=neutral', hv('zs=attr_words_only;unseen=neutral'), sort_by=0)
    if not suf: table('attr_hybrid zs=describe, unseen=veto', hv('zs=describe;unseen=veto'), sort_by=0)
    table('attr_unseen (leave-attribute-out, n=1467; probe alone is 0 by construction)',
          [('probe_alone', A('attr_unseen', 'probe_alone' + suf, 'acc_all')),
           ('hybrid describe/neutral', A('attr_unseen', 'hybrid zs=describe;unseen=neutral' + suf, 'acc_all')),
           ('hybrid words/neutral', A('attr_unseen', 'hybrid zs=attr_words_only;unseen=neutral' + suf, 'acc_all')),
           ('hybrid describe/veto', A('attr_unseen', 'hybrid zs=describe;unseen=veto' + suf, 'acc_all')),
           ('zero-shot alone (ref)', A('attr_zeroshot', 'describe' + suf, 'acc_all'))], sort_by=1)
    table('key_retrieval (k=10, n_queries from harness)', [('recall@10', A('key_retrieval', 'cosine,k=10' + suf, 'recall_at_k')),
          ('hit@10', A('key_retrieval', 'cosine,k=10' + suf, 'hit_at_k')), ('mrr', A('key_retrieval', 'cosine,k=10' + suf, 'mrr')),
          ('tfidf recall@10', A('key_retrieval', 'cosine,k=10' + suf, 'tfidf_recall_at_k'))], sort_by=0)
    table('truth_false (false-vs-rest, LR C=1)', [('auc', A('truth_false', 'C=1' + suf, 'auc')), ('ap', A('truth_false', 'C=1' + suf, 'ap')),
          ('f1_max', A('truth_false', 'C=1' + suf, 'f1_max'))], sort_by=0)
    table('truth_three (3-class, LR C=1)', [('acc', A('truth_three', 'C=1' + suf, 'acc')), ('macro_f1', A('truth_three', 'C=1' + suf, 'macro_f1')),
          ('arena_best', A('truth_three', 'C=1' + suf, 'arena_best')), ('arena_always_true', A('truth_three', 'C=1' + suf, 'arena_always_true'))], sort_by=2)

sp = lambda k: (lambda m: next((r.get(k) if k in r else r['metrics'].get(k) for (mm, t, v), r in R.items() if mm == m and t == 'speed' and v.startswith('bs=')), None))
table('speed / size (2,000 texts, 2 threads, Mac arm64)', [('params_M', sp('params_m')), ('disk_MB', sp('disk_mb')), ('dim', sp('dim')),
      ('max_seq', sp('max_seq_length')), ('vocab', sp('vocab')), ('sents/s', sp('sentences_per_s')), ('est_s_20k_x86', sp('est_sec_20k_x86'))], sort_by=5)
fails = [(m, v, r['metrics'].get('error', '')[:160]) for (m, t, v), r in R.items() if v in ('load_failed', 'run_failed')]
print('\nFAILURES:', fails)

# ---------------------------------------------------------------- top-3 per task and the centered effect
TOP = [('attr_probe', 'C=10', 'acc_all'), ('attr_knn', 'k=5', 'acc_all'), ('attr_zeroshot', 'describe', 'acc_all'), ('attr_hybrid', 'zs=describe;unseen=neutral', 'acc_all'),
       ('attr_hybrid', 'zs=describe;unseen=neutral', 'acc_unseen'), ('attr_unseen', 'hybrid zs=describe;unseen=neutral', 'acc_all'),
       ('key_retrieval', 'cosine,k=10', 'recall_at_k'), ('truth_false', 'C=1', 'auc'), ('truth_three', 'C=1', 'arena_best'), ('speed', None, 'sentences_per_s')]
print('\n## TOP-3 per task (raw, all models incl. references)')
for t, v, k in TOP:
    c = []
    for (m, tt, vv), r in R.items():
        if tt != t or (v is not None and vv != v) or (v is None and not vv.startswith('bs=')): continue
        x = r['metrics'].get(k)
        if x is not None: c.append((x, m))
    c.sort(reverse=True)
    print(f'{t}/{k}: ' + '; '.join(f'{SHORT(m)} [{TIER.get(m, "?").split(" ")[0]}] {x:.3f}' if x < 1000 else f'{SHORT(m)} [{TIER.get(m, "?").split(" ")[0]}] {x:.0f}' for x, m in c[:3]))

print('\n## EFFECT of mean-centering (raw -> centered)')
pairs_ = [('attr_probe all', 'attr_probe', 'C=10', 'acc_all'), ('kNN all', 'attr_knn', 'k=5', 'acc_all'), ('zs describe', 'attr_zeroshot', 'describe', 'acc_all'),
          ('hybrid all', 'attr_hybrid', 'zs=describe;unseen=neutral', 'acc_all'), ('recall@10', 'key_retrieval', 'cosine,k=10', 'recall_at_k'),
          ('false AUC', 'truth_false', 'C=1', 'auc'), ('3-cls arena', 'truth_three', 'C=1', 'arena_best')]
print('| model | ' + ' | '.join(h for h, *_ in pairs_) + ' |\n|' + '---|' * (len(pairs_) + 1))
for m in order:
    cells = []
    for h, t, v, k in pairs_:
        a, b = get(m, t, v, k), get(m, t, v + ';centered', k)
        cells.append('-' if a is None or b is None else f'{a:.3f} -> {b:.3f}')
    if any(c != '-' for c in cells): print(f'| {SHORT(m)} | ' + ' | '.join(cells) + ' |')
