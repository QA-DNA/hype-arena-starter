"""Print every w5 record compactly (3 decimals): python3 summarize.py"""
import json
KEYS = ['acc_all', 'acc_ge5', 'acc_1to4', 'acc_unseen', 'auc', 'ap', 'f1_max', 'brier', 'ece', 'acc', 'macro_f1',
        'false_recall', 'false_precision', 'unsure_recall', 'arena_at_05', 'arena_best', 'arena_best_t',
        'arena_always_true', 'sentences_per_s', 'est_sec_20k_x86']
for line in open('/tmp/veridyct-emb/results/w5.jsonl'):
    r = json.loads(line); m = r['metrics']
    vals = ' '.join(f'{k}={m[k]:.3f}' if isinstance(m.get(k), float) else f'{k}={m[k]}' for k in KEYS if k in m and m[k] is not None)
    ext = ' '.join(f'{k}={r[k]}' for k in ('params_m', 'disk_mb', 'train_s', 'sents_per_s', 'pairs_per_s') if k in r)
    print(f"{r['model'][:24]:24s} {r['task']:20s} {r['variant']:28s} n={r['n']} {vals} | {ext}")
