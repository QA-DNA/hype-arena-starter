"""Worker D, task 3 extra: the competition-shaped mix. Labelled pages keep their GOLD forms (practice ships with forms),
hidden pages use the CV-extracted forms; exp.py/v9.py are reloaded per split because they build ROWS/OBS at import.
Run: FIXU=1 python -I e2e_mixed.py <extracted forms jsonl> <tag>"""
import csv, importlib, json, os, sys, time
for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'): os.environ[k] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from e2e import points

ext = {json.loads(l)['id']: json.loads(l)['assertions'] for l in open(sys.argv[1], encoding='utf-8')}
gold = {r['id']: json.loads(r['form']) for r in csv.DictReader(open('/Users/mogaeduard/VERIDYCT/data/practice.csv'))}
tmp = f'{HERE}/forms_mixed_tmp_{sys.argv[2]}.jsonl'
os.environ['FORMS'] = ''
import exp as X
import v9 as M
for reg in ('R80', 'R10'):
    ms, cms, t0 = [], 0, time.time()
    for lab in list(X.splits(reg)):
        with open(tmp, 'w', encoding='utf-8') as f:
            for r in X.ROWS: f.write(json.dumps(dict(id=r['id'], assertions=gold[r['id']] if lab[r['page']] else ext[r['id']])) + '\n')
        os.environ['FORMS'] = tmp
        X = importlib.reload(X); M = importlib.reload(M)
        hid = ~lab[M.PAGE]; yp, conf = M.V['V9lr']()(lab)
        m = M.metrics(M.Y[hid], yp[hid], conf[hid]); ms.append(m); cms = cms + m['cm']
    avg = {k: float(np.mean([m[k] for m in ms])) for k in ms[0] if k != 'cm'}; avg['cm'] = cms
    pts, pat = points(cms)
    rec = dict(ts=time.strftime('%Y-%m-%dT%H:%M:%S'), worker='D', task='e2e_v9_mixed', forms=sys.argv[2], model='V9lr',
               fixu=os.environ.get('FIXU', '1'), regime=reg, acc=round(avg['acc'], 4), false_recall=round(avg['frec'], 4),
               false_precision=round(avg['fprec'], 4), brier=round(avg['brier'], 4), pred_unsure=int(cms[:, 2].sum()),
               cm=cms.tolist(), points_per_row=round(float(pts), 4), always_true_points_per_row=round(float(pat), 4),
               seconds=round(time.time() - t0, 1))
    print(M.fmt('V9lr/mixed-' + sys.argv[2], reg, avg), 'pts/row', rec['points_per_row'], 'always-true', rec['always_true_points_per_row'],
          'pred_unsure', rec['pred_unsure'], 'cm', rec['cm'], f"{rec['seconds']}s", flush=True)
    with open('/tmp/veridyct-evalsuite/results/D.jsonl', 'a') as f: f.write(json.dumps(rec) + '\n')
os.remove(tmp)
