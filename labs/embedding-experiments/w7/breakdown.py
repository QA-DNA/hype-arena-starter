import sys, runpy, io, contextlib, json
from collections import Counter
sys.argv = ['measure.py', '--no-log']
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ns = runpy.run_path('/tmp/veridyct-emb/w7/measure.py')
E2E, sf, pred, rows = ns['E2E'], ns['sf'], ns['pred'], ns['rows']
kind_of = {}
for r in rows:
    for f in r['facts']: kind_of[f['attribute']] = f['value']['kind']
# per-kind table
KINDS = ['quantity', 'money', 'duration', 'percent', 'date', 'version', 'boolean', 'name']
print('per-kind exact (n):', {k: E2E['pred_attr/ranked'][0]['per_kind'][k]['n'] for k in KINDS})
for name in ['pred_attr/first_all', 'pred_attr/ranked', 'gold_attr/first_all', 'gold_attr/ranked', 'gold_attr/ranked+fallback', 'gold_attr_gold_kind/first_all', 'gold_attr_gold_kind/ranked']:
    pk = E2E[name][0]['per_kind']
    print(f'{name:32s}', ' '.join(f'{k[:5]}={pk[k]["exact"]:.3f}' for k in KINDS))
# error causes under predicted attribute
res, errs = E2E['pred_attr/ranked']
cause = Counter()
for r, f, a, sel in errs:
    ok_attr = a == f['attribute']
    same_kind = kind_of.get(a) == f['value']['kind']
    unseen = False
    cause[('attr right' if ok_attr else ('attr wrong, same kind' if same_kind else 'attr wrong, other kind'))] += 1
print('value errors under pred_attr/ranked:', len(errs), dict(cause))
# value-correct despite wrong attribute
n = sum(1 for i, r in enumerate(sf) if pred[i] != r['facts'][0]['attribute'])
print('wrong attr rows', n)
# error patterns for value-step with gold attribute and gold kind
res, errs = E2E['gold_attr_gold_kind/ranked']
print('value-step errors with gold attr+kind:', len(errs), Counter(f['value']['kind'] for r, f, a, s in errs))
res, errs = E2E['gold_attr_gold_kind/first_all']
print('first_all errors with gold attr+kind:', len(errs), Counter(f['value']['kind'] for r, f, a, s in errs))
for r, f, a, sel in errs[:0]: pass
