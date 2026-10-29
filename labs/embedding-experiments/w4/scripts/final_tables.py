"""Compact deliverable tables from results/w4.jsonl (last record per model/task/variant prefix) + stored attr predictions."""
import sys, json, glob, os; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H
import numpy as np
R = [json.loads(l) for l in open(H.results_path('w4'))]
ORDER = ['ce-xsmall', 'ce-small', 'ce-base', 'ce-minilm2-l6-h768', 'ce-distilroberta', 'ml-base-mnli-fever-anli', 'ts-deberta-small-long-nli',
         'ml-base-zeroshot2', 'ml-modernbert-base-zeroshot2', 'ml-large-zeroshot2', 'albert-xlarge-vitaminc-mnli', 'bart-large-mnli']
BIN = {'ml-base-zeroshot2', 'ml-large-zeroshot2', 'ml-modernbert-base-zeroshot2'}
nm = lambda m: m + ('*' if m in BIN else '')
f = lambda x: '-' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:.3f}'
def get(m, t, vp):
    c = [r for r in R if r['model'] == m and r['task'] == t and r['variant'].startswith(vp)]; return c[-1] if c else None
def tab(head, body):
    print('| ' + ' | '.join(head) + ' |'); print('|' + '---|' * len(head))
    for b in body: print('| ' + ' | '.join(map(str, b)) + ' |')
    print()
K = ['quantity', 'money', 'percent', 'date', 'duration', 'version', 'name', 'boolean']
print('CONFLICT'); body = []
for m in ORDER:
    r = get(m, 'nli_conflict', 'p_'); bk = r['by_kind']; mt = r['metrics']
    body.append([nm(m), r['n'], f(mt['auc']), f(mt['ap']), f(mt['f1_max'])] + [f(bk[k]['auc']) for k in K])
tab(['model', 'n', 'AUC', 'AP', 'F1max', 'qty', 'money', 'pct', 'date', 'dur', 'ver', 'name', 'bool'], body)
print('conflict 1-p_entail AUC:', {m: round(get(m, 'nli_conflict', '1-p_entail')['metrics']['auc'], 3) for m in ORDER if m not in BIN})
print('\nANCHOR forward'); body = []
for m in ORDER:
    a = get(m, 'nli_anchor', 'forward:p_'); b = get(m, 'nli_anchor', 'forward:1-p_entail'); d = a['detail']
    body.append([nm(m), a['n'], f(a['metrics']['auc']), f(a['metrics']['ap']), f(a['metrics']['f1_max']), f(b['metrics']['auc']), f(d['p_contra_nearest_auc_all']),
                 f"{f(d['p_contra_max_auc_nearest_value_differs'])} / {f(d['p_contra_max_auc_nearest_value_same'])}",
                 f"{f(d['p_contra_nearest_auc_nearest_value_differs'])} / {f(d['p_contra_nearest_auc_nearest_value_same'])}"])
tab(['model', 'rows', 'AUC pc_max', 'AP', 'F1max', 'AUC 1-pe_max', 'AUC pc_near', 'pc_max differs/same', 'pc_near differs/same'], body)
print('ANCHOR reverse'); body = []
for m in ORDER:
    a = get(m, 'nli_anchor', 'reverse:p_')
    if a:
        b = get(m, 'nli_anchor', 'reverse:1-p_entail'); fa = get(m, 'nli_anchor', 'forward:p_'); fb = get(m, 'nli_anchor', 'forward:1-p_entail')
        body.append([m, a['n'], f(fa['metrics']['auc']), f(a['metrics']['auc']), f(fb['metrics']['auc']), f(b['metrics']['auc']), f(a['detail']['p_contra_nearest_auc_all'])])
tab(['model', 'rows', 'fwd pc_max', 'rev pc_max', 'fwd 1-pe_max', 'rev 1-pe_max', 'rev pc_near'], body)
print('ATTR'); body = []
for m in ORDER:
    a = get(m, 'nli_attr', 'tmpl1'); b = get(m, 'nli_attr', 'tmpl2')
    z = np.load(f'/tmp/veridyct-emb/w4/scores/{m}.attr_tmpl1.npz', allow_pickle=True)
    k125 = f(float(np.mean([p == q for p, q in zip(z['pred'][:125], z['y'][:125])]))) if len(z['rows']) >= 125 else '-'
    body.append([nm(m), a['n'], f(a['metrics']['acc_all']), (f(b['metrics']['acc_all']) + f" (n={b['n']})") if b else '-', k125, f(a['chance_acc'])])
tab(['model', 'rows', 'acc tmpl1', 'acc tmpl2', 'acc tmpl1 first 125 rows', 'chance'], body)
print('SPEED'); body = []
for m in ORDER:
    a = [r for r in R if r['model'] == m and r['task'] == 'speed' and r['variant'] == 'bs32-2threads-pairs'][-1]; rc = [r for r in R if r['model'] == m and r['task'] == 'speed' and 'recheck' in r['variant']]
    ld = a['notes'].split('load avg ')[-1]
    body.append([nm(m), f"{a['pairs_per_s']:.1f} (n={a['n']}, load {ld})", f"{rc[-1]['pairs_per_s']:.1f}" if rc else '-', f"{a['params_m']:.1f}", f"{a['disk_mb']:.0f}", f"{20000 / (rc[-1]['pairs_per_s'] if rc else a['pairs_per_s']) * 2:.0f}"])
tab(['model', 'pairs/s in-run', 'pairs/s interleaved recheck', 'params M', 'disk MB', 'est s/20k pairs x86'], body)
