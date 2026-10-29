"""Worker D, task 3 diagnostic: per-row V9lr R80 predictions on a forms file, split by whether the extracted row form is
exact and whether every extracted subject is named in the row text; plus a POST-HOC hybrid (answer 'true' where the
extraction leans on context). Run: FORMS=<forms jsonl> FIXU=1 python -I e2e_rows.py <tag>"""
import json, os, sys
for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'): os.environ[k] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(2, '/tmp/veridyct-emb/common')
import numpy as np
import v9 as M
from run_cv import named, vkey

forms = {json.loads(l)['id']: json.loads(l)['assertions'] for l in open(os.environ.get('SPLIT_FORMS') or os.environ['FORMS'], encoding='utf-8')}  # split masks from these forms
gold = {r['id']: json.loads(r['form']) for r in __import__('csv').DictReader(open(M.DATA + 'practice.csv'))}


def pts(y, p): return float(np.mean(np.where(p == 'unsure', 0, np.where(p == y, 1, -1)))) if len(y) else float('nan')


yp = np.empty(len(M.ROWS), dtype=object)
for lab in M.splits('R80'):
    hid = ~lab[M.PAGE]; o, _ = M.V['V9lr']()(lab); yp[hid] = o[hid]
yp = yp.astype(str); Y = M.Y
exact = np.array([sorted((f['subject'], f['attribute'], vkey(f['value'])) for f in forms[r['id']]) ==
                  sorted((f['subject'], f['attribute'], vkey(f['value'])) for f in gold[r['id']]) for r in M.ROWS])
own = np.array([bool(forms[r['id']]) and {f['subject'] for f in forms[r['id']]} <= named(r) for r in M.ROWS])
out = {}
for nm, m in (('all', np.ones(len(Y), bool)), ('form_exact', exact), ('form_wrong', ~exact),
              ('subjects_named_in_row', own), ('subject_from_context_or_empty', ~own)):
    out[nm] = dict(n=int(m.sum()), acc=round(float(np.mean(Y[m] == yp[m])), 4), points=round(pts(Y[m], yp[m]), 4),
                   always_true_points=round(pts(Y[m], np.full(m.sum(), 'true')), 4),
                   false_rows=int((Y[m] == 'false').sum()), false_caught=int(((Y[m] == 'false') & (yp[m] == 'false')).sum()))
hy = np.where(own, yp, 'true')
out['posthoc_hybrid_V9_where_named_else_true'] = dict(acc=round(float(np.mean(Y == hy)), 4), points=round(pts(Y, hy), 4))
print(os.environ.get('FIXU', '1'), sys.argv[1], json.dumps(out, indent=1))
with open('/tmp/veridyct-evalsuite/results/D.jsonl', 'a') as f:
    f.write(json.dumps(dict(worker='D', task='e2e_v9_rows_R80', forms=sys.argv[1], fixu=os.environ.get('FIXU', '1'), split=out)) + '\n')
