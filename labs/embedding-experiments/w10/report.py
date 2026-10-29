import json, collections
R = [json.loads(l) for l in open('/tmp/veridyct-emb/results/w10.jsonl')]
short = lambda m: m.split('/')[-1].replace('finecat-nli-', 'finecat-').replace('-v3.0', '')
ORDER = ['finecat-xxs', 'finecat-xs', 'finecat-s', 'finecat-v2-m', 'finecat-ultra-m', 'ModernBERT-base-nli', 'albert-base-vitaminc-mnli', 'gliclass-edge', 'gliclass-modern-base']
def f(x, nd=3): return '-' if x is None else (f'{x:.{nd}f}' if isinstance(x, float) else str(x))
def table(head, rows): return '\n'.join(['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)] + ['| ' + ' | '.join(map(str, r)) + ' |' for r in rows])
get = lambda task, model, variant: next((r for r in R if r['task'] == task and short(r['model']) == model and r['variant'] == variant), None)
models = [m for m in ORDER if any(short(r['model']) == m for r in R)]
# ---- anchor
rows = []
for m in models:
    a, b, c = (get('nli_anchor', m, v) for v in ('p_contra_max', '1-p_entail_max', 'p_contra_nearest'))
    if not a: continue
    rows.append((m, f(a['metrics']['auc']), f(a['metrics']['ap']), f(a['metrics']['f1_max']), f(b['metrics']['auc']), f(b['metrics']['ap']), f(c['metrics']['auc']), f(c['metrics']['ap']), f(c['metrics']['f1_max']),
                 f(a['metrics']['auc_nearest_diff']), f(c['metrics']['auc_nearest_diff']), f(a['metrics']['auc_nearest_same']), f(c['metrics']['auc_nearest_same'])))
print('## nli_anchor (n=1353 rows, 202 false; AP baseline 0.149; DIFF subset n=467/190 false; SAME subset n=886/12 false)\n' + table(
    ['model', 'cmax AUC', 'cmax AP', 'cmax F1', '1-emax AUC', '1-emax AP', 'cnear AUC', 'cnear AP', 'cnear F1', 'cmax DIFF', 'cnear DIFF', 'cmax SAME', 'cnear SAME'], rows))
# ---- conflict
rows = []
for m in models:
    a, b = get('nli_conflict', m, 'p_contra(i->j)'), get('nli_conflict', m, '1-p_entail(i->j)')
    if a: rows.append((m, f(a['metrics']['auc']), f(a['metrics']['ap']), f(a['metrics']['f1_max']), f(b['metrics']['auc']), f(b['metrics']['f1_max'])))
print('\n## nli_conflict (n=2649 pairs, 1686 differ)\n' + table(['model', 'p_contra AUC', 'AP', 'F1max', '1-p_entail AUC', 'F1max'], rows))
kinds = ['quantity', 'money', 'percent', 'date', 'name', 'boolean', 'duration', 'version']
rows = [(m,) + tuple(f(get('nli_conflict', m, 'p_contra(i->j)')['metrics']['auc_by_kind'][k]['auc']) for k in kinds) for m in models if get('nli_conflict', m, 'p_contra(i->j)')]
n = get('nli_conflict', models[0], 'p_contra(i->j)')['metrics']['auc_by_kind']
print('\n## per-kind conflict AUC (p_contra), n pairs: ' + ', '.join(f'{k} {n[k]["n"]}' for k in kinds) + '\n' + table(['model'] + kinds, rows))
extra = [r for r in R if r['task'] == 'nli_conflict' and r['variant'] not in ('p_contra(i->j)', '1-p_entail(i->j)')]
if extra: print('\n### conflict extras\n' + table(['model', 'variant', 'AUC', 'AP', 'F1max'], [(short(r['model']), r['variant'], f(r['metrics']['auc']), f(r['metrics']['ap']), f(r['metrics']['f1_max'])) for r in extra]))
extra = [r for r in R if r['task'] == 'nli_anchor' and r['variant'] not in ('p_contra_max', '1-p_entail_max', 'p_contra_nearest')]
if extra: print('\n### anchor extras\n' + table(['model', 'variant', 'AUC', 'AP', 'F1max', 'DIFF', 'SAME'], [(short(r['model']), r['variant'], f(r['metrics']['auc']), f(r['metrics']['ap']), f(r['metrics']['f1_max']), f(r['metrics']['auc_nearest_diff']), f(r['metrics']['auc_nearest_same'])) for r in extra]))
# ---- attr
rows = []
for r in R:
    if r['task'] == 'nli_attr': rows.append((short(r['model']), r['variant'][:75], f(r['metrics']['acc_all']), r['n'], f(r.get('pairs_per_s', r.get('rows_per_s')), 1)))
rows.sort(key=lambda x: (ORDER.index(x[0]) if x[0] in ORDER else 99, x[1]))
print('\n## nli_attr\n' + table(['model', 'variant', 'acc', 'n', 'pairs/s or rows/s'], rows))
# ---- speed
rows = []
for r in R:
    if r['task'] == 'speed': rows.append((short(r['model']), r['variant'], f(r['params_m'], 1), f(r['disk_mb'], 1), f(r['metrics'].get('pairs_per_s', r['metrics'].get('rows_per_s')), 1), f(r['metrics'].get('est_sec_20k_pairs_x86', r['metrics'].get('est_sec_20k_rows_x86')), 0), r['notes'].split('load avg ')[1].split(' (')[0] if 'load avg ' in r['notes'] else ''))
rows.sort(key=lambda x: (ORDER.index(x[0]) if x[0] in ORDER else 99, x[1]))
print('\n## speed\n' + table(['model', 'variant', 'params M', 'disk MB', 'per s', 'est s/20k x86', 'load'], rows))
