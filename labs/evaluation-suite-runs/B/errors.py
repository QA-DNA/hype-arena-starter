"""Error listing for development-only worlds (dev, pilot, prac, diag). Usage: python -I errors.py --world dev [--n 40] [--classes]"""
import argparse, json, os, sys, random
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure import GOLD, DATA, vkey
ALLOWED = {'dev', 'pilot', 'prac', 'diag'}

def classify(g, p, text):
    gk = {(f['subject'], f['attribute']): f['value'] for f in g['form']}
    pk = {(f['subject'], f['attribute']): f['value'] for f in p['assertions']}
    out = []
    for k, v in gk.items():
        if k in pk:
            if vkey(pk[k]) != vkey(v):
                pv = pk[k]
                if pv['kind'] != v['kind']: out.append('value:kind')
                elif pv.get('op') != v.get('op'): out.append(f"value:op {v.get('op')}->{pv.get('op')}")
                elif pv.get('unit') != v.get('unit'): out.append(f"value:unit")
                elif pv.get('per') != v.get('per'): out.append('value:per')
                else: out.append(f"value:{v['kind']}")
        else:
            same_s = [a for (s, a) in pk if s == k[0] and (s, a) not in gk]
            same_a = [s for (s, a) in pk if a == k[1] and (s, a) not in gk]
            if same_s: out.append('pair:wrong_attribute')
            elif same_a: out.append('pair:wrong_subject')
            else: out.append('pair:missed' + (' (ctx row)' if g['context_row_id'] else ''))
    for k in pk:
        if k not in gk and not any(k[0] == s for s, a in gk) and not any(k[1] == a for s, a in gk):
            out.append('pair:spurious')
    return out

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--world', default='dev'); ap.add_argument('--n', type=int, default=30)
    ap.add_argument('--cls'); ap.add_argument('--forms-dir', default='/tmp/veridyct-evalsuite/forms/B')
    a = ap.parse_args(); assert a.world in ALLOWED, 'held-out world: no error inspection'
    gold = [json.loads(l) for l in open(f'{DATA}/{GOLD[a.world]}/gold/rows.jsonl')]
    pred = {json.loads(l)['id']: json.loads(l) for l in open(f'{a.forms_dir}/{a.world}.jsonl')}
    C, ex = Counter(), {}
    for g in gold:
        p = pred[g['id']]
        for c in classify(g, p, g['text']):
            C[c] += 1; ex.setdefault(c, []).append(g)
    for c, n in C.most_common(): print(n, c)
    random.seed(0)
    for c in ([a.cls] if a.cls else list(C)[:0]):
        for g in random.sample(ex[c], min(a.n, len(ex[c]))):
            print('---', g['id'], g['visible'], 'ctx' if g['context_row_id'] else ''); print(g['text'])
            print('  G', [(f['subject'], f['attribute'], f['value']) for f in g['form']])
            print('  P', [(f['subject'], f['attribute'], f['value']) for f in pred[g['id']]['assertions']])
