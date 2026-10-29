"""Builds the markdown tables from results/w4.jsonl (own-N) and scores/*.npz (common-N prefix recomputation). No torch."""
import sys, json, glob, os; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H
import numpy as np
from sklearn.metrics import roc_auc_score
ROOT = '/tmp/veridyct-emb/w4'
R = [json.loads(l) for l in open(H.results_path('w4'))]
ORDER = ['ce-xsmall', 'ce-small', 'ce-base', 'ce-minilm2-l6-h768', 'ce-distilroberta', 'ml-base-mnli-fever-anli', 'ml-base-zeroshot2',
         'ml-large-zeroshot2', 'ml-modernbert-base-zeroshot2', 'ts-deberta-small-long-nli', 'albert-xlarge-vitaminc-mnli', 'bart-large-mnli']
BIN = {'ml-base-zeroshot2', 'ml-large-zeroshot2', 'ml-modernbert-base-zeroshot2'}
f3 = lambda x: 'n/a' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:.3f}'
def get(model, task, variant_prefix):
    c = [r for r in R if r['model'] == model and r['task'] == task and r['variant'].startswith(variant_prefix)]
    return c[-1] if c else None
def auc(y, s):
    y = np.asarray(y, int); return float(roc_auc_score(y, s)) if 0 < y.sum() < len(y) else float('nan')
models = [m for m in ORDER if any(r['model'] == m for r in R)]
KINDS = ['quantity', 'money', 'percent', 'date', 'duration', 'version', 'name', 'boolean']

def md(head, body):
    print('| ' + ' | '.join(head) + ' |'); print('|' + '---|' * len(head))
    for b in body: print('| ' + ' | '.join(map(str, b)) + ' |')
    print()

# ---------- own-N tables ----------
print('### nli_conflict (own N; score = p_contra, binary models use p_not_entail marked *)')
body = []
for m in models:
    r = get(m, 'nli_conflict', 'p_')
    if not r: body.append([m, 'FAILED'] + [''] * 11); continue
    bk, mt = r['by_kind'], r['metrics']
    body.append([m + ('*' if m in BIN else ''), r['n'], f3(mt['auc']), f3(mt['ap']), f3(mt['f1_max'])] + [f3(bk[k]['auc']) for k in KINDS])
md(['model', 'n', 'AUC', 'AP', 'F1max'] + KINDS, body)
print('### nli_conflict, 3-class models, score = 1 - p_entail (neutral counts as conflict)')
body = []
for m in models:
    r = get(m, 'nli_conflict', '1-p_entail')
    if r: body.append([m, r['n'], f3(r['metrics']['auc']), f3(r['metrics']['ap']), f3(r['metrics']['f1_max'])] + [f3(r['by_kind'][k]['auc']) for k in KINDS])
md(['model', 'n', 'AUC', 'AP', 'F1max'] + KINDS, body)

print('### nli_anchor forward (premise=anchor, hypothesis=row; y = row is false)')
body = []
for m in models:
    a = get(m, 'nli_anchor', 'forward:p_'); b = get(m, 'nli_anchor', 'forward:1-p_entail')
    if not a: body.append([m, 'FAILED'] + [''] * 9); continue
    d = a['detail']
    body.append([m + ('*' if m in BIN else ''), a['n'], d['n_pairs'], f3(a['metrics']['auc']), f3(a['metrics']['ap']), f3(a['metrics']['f1_max']), f3(b['metrics']['auc']),
                 f3(d['p_contra_nearest_auc_all']), f3(d['p_contra_max_auc_nearest_value_differs']), f3(d['p_contra_max_auc_nearest_value_same']),
                 f3(d['p_contra_nearest_auc_nearest_value_differs']), f3(d['p_contra_nearest_auc_nearest_value_same']), f3(d['auc_value_differs_vs_p_contra_nearest'])])
md(['model', 'rows', 'pairs', 'AUC pc_max', 'AP', 'F1max', 'AUC 1-pe_max', 'AUC pc_near', 'pcmax AUC differs', 'pcmax AUC same', 'pcnear AUC differs', 'pcnear AUC same', 'AUC(value differs; pc_near)'], body)
r0 = next((get(m, 'nli_anchor', 'forward:p_') for m in models if get(m, 'nli_anchor', 'forward:p_')), None)
if r0: d = r0['detail']; print(f"subset sizes (full run): value-differs n={d['n_differs']} (false {d['pos_differs']}), value-same n={d['n_same']} (false {d['pos_same']})\n")
body = []
for m in models:
    a = get(m, 'nli_anchor', 'reverse:p_'); b = get(m, 'nli_anchor', 'reverse:1-p_entail'); f = get(m, 'nli_anchor', 'forward:p_')
    if a: body.append([m, a['n'], f3(a['metrics']['auc']), f3(b['metrics']['auc']), f3(a['detail']['p_contra_max_auc_nearest_value_differs']), f3(a['detail']['p_contra_max_auc_nearest_value_same']), f3(f['metrics']['auc'])])
if body:
    print('### nli_anchor reverse (premise=row, hypothesis=anchor)')
    md(['model', 'rows', 'AUC pc_max', 'AUC 1-pe_max', 'pcmax AUC differs', 'pcmax AUC same', 'forward AUC pc_max (own N)'], body)

print('### nli_attr (acc = acc_all = acc_unseen; train_counts 0)')
body = []
for m in models:
    for tn in ('tmpl1', 'tmpl2'):
        r = get(m, 'nli_attr', tn)
        if r: body.append([m, tn, r['n'], r['n_pairs'], f3(r['metrics']['acc_all']), f3(r['chance_acc'])])
md(['model', 'template', 'rows', 'pairs', 'acc', 'chance'], body)

print('### speed (2 threads, bs 32, longest first)')
body = []
for m in models:
    r = get(m, 'speed', 'bs32')
    if r: body.append([m, f"{r['pairs_per_s']:.1f}", r['n'], f"{r['params_m']:.1f}", f"{r['disk_mb']:.0f}", f"{r['metrics']['est_sec_20k_pairs_x86']:.0f}"])
md(['model', 'pairs/s', 'pairs timed', 'params M', 'disk MB', 'est s / 20k pairs x86'], body)

# ---------- common-N recomputation from stored logits ----------
def lm_of(m):
    d = f"{ROOT}/models/{json.load(open(glob.glob(f'{ROOT}/models/*')[0] + '/config.json')) and ''}"
    return None
def load_lm(m):
    rid = {r['model']: None for r in R}
    import re
    cand = glob.glob(f"{ROOT}/models/*/config.json")
    key2dir = {'ce-xsmall': 'cross-encoder--nli-deberta-v3-xsmall', 'ce-small': 'cross-encoder--nli-deberta-v3-small', 'ce-base': 'cross-encoder--nli-deberta-v3-base',
               'ce-minilm2-l6-h768': 'cross-encoder--nli-MiniLM2-L6-H768', 'ce-distilroberta': 'cross-encoder--nli-distilroberta-base',
               'ml-base-mnli-fever-anli': 'MoritzLaurer--DeBERTa-v3-base-mnli-fever-anli', 'ml-base-zeroshot2': 'MoritzLaurer--deberta-v3-base-zeroshot-v2.0',
               'ml-large-zeroshot2': 'MoritzLaurer--deberta-v3-large-zeroshot-v2.0', 'ml-modernbert-base-zeroshot2': 'MoritzLaurer--ModernBERT-base-zeroshot-v2.0',
               'ts-deberta-small-long-nli': 'tasksource--deberta-small-long-nli', 'albert-xlarge-vitaminc-mnli': 'tals--albert-xlarge-vitaminc-mnli', 'bart-large-mnli': 'facebook--bart-large-mnli'}
    p = f"{ROOT}/models/{key2dir[m]}/config.json"
    if not os.path.exists(p): p = glob.glob(f"/tmp/veridyct-bench/hf/hub/models--{key2dir[m].replace('--', '--')}/snapshots/*/config.json")[0]
    lab = json.load(open(p))['id2label']; mp = {}
    for i, n in lab.items():
        n = n.lower().replace('_', ' ')
        if n == 'not entailment': mp['ne'] = int(i)
        elif n.startswith('entail') or n == 'supports': mp['e'] = int(i)
        elif n.startswith('contradict') or n == 'refutes': mp['c'] = int(i)
        elif n.startswith('neutral') or n == 'not enough info': mp['n'] = int(i)
    return mp
def pe_pc(lg, mp):
    z = lg.astype(np.float64); P = np.exp(z - z.max(1, keepdims=True)); P /= P.sum(1, keepdims=True)
    return P[:, mp['e']], P[:, mp['c']] if 'c' in mp else P[:, mp['ne']]

rows, lex = H.load(); byidx = {r['idx']: r for r in rows}
Pr = H.same_key_pairs(rows)
kind_of = lambda k: byidx[Pr[k][0]]['facts'][0]['value']['kind']
def common(task_file, nfun):
    out = {}
    for m in models:
        p = f'{ROOT}/scores/{m}.{task_file}.npz'
        if os.path.exists(p): out[m] = np.load(p, allow_pickle=True)
    return out
print('### common-N views (prefix of the shared seeded order, recomputed from stored logits)')
C = common('conflict', None)
if C:
    C = {m: z for m, z in C.items() if len(z['sel']) >= 500}
    N = min(len(z['sel']) for z in C.values()); print(f'conflict common N = {N} pairs (prefix of the stratified order; models with < 500 pairs excluded here)')
    body = []
    for m, z in C.items():
        sel = z['sel'][:N]; mp = load_lm(m); pe, pc = pe_pc(z['logits'][:N], mp)
        y = np.array([not Pr[k][2] for k in sel], int); kd = np.array([kind_of(k) for k in sel])
        body.append([m + ('*' if m in BIN else ''), f3(auc(y, pc)), f3(auc(y, 1 - pe))] + [f3(auc(y[kd == k], pc[kd == k])) for k in KINDS])
    md(['model', 'AUC p_contra', 'AUC 1-p_entail'] + KINDS, body)
    print('per-kind n/n_differ in the common prefix: ' + ', '.join(f"{k}={int((np.array([kind_of(q) for q in next(iter(C.values()))['sel'][:N]]) == k).sum())}" for k in KINDS) + '\n')
A = common('anchor_forward', None)
if A:
    A = {m: z for m, z in A.items() if len(z['rows']) >= 300}
    M = min(len(z['rows']) for z in A.values()); print(f'anchor common N = {M} rows (models with < 300 rows excluded here)')
    body = []
    for m, z in A.items():
        mp = load_lm(m); pe, pc = pe_pc(z['logits'], mp); pr = z['pair_row']; ys, a1, a2, a3 = [], [], [], []
        for ridx in z['rows'][:M]:
            ix = np.flatnonzero(pr == ridx); ys.append(int(byidx[ridx]['label'] == 'false')); a1.append(pc[ix].max()); a2.append(pe[ix].max()); a3.append(pc[ix[0]])
        body.append([m + ('*' if m in BIN else ''), f3(auc(ys, a1)), f3(auc(ys, 1 - np.array(a2))), f3(auc(ys, a3)), int(sum(ys))])
    md(['model', 'AUC pc_max', 'AUC 1-pe_max', 'AUC pc_near', 'false rows'], body)
T = common('attr_tmpl1', None)
if T:
    T = {m: z for m, z in T.items() if len(z['rows']) >= 150}
    K = min(len(z['rows']) for z in T.values()); print(f'attr common N = {K} rows (models with < 150 rows excluded here)')
    md(['model', f'acc (first {K} rows)'], [[m, f3(float(np.mean([a == b for a, b in zip(z['pred'][:K], z['y'][:K])])))] for m, z in T.items()])

# ---------- model-independent oracle reference for nli_anchor ----------
NA = H.nearest_anchors(rows, 2)
tf = [r for r in H.single_fact_rows(rows) if r['label'] in ('true', 'false') and NA[r['idx']]]
y = np.array([r['label'] == 'false' for r in tf], int)
near = np.array([not NA[r['idx']][0]['same_value'] for r in tf], int)
anyd = np.array([any(not a['same_value'] for a in NA[r['idx']]) for r in tf], int)
print(f"oracle (gold values, no NLI): AUC(y_false; nearest anchor value differs)={auc(y, near):.3f}, AUC(y_false; any of the up-to-4 anchors differs)={auc(y, anyd):.3f}, "
      f"P(nearest differs | false)={near[y == 1].mean():.3f}, P(nearest differs | true)={near[y == 0].mean():.3f}, n={len(tf)}")
