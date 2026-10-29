"""Markdown tables from /tmp/veridyct-emb/results/w9.jsonl (read-only). Usage: python3 report.py"""
import json, collections
R = [json.loads(l) for l in open('/tmp/veridyct-emb/results/w9.jsonl')]
short = lambda m: m.split('/')[-1]
def get(task, variant=None):
    out = collections.OrderedDict()
    for r in R:
        if r['task'] == task and (variant is None or r['variant'] == variant):
            out[(r['model'], r['variant'])] = r
    return out
def f(v, d=3): return '-' if v is None else (f'{v:.{d}f}' if isinstance(v, float) else str(v))
def table(task, cols, variants=None, title=None):
    rows = [(m, v, r) for (m, v), r in get(task).items() if variants is None or v in variants]
    print(f'\n**{title or task}**\n')
    print('| model | variant | ' + ' | '.join(cols) + ' |'); print('|' + '---|' * (2 + len(cols)))
    for m, v, r in rows:
        print(f'| {short(m)} | {v} | ' + ' | '.join(f(r["metrics"].get(c)) for c in cols) + ' |')
table('attr_probe', ['acc_all', 'acc_ge5', 'acc_1to4'])
table('attr_knn', ['acc_all', 'acc_ge5', 'acc_1to4'])
table('attr_zeroshot', ['acc_all'])
table('attr_hybrid', ['acc_all', 'acc_ge5', 'acc_1to4', 'acc_unseen'])
table('attr_unseen', ['acc_all'])
table('key_retrieval', ['recall_at_k', 'hit_at_k', 'mrr', 'tfidf_recall_at_k', 'tfidf_mrr'])
table('truth_false', ['auc', 'ap', 'f1_max'])
table('truth_three', ['acc', 'macro_f1', 'arena_best', 'ece', 'arena_always_true'])
print('\n**speed / size**\n\n| model | sents/s | est s per 20k x86 | params M | disk MB | dim | max_seq |\n|---|---|---|---|---|---|---|')
for (m, v), r in get('speed').items():
    print(f'| {short(m)} | {f(r["metrics"]["sentences_per_s"],1)} | {f(r["metrics"]["est_sec_20k_x86"],0)} | {f(r.get("params_m"),1)} | {f(r.get("disk_mb"),0)} | {r.get("dim")} | {r.get("max_seq_length")} |')

# ---------------------------------------------------------------- top-3 per task vs the TF-IDF references (primary variants only: no '@tag' extras)
print('\n**top-3 per task (primary variant, no @tag extras)**\n')
REF = {'attr_probe': ('acc_all', 0.873, 'TF-IDF+LinearSVC acc_all 0.873'), 'attr_knn': ('acc_all', 0.873, 'TF-IDF acc_all 0.873'),
       'attr_zeroshot': ('acc_all', 0.873, 'TF-IDF acc_all 0.873 (zero-shot has no training, so also covers unseen attrs where TF-IDF scores 0)'),
       'attr_hybrid': ('acc_all', 0.873, 'TF-IDF acc_all 0.873'), 'attr_unseen': ('acc_all', 0.0, 'TF-IDF/probe 0.000 on unseen'),
       'key_retrieval': ('recall_at_k', None, 'char TF-IDF recall@10 (per-row below)'), 'truth_false': ('auc', 0.633, 'TF-IDF LR AUC 0.633'),
       'truth_three': ('arena_best', 0.687, 'always-true arena 0.687')}
PRIMARY = {'attr_probe': 'LR_C10', 'attr_knn': 'k5', 'attr_zeroshot': 'describe', 'attr_hybrid': 'z_probe+z_zeroshot',
           'attr_unseen': 'hybrid_z_probe+z_zeroshot', 'key_retrieval': 'cosine_k10', 'truth_false': 'LR_balanced_C1', 'truth_three': 'LR_balanced_C1'}
for task, (metric, ref, refname) in REF.items():
    cand = [(r['metrics'].get(metric), short(r['model'])) for (m, v), r in get(task).items() if v == PRIMARY[task]]
    cand = sorted([c for c in cand if c[0] is not None], reverse=True)[:3]
    refs = [r['metrics'].get('tfidf_recall_at_k') for (m, v), r in get(task).items() if task == 'key_retrieval'][:1]
    ref = ref if ref is not None else (refs[0] if refs else None)
    print(f'- {task} ({metric}; ref {refname}{"" if ref is None else f" = {ref:.3f}"}): ' + ', '.join(f'{n} {v:.3f}' + ('' if ref is None else f' ({v - ref:+.3f})') for v, n in cand))
