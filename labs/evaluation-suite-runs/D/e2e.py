"""Worker D, task 3: V9lr (the published V9 row) under exp.py's R80 / R10 regimes, on gold or extracted forms.
Run: FORMS=<forms jsonl or empty for gold> FIXU=<1 fixed decide() | 0 original> python -I e2e.py <tag>
Prints exp.py's table row plus pooled-cm counts and arena points (+1 right, -1 wrong, 0 for an 'unsure' answer)."""
import json, os, sys, time
for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'): os.environ[k] = '1'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import v9 as M  # imports D/exp.py (FORMS-aware load)


def points(cm):  # rows = gold (true, false, unsure), cols = prediction
    right = cm[0, 0] + cm[1, 1]; wrong = cm[:, :2].sum() - right; n = cm.sum()
    return (right - wrong) / n, (cm[0].sum() - cm[1].sum() - cm[2].sum()) / n


def main(tag):
    out = []
    nf = [len(r['facts']) for r in M.ROWS]
    info = dict(rows=len(M.ROWS), facts=int(sum(nf)), rows_without_facts=int(sum(n == 0 for n in nf)),
                drops=dict(M.FORM_DROPS), keys=len(M.OBS))
    print(tag, info, flush=True)
    for reg in ('R80', 'R10'):
        t0 = time.time(); M.CHOSEN.clear()
        m = M.run('V9lr', M.V['V9lr'](), reg)
        cm = m['cm']; pts, pts_at = points(cm)
        rec = dict(ts=time.strftime('%Y-%m-%dT%H:%M:%S'), worker='D', task='e2e_v9', forms=tag, model='V9lr',
                   fixu=os.environ.get('FIXU', '1'), regime=reg, acc=round(m['acc'], 4), macro_f1=round(m['mf1'], 4),
                   false_recall=round(m['frec'], 4), false_precision=round(m['fprec'], 4), unsure_recall=round(m['urec'], 4),
                   brier=round(m['brier'], 4), ece=round(m['ece'], 4), coverage=round(m['cov'], 4),
                   pred_unsure=int(cm[:, 2].sum()), gold_unsure=int(cm[2].sum()), cm=cm.tolist(),
                   points_per_row=round(float(pts), 4), always_true_points_per_row=round(float(pts_at), 4),
                   always_true_acc=round(float(cm[0].sum() / cm.sum()), 4), chosen=[list(map(float, c)) for c in M.CHOSEN],
                   seconds=round(time.time() - t0, 1), **info)
        print(M.fmt('V9lr/' + tag, reg, m), 'pts/row', rec['points_per_row'], 'always-true', rec['always_true_points_per_row'],
              'pred_unsure', rec['pred_unsure'], 'cm', rec['cm'], f"{rec['seconds']}s", flush=True)
        with open('/tmp/veridyct-evalsuite/results/D.jsonl', 'a') as f: f.write(json.dumps(rec) + '\n')
        out.append(rec)
    json.dump(out, open(f'{HERE}/e2e_{tag}.json', 'w'), indent=1)


if __name__ == '__main__':
    main(sys.argv[1])
