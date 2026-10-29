"""Worker D, task 1+2: B's extractor on REAL practice prose under page-grouped 5-fold CV (harness page_folds).
Per fold: Extractor(train folds only) runs over ALL rows in id order (text-only context, so the previous-row subject
is the real previous row) and keeps the held-out rows. Also a non-CV run (trained on all rows) as an upper bound.
Writes D/forms_cv.jsonl, D/forms_all.jsonl, D/extract_metrics.json, D/errors.txt; appends to results/D.jsonl.
Run: /tmp/veridyct-bench/.venv/bin/python -I run_cv.py"""
import json, os, sys, time
from collections import Counter, defaultdict

for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'): os.environ[k] = '2'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(1, '/tmp/veridyct-emb/common')
import harness as H  # load(), page_folds(): practice.csv copy is byte-identical to VERIDYCT/data/practice.csv
import extract as E
import values as V

RES = '/tmp/veridyct-evalsuite/results/D.jsonl'
# pure lexicon (no B partial aliases) for the 'gold subject named in the row' split, any case (value contract rule)
LEX0 = dict(subjects={s['name']: dict(aliases=list(s['aliases']), attributes=s['attributes']) for s in E.L['subjects']},
            events=E.L['events'])


def norm(v):  # B's measure.py: numbers to 9 significant digits
    if isinstance(v, dict): return {k: norm(x) for k, x in v.items()}
    return float(f'{v:.9g}') if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def vkey(v): return json.dumps(norm(v), sort_keys=True)


def named(r): return {n for _, _, n in V.find_entities(r['text'], LEX0, strict_case=False)}


class Acc:  # B's measure.py Acc, plus first-assertion subject/attribute/value accuracy for the single-fact comparison
    def __init__(self): self.c = Counter()

    def add(self, gold, pred):
        c = self.c
        gp, pp = Counter((f['subject'], f['attribute']) for f in gold), Counter((f['subject'], f['attribute']) for f in pred)
        gv = Counter((f['subject'], f['attribute'], vkey(f['value'])) for f in gold)
        pv = Counter((f['subject'], f['attribute'], vkey(f['value'])) for f in pred)
        c['rows'] += 1; c['g'] += sum(gp.values()); c['p'] += sum(pp.values())
        c['tp_pair'] += sum((gp & pp).values()); c['tp_val'] += sum((gv & pv).values())
        c['row_exact'] += gv == pv; c['row_pair_exact'] += gp == pp
        if len(gold) == 1:
            g, p = gold[0], (pred[0] if pred else None)
            c['sf'] += 1; c['sf_subj'] += bool(p and p['subject'] == g['subject'])
            c['sf_pair'] += bool(p and (p['subject'], p['attribute']) == (g['subject'], g['attribute']))
            c['sf_first_exact'] += bool(p and (p['subject'], p['attribute'], vkey(p['value'])) ==
                                        (g['subject'], g['attribute'], vkey(g['value'])))

    def metrics(self):
        c, f = self.c, lambda a, b: a / b if b else float('nan')
        out = dict(rows=c['rows'], gold_assertions=c['g'], pred_assertions=c['p'])
        for k in ('pair', 'val'):
            p, r = f(c['tp_' + k], c['p']), f(c['tp_' + k], c['g'])
            out.update({f'{k}_p': round(p, 4), f'{k}_r': round(r, 4), f'{k}_f1': round(f(2 * p * r, p + r), 4)})
        out['row_exact'] = round(f(c['row_exact'], c['rows']), 4); out['row_pair_exact'] = round(f(c['row_pair_exact'], c['rows']), 4)
        if c['sf']:
            out.update(sf_subject=round(c['sf_subj'] / c['sf'], 4), sf_attribute=round(c['sf_pair'] / c['sf'], 4),
                       sf_first_exact=round(c['sf_first_exact'] / c['sf'], 4))
        return out


def extract(rows, folds, page_ctx=0):
    """-> {id: output}; folds=None means one model trained on all rows (non-CV upper bound)."""
    out, unseen = {}, Counter()
    for tr, te in (folds or [(range(len(rows)), range(len(rows)))]):
        ex = E.Extractor([rows[i] for i in tr])
        keep = {rows[i]['id'] for i in te}
        for o in ex.run_rows(rows, page_ctx):
            if o['id'] in keep: out[o['id']] = o
        for i in te:  # gold facts whose attribute never occurs in the training folds (kind unknown -> KIND_ANY)
            for f in rows[i]['facts']: unseen['facts'] += 1; unseen['unseen'] += ex.kind.get(f['attribute'], E.KIND_ANY) == E.KIND_ANY
    return out, unseen


def measure(rows, pred):
    acc = defaultdict(Acc)
    for r in rows:
        g, p = r['facts'], pred[r['id']]['assertions']
        nm = named(r)
        keys = ['all', 'single' if len(g) == 1 else 'multi', ('single|' if len(g) == 1 else 'multi|') +
                ('named' if all(f['subject'] in nm for f in g) else 'not_named'),
                'named' if all(f['subject'] in nm for f in g) else 'not_named']
        for k in keys: acc[k].add(g, p)
    return {k: v.metrics() for k, v in sorted(acc.items())}


def main(page_ctx=0):
    sfx = {0: '', 1: '_pagectx', 2: '_pagectx_all'}[page_ctx]
    rows, _ = H.load()
    folds = H.page_folds(rows)
    res = {}
    for tag, fl in (('cv', folds), ('all', None)):
        t0 = time.time()
        pred, unseen = extract(rows, fl, page_ctx)
        with open(f'{HERE}/forms_{tag}{sfx}.jsonl', 'w', encoding='utf-8') as f:
            for r in rows: f.write(json.dumps(pred[r['id']], ensure_ascii=False) + '\n')
        m = measure(rows, pred)
        m['_unseen_attr_facts'] = dict(unseen); m['_seconds'] = round(time.time() - t0, 1)
        res[tag] = m
        for k, v in m.items():
            print(f'{tag + sfx:16s} {k:20s} ' + (' '.join(f'{x}={y}' for x, y in v.items()) if isinstance(v, dict) else str(v)), flush=True)
        with open(RES, 'a') as f:
            f.write(json.dumps(dict(ts=time.strftime('%Y-%m-%dT%H:%M:%S'), worker='D', task='practice_extraction',
                                    regime='page-grouped 5-fold CV' if tag == 'cv' else 'trained on all rows (upper bound)',
                                    extractor='B/extract.py v1 (D copy)' + (f' + D post-hoc page_ctx={page_ctx}' if page_ctx else ''), metrics=m)) + '\n')
    json.dump(res, open(f'{HERE}/extract_metrics{sfx}.json', 'w'), indent=1)


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
