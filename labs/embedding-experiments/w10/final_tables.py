import json, collections, re
R = [json.loads(l) for l in open('/tmp/veridyct-emb/results/w10.jsonl')]
short = lambda m: m.split('/')[-1].replace('finecat-nli-', 'finecat-').replace('-v3.0', '').replace('ModernBERT-base-nli', 'ModernBERT-nli').replace('albert-base-vitaminc-mnli', 'albert-vitaminc')
ORDER = ['finecat-xxs', 'finecat-xs', 'finecat-s', 'finecat-v2-m', 'finecat-ultra-m', 'ModernBERT-nli', 'albert-vitaminc', 'gliclass-edge', 'gliclass-modern-base']
f = lambda x, nd=3: '-' if x is None else (f'{x:.{nd}f}' if isinstance(x, float) else str(x))
def table(head, rows): return '\n'.join(['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)] + ['| ' + ' | '.join(map(str, r)) + ' |' for r in rows])
get = lambda task, m, v: next((r for r in R if r['task'] == task and short(r['model']) == m and r['variant'] == v), None)
startswith = lambda task, m, v: next((r for r in R if r['task'] == task and short(r['model']) == m and r['variant'].startswith(v)), None)
models = [m for m in ORDER if any(short(r['model']) == m for r in R)]
rows = []
for m in models:
    a, b, c = (get('nli_anchor', m, v) for v in ('p_contra_max', '1-p_entail_max', 'p_contra_nearest'))
    if a: rows.append((m, f'{a["metrics"]["auc"]:.3f} ({a["metrics"]["ap"]:.3f})', f'{b["metrics"]["auc"]:.3f}', f'{c["metrics"]["auc"]:.3f} ({c["metrics"]["ap"]:.3f})', f(c['metrics']['f1_max']),
                       f'{a["metrics"]["auc_nearest_diff"]:.3f} / {c["metrics"]["auc_nearest_diff"]:.3f}', f'{a["metrics"]["auc_nearest_same"]:.3f} / {c["metrics"]["auc_nearest_same"]:.3f}'))
print('ANCHOR\n' + table(['model', 'p_contra_max AUC (AP)', '1-p_entail_max AUC', 'p_contra_nearest AUC (AP)', 'near F1max', 'DIFF AUC max/near', 'SAME AUC max/near'], rows))
rows = []
for m in models:
    a, b = get('nli_conflict', m, 'p_contra(i->j)'), get('nli_conflict', m, '1-p_entail(i->j)')
    if a: rows.append((m, f(a['metrics']['auc']), f(a['metrics']['ap']), f(a['metrics']['f1_max']), f(b['metrics']['auc'])))
print('\nCONFLICT\n' + table(['model', 'AUC', 'AP', 'F1max', '1-p_entail AUC'], rows))
kinds = ['quantity', 'money', 'percent', 'date', 'name', 'boolean', 'duration', 'version']
rows = [(m,) + tuple(f(get('nli_conflict', m, 'p_contra(i->j)')['metrics']['auc_by_kind'][k]['auc']) for k in kinds) for m in models if get('nli_conflict', m, 'p_contra(i->j)')]
n = get('nli_conflict', models[0], 'p_contra(i->j)')['metrics']['auc_by_kind']
print('\nPERKIND (n: ' + ', '.join(f'{k} {n[k]["n"]}' for k in kinds) + ')\n' + table(['model'] + kinds, rows))
ex = [r for r in R if r['task'] == 'nli_conflict' and r['variant'] not in ('p_contra(i->j)', '1-p_entail(i->j)')]
for r in ex: print('CONFLICT EXTRA', short(r['model']), r['variant'], f(r['metrics']['auc']), f(r['metrics']['ap']), f(r['metrics']['f1_max']))
ex = [r for r in R if r['task'] == 'nli_anchor' and r['variant'] not in ('p_contra_max', '1-p_entail_max', 'p_contra_nearest')]
for r in ex: print('ANCHOR EXTRA', short(r['model']), r['variant'], f(r['metrics']['auc']), f(r['metrics']['ap']), f(r['metrics']['f1_max']), f(r['metrics']['auc_nearest_diff']), f(r['metrics']['auc_nearest_same']))
rows = []
for m in models:
    main = startswith('nli_attr', m, 'sample400 hyp=') or startswith('nli_attr', m, 'sample400 labels=attr words')
    full = startswith('nli_attr', m, 'full1467 hyp=') or startswith('nli_attr', m, 'full1467 labels=attr words')
    t = {k: startswith('nli_attr', m, f'sample400 {k}') for k in ('T2', 'T3', 'T4')}
    rows.append((m, f(main['metrics']['acc_all']) if main else '-', f(full['metrics']['acc_all']) if full else '-', *(f(t[k]['metrics']['acc_all']) if t[k] else '-' for k in ('T2', 'T3', 'T4'))))
print('\nATTR\n' + table(['model', 'spec template, sample400', 'spec template, full 1467', 'T2 no-subject "states the {attr}"', 'T3 no-subject "is about the {attr}"', 'T4 "{attr} of {subject} is given"'], rows))
rows = []
for m in models:
    first = next((r for r in R if r['task'] == 'speed' and short(r['model']) == m and r['variant'].startswith(('pairs', 'rows'))), None)
    re_ = next((r for r in R if r['task'] == 'speed' and short(r['model']) == m and r['variant'].startswith('recheck')), None)
    if not first: continue
    k = 'rows_per_s' if 'rows_per_s' in first['metrics'] else 'pairs_per_s'
    ld = re.search(r'load avg (\d+\.\d+)', first['notes']).group(1)
    rows.append((m, f(first['params_m'], 1), f(first['disk_mb'], 1), f(first['metrics'][k], 1) + ('' if k == 'pairs_per_s' else ' rows'), ld, f(re_['metrics']['pairs_per_s'], 1) if re_ else '-', f(20000 / (re_['metrics']['pairs_per_s'] if re_ else first['metrics'][k]) * 2.0, 0)))
print('\nSPEED\n' + table(['model', 'params M', 'disk MB', 'first pass per s', 'load', 're-check pairs/s', 'est s/20k pairs x86'], rows))
