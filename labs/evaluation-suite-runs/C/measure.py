"""Extraction metrics of forms/C/<world>.jsonl against gold forms (gold is read ONLY here).
Usage: python -I measure.py --world dev [--forms-dir ...] [--tag final] [--errors N] [--no-log]"""
import argparse, collections, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core as C
from extract import WORLDS

GOLD = dict(WORLDS, clean=WORLDS['dev'])  # the clean ablation keeps dev ids/facts; its answers are dev gold (ablation.json)
HELD_OUT = {'cal', 'sealed', 'extcal', 'extsealed'}


def match(G, P):
    """-> (pair TP, triple TP) with multiset semantics."""
    pg = collections.Counter((g['subject'], g['attribute']) for g in G)
    pp = collections.Counter((p['subject'], p['attribute']) for p in P)
    pair = sum((pg & pp).values())
    used, trip = set(), 0
    for p in P:
        for j, g in enumerate(G):
            if j not in used and g['subject'] == p['subject'] and g['attribute'] == p['attribute'] and C.val_eq(g['value'], p['value']):
                used.add(j); trip += 1; break
    return pair, trip


def classify(G, P, text):
    """One error class per wrong row (first that applies)."""
    if len(P) < len(G): return 'missed assertion (segmentation/aside cut)'
    if len(P) > len(G): return 'extra assertion (aside kept/over-split)'
    gs = sorted((g['subject'], g['attribute']) for g in G); ps = sorted((p['subject'], p['attribute']) for p in P)
    if gs != ps:
        ga = sorted(g['attribute'] for g in G); pa = sorted(p['attribute'] for p in P)
        if ga == pa: return 'subject wrong'
        gsub = sorted(g['subject'] for g in G); psub = sorted(p['subject'] for p in P)
        return 'attribute wrong' if gsub == psub else 'subject+attribute wrong'
    for g in G:
        p = next((p for p in P if (p['subject'], p['attribute']) == (g['subject'], g['attribute']) and not C.val_eq(g['value'], p['value'])), None)
        if p is None: continue
        gv, pv = g['value'], p['value'] or {}
        if gv.get('op') != pv.get('op'): return 'value op (%s): gold %s pred %s' % (gv['kind'], gv.get('op'), pv.get('op'))
        if gv.get('unit') != pv.get('unit'): return 'value unit (%s)' % gv['kind']
        return 'value wrong (%s)' % gv['kind']
    return 'other'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--world', required=True); ap.add_argument('--data', default='/Users/mogaeduard/Downloads/evaluation-data')
    ap.add_argument('--forms-dir', default='/tmp/veridyct-evalsuite/forms/C'); ap.add_argument('--tag', default='dev-run')
    ap.add_argument('--errors', type=int, default=0); ap.add_argument('--no-log', action='store_true')
    ap.add_argument('--only', default='', help='keep gold rows whose template or aside family is in this comma list')
    a = ap.parse_args()
    gold = [json.loads(l) for l in open(os.path.join(a.data, GOLD[a.world], 'gold/rows.jsonl'), encoding='utf-8')]
    if a.only:
        keep = set(a.only.split(','))
        gold = [g for g in gold if keep & ({g['template_family']} | {d['family'] for d in g['distractors']})]
    pred = {}
    for l in open(os.path.join(a.forms_dir, a.world + '.jsonl'), encoding='utf-8'):
        o = json.loads(l); pred[o['id']] = o
    M = {k: collections.Counter() for k in ('anchors', 'targets', 'all')}
    kind_n, kind_ok = collections.Counter(), collections.Counter()
    errs = collections.defaultdict(list)
    for g in gold:
        o = pred.get(g['id'], dict(assertions=[], interval=None))
        G, P = g['form'], o['assertions']
        pair, trip = match(G, P)
        exact = trip == len(G) == len(P)
        for part in ('anchors' if g['visible'] else 'targets', 'all'):
            m = M[part]
            m['rows'] += 1; m['gold'] += len(G); m['pred'] += len(P); m['pair_tp'] += pair; m['trip_tp'] += trip; m['row_exact'] += exact
            iv_g = g['validity_qualifier'] or None; iv_p = o.get('interval')
            m['iv_ok'] += (iv_g == iv_p); m['iv_gold'] += bool(iv_g)
            m['iv_exact_when_gold'] += bool(iv_g) and iv_g == iv_p
        for x in G:
            same = [p for p in P if (p['subject'], p['attribute']) == (x['subject'], x['attribute'])]
            if same:
                kind_n[x['value']['kind']] += 1; kind_ok[x['value']['kind']] += any(C.val_eq(x['value'], p['value']) for p in same)
        if not exact:
            errs[classify(G, P, g['text'])].append((g['text'], G, P))
    res = dict(worker='C', tag=a.tag, world=a.world, only=a.only or None, held_out=a.world in HELD_OUT, time=time.strftime('%Y-%m-%d %H:%M:%S'))
    for part, m in M.items():
        if not m['rows']: continue
        d = {}
        for lvl in ('pair', 'trip'):
            pr = m[lvl + '_tp'] / max(1, m['pred']); rc = m[lvl + '_tp'] / max(1, m['gold'])
            d[lvl] = dict(p=round(pr, 4), r=round(rc, 4), f1=round(2 * pr * rc / max(1e-9, pr + rc), 4))
        d['row_exact'] = round(m['row_exact'] / m['rows'], 4); d['rows'] = m['rows']; d['assertions'] = m['gold']
        d['interval_row_acc'] = round(m['iv_ok'] / m['rows'], 4)
        if m['iv_gold']: d['interval_exact_when_stated'] = round(m['iv_exact_when_gold'] / m['iv_gold'], 4)
        res[part] = d
    res['value_acc_given_pair'] = {k: round(kind_ok[k] / kind_n[k], 4) for k in sorted(kind_n)}
    res['error_classes'] = {k: len(v) for k, v in sorted(errs.items(), key=lambda kv: -len(kv[1]))}
    print(json.dumps(res, indent=1))
    if not a.no_log:
        os.makedirs('/tmp/veridyct-evalsuite/results', exist_ok=True)
        with open('/tmp/veridyct-evalsuite/results/C.jsonl', 'a') as f:
            f.write(json.dumps(res) + '\n')
    for k, v in sorted(errs.items(), key=lambda kv: -len(kv[1]))[:12]:
        for text, G, P in v[:a.errors]:
            print('\n##', k, '|', text)
            print('  GOLD', [(x['subject'], x['attribute'], x['value']) for x in G])
            print('  PRED', [(x['subject'], x['attribute'], x['value']) for x in P])


if __name__ == '__main__':
    main()
