"""Extraction metrics of forms/<tag>/<world>.jsonl against the world's gold (the ONLY reader of gold/).
Per-assertion P/R/F1 on (subject, attribute) and (subject, attribute, typed value exact); row exact form match;
interval exact match on anchors; anchors vs targets; slices by distractor, arity, track, template_family.
Usage: python -I measure.py --worlds dev cal ... [--forms-dir /tmp/veridyct-evalsuite/forms/B] [--tag B] [--slices]"""
import argparse, json, os, sys, time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import DATA, WORLDS

GOLD = dict(WORLDS, clean=WORLDS['dev'])  # clean = development rows with the asides removed (ablation.json)


def norm(v):
    if isinstance(v, dict): return {k: norm(x) for k, x in v.items()}
    return float(f'{v:.9g}') if isinstance(v, (int, float)) and not isinstance(v, bool) else v  # gold float noise: 3.7699999999999996 == 3.77


def vkey(v): return json.dumps(norm(v), sort_keys=True)


class Acc:
    def __init__(self): self.c = Counter()

    def add(self, gold, pred, interval_ok=None):
        c = self.c
        gp, pp = Counter((f['subject'], f['attribute']) for f in gold), Counter((f['subject'], f['attribute']) for f in pred)
        gv = Counter((f['subject'], f['attribute'], vkey(f['value'])) for f in gold)
        pv = Counter((f['subject'], f['attribute'], vkey(f['value'])) for f in pred)
        c['rows'] += 1; c['g'] += sum(gp.values()); c['p'] += sum(pp.values())
        c['tp_pair'] += sum((gp & pp).values()); c['tp_val'] += sum((gv & pv).values())
        c['row_exact'] += gv == pv; c['row_pair_exact'] += gp == pp
        if interval_ok is not None: c['int_n'] += 1; c['int_ok'] += interval_ok

    def metrics(self):
        c, f = self.c, lambda a, b: a / b if b else 0.0
        out = dict(rows=c['rows'], gold_assertions=c['g'], pred_assertions=c['p'])
        for k in ('pair', 'val'):
            p, r = f(c['tp_' + k], c['p']), f(c['tp_' + k], c['g'])
            out.update({f'{k}_p': round(p, 4), f'{k}_r': round(r, 4), f'{k}_f1': round(f(2 * p * r, p + r), 4)})
        out['row_exact'] = round(f(c['row_exact'], c['rows']), 4); out['row_pair_exact'] = round(f(c['row_pair_exact'], c['rows']), 4)
        if c['int_n']: out['interval_acc'] = round(f(c['int_ok'], c['int_n']), 4)
        return out


def measure(world, forms_dir):
    gold = [json.loads(l) for l in open(f'{DATA}/{GOLD[world]}/gold/rows.jsonl', encoding='utf-8')]
    pred = {}
    for l in open(f'{forms_dir}/{world}.jsonl', encoding='utf-8'):
        o = json.loads(l); pred[o['id']] = o
    acc = defaultdict(Acc)
    for g in gold:
        p = pred.get(g['id'], dict(assertions=[], interval=None))
        part = 'anchor' if g['visible'] else 'target'
        iv = (p.get('interval') == g['validity_qualifier']) if g['visible'] else None
        keys = ['all', part, f'{part}|distractor={"yes" if g["distractors"] else "no"}', f'{part}|arity={min(len(g["form"]), 4)}',
                f'{part}|track={g["track"]}', f'{part}|family={g["template_family"]}', f'{part}|ctx={"yes" if g["context_row_id"] else "no"}']
        for k in keys: acc[k].add(g['form'], p['assertions'], iv if k in ('all', part) else None)
    return {k: v.metrics() for k, v in sorted(acc.items())}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--worlds', nargs='+', required=True); ap.add_argument('--forms-dir', default='/tmp/veridyct-evalsuite/forms/B')
    ap.add_argument('--tag', default='B'); ap.add_argument('--slices', action='store_true'); ap.add_argument('--log', action='store_true')
    a = ap.parse_args()
    for w in a.worlds:
        m = measure(w, a.forms_dir)
        show = m if a.slices else {k: m[k] for k in ('all', 'anchor', 'target') if k in m}
        for k, v in show.items():
            print(f'{w:9s} {k:42s} ' + ' '.join(f'{x}={y}' for x, y in v.items()))
        if a.log:
            with open('/tmp/veridyct-evalsuite/results/B.jsonl', 'a') as f:
                f.write(json.dumps(dict(ts=time.strftime('%Y-%m-%dT%H:%M:%S'), worker='B', tag=a.tag, task='extraction', world=w, metrics=m)) + '\n')
