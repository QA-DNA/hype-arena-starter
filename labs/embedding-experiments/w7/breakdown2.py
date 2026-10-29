import sys, runpy, io, contextlib, json
from collections import Counter
sys.argv = ['measure.py', '--no-log']
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ns = runpy.run_path('/tmp/veridyct-emb/w7/measure.py')
E2E, sf, pred, rows, CAND_SF, primary = ns['E2E'], ns['sf'], ns['pred'], ns['rows'], ns['CAND_SF'], ns['primary']
kind_of = {}
for r in rows:
    for f in r['facts']: kind_of[f['attribute']] = f['value']['kind']
for name in ['pred_attr/first_all', 'gold_attr/first_all']:
    res, errs = E2E[name]
    cause = Counter()
    for r, f, a, sel in errs:
        if sel is None: cause['no candidate of the implied kind / kind unknown'] += 1
        elif a == f['attribute']: cause['attr right, another candidate of the right kind picked'] += 1
        elif kind_of.get(a) == f['value']['kind']: cause['attr wrong, same kind, other candidate'] += 1
        else: cause['attr wrong, kind differs'] += 1
    print(name, len(errs), dict(cause))
# ambiguity: rows with >1 primary candidate of the gold kind
amb = Counter()
for i, r in enumerate(sf):
    g = r['facts'][0]['value']['kind']
    n = len([c for c in primary(CAND_SF[i]) if c['kind'] == g])
    amb[g, n > 1] += 1
tot = Counter()
for (k, m), c in amb.items(): tot[m] += c
print('rows with >1 primary candidate of the gold kind:', tot[True], 'of', len(sf), {k: amb[k, True] for k in ['quantity','money','duration','percent','date','version','boolean','name']})
