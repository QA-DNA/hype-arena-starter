"""Compact per-task markdown tables for the hand-off message (reads w3.jsonl).  python -I final_tables.py"""
import json
from collections import OrderedDict
R = OrderedDict(((r['model'], r['task'], r['variant']), r) for r in map(json.loads, open('/tmp/veridyct-emb/results/w3.jsonl')))
N = {'minishlab/potion-base-8M': 'potion-8M', 'minishlab/potion-base-32M': 'potion-32M', 'minishlab/potion-retrieval-32M': 'potion-retr-32M',
     'sentence-transformers/static-retrieval-mrl-en-v1': 'static-retr-en', 'sentence-transformers/static-similarity-mrl-multilingual-v1': 'static-sim-multi',
     'sentence-transformers/average_word_embeddings_glove.6B.300d': 'glove-300d', 'tfidf-char_wb2-5+word1-2->TruncatedSVD300': 'LSA-300 (ref)',
     'tfidf-char_wb2-5+word1-2->SparseRandomProjection512': 'RP-512 (ref)', 'intfloat/multilingual-e5-small': 'e5-small',
     'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2': 'para-MiniLM', 'Qwen/Qwen3-Embedding-0.6B': 'Qwen3 +instr',
     'Qwen/Qwen3-Embedding-0.6B (no instruction)': 'Qwen3 no-instr', 'nomic-ai/nomic-embed-text-v2-moe': 'nomic-v2-moe'}
T = {m: R[(m, 'speed', next(v for (mm, t, v) in R if mm == m and t == 'speed' and v.startswith('bs=')))]['tier'].split(' ')[0] for m in N}
g = lambda m, t, v, k: (R.get((m, t, v)) or {'metrics': {}})['metrics'].get(k)
def table(title, cols, key=0, note=''):
    rows = [(m, [f(m) for _, f in cols]) for m in N]
    rows.sort(key=lambda r: -(r[1][key] if r[1][key] is not None else -1))
    print(f'\n**{title}**{note}\n\n| model | tier | ' + ' | '.join(h for h, _ in cols) + ' |\n|' + '---|' * (len(cols) + 2))
    for m, v in rows: print(f'| {N[m]} | {T[m]} | ' + ' | '.join('-' if x is None else (f'{x:.3f}' if isinstance(x, float) and x < 1e4 else f'{x:,.0f}' if isinstance(x, float) else str(x)) for x in v) + ' |')
q = lambda t, v, k: (lambda m: g(m, t, v, k))
H = 'zs=describe;unseen=neutral'
table('attr_probe (C=10; unseen 0 by construction; TF-IDF+SVM ref 0.873 / 0.961)', [('all', q('attr_probe', 'C=10', 'acc_all')), ('ge5', q('attr_probe', 'C=10', 'acc_ge5')),
      ('all, centered', q('attr_probe', 'C=10;centered', 'acc_all'))])
table('attr_knn (k=5)', [('all', q('attr_knn', 'k=5', 'acc_all'))])
table('attr_zeroshot (no training)', [('subject+attr', q('attr_zeroshot', 'describe', 'acc_all')), ('attr only', q('attr_zeroshot', 'attr_words_only', 'acc_all'))])
table('attr_hybrid (page folds)', [('all', q('attr_hybrid', H, 'acc_all')), ('unseen (n=76)', q('attr_hybrid', H, 'acc_unseen')), ('all, centered', q('attr_hybrid', H + ';centered', 'acc_all'))])
table('attr_unseen (leave-attribute-out; probe alone 0.000 everywhere)', [('hybrid', q('attr_unseen', 'hybrid ' + H, 'acc_all')),
      ('zero-shot alone', q('attr_zeroshot', 'describe', 'acc_all'))])
table('key_retrieval (TF-IDF char ref: recall@10 0.666, mrr 0.865)', [('recall@10', q('key_retrieval', 'cosine,k=10', 'recall_at_k')), ('mrr', q('key_retrieval', 'cosine,k=10', 'mrr'))])
table('truth_false (TF-IDF ref AUC 0.633)', [('AUC', q('truth_false', 'C=1', 'auc'))])
table('truth_three (always-true arena bar 0.687)', [('arena_best', q('truth_three', 'C=1', 'arena_best'))])
sp = lambda k: (lambda m: next((r.get(k) if k in r else r['metrics'].get(k)) for (mm, t, v), r in R.items() if mm == m and t == 'speed' and v.startswith('bs=')))
rows = sorted(N, key=lambda m: -sp('sentences_per_s')(m))
print('\n**speed / size (2,000 texts, 2 threads)**\n\n| model | tier | sents/s | params M | disk MB | dim | vocab |\n|---|---|---|---|---|---|---|')
for m in rows:
    v = sp('vocab')(m) if any(mm == m and t == 'speed' and 'vocab' in r for (mm, t, vv), r in R.items()) else None
    print(f"| {N[m]} | {T[m]} | {sp('sentences_per_s')(m):,.0f} | {sp('params_m')(m):,.1f} | {sp('disk_mb')(m):,.0f} | {sp('dim')(m)} | {'-' if v is None else format(v, ',')} |")
