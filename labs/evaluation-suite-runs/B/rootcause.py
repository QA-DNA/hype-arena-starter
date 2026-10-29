"""Root-cause buckets for extraction errors (run AFTER the final extraction). Usage: python -I rootcause.py dev cal sealed synth"""
import json, os, re, sys, random
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure import GOLD, DATA, vkey

def causes(g, p):
    gk = {(f['subject'], f['attribute']): f['value'] for f in g['form']}
    pk = {(f['subject'], f['attribute']): f['value'] for f in p['assertions']}
    t, out = g['text'], []
    miss, extra = [k for k in gk if k not in pk], [k for k in pk if k not in gk]
    for k in gk:
        if k in pk and vkey(pk[k]) != vkey(gk[k]):
            v, w = gk[k], pk[k]
            out.append('value: operator ' + f"{v.get('op')}->{w.get('op')}" if v.get('op') != w.get('op') else
                       'value: unit' if v.get('unit') != w.get('unit') else 'value: kind/number/other')
    if not miss and not extra: return out
    if re.search(r'\b[A-Z]\.\s+\S', t) and len(pk) < len(gk):
        return out + ['clause split blocked: period after a one-letter capital (Series A. / 51 W. / I/O.)']
    for k in miss:
        pe = [e for e in extra if e[0] == k[0]]
        if any(e == ('Hooly Android', 'version') for e in extra) and k[1] == 'shipping_android':
            out.append('entity as noun modifier: "<phone> is on Android version" -> Hooly Android/version')
        elif pe:
            gkind, pkind = gk[k]['kind'], pk[pe[0]]['kind']
            out.append(f'wrong attribute, same subject ({gkind} gold vs {pkind} predicted)' if gkind != pkind else f'wrong attribute, same subject and kind ({k[1]} -> {pe[0][1]})')
        elif any(e[1] == k[1] for e in extra):
            out.append('wrong subject' + (' (previous-row context)' if g['context_row_id'] else ''))
        elif g['context_row_id']:
            out.append('missed: previous-row context assertion')
        else:
            out.append('missed assertion (no candidate)' + (' in row with aside' if g['distractors'] else ''))
    for e in extra:
        if not any(e[0] == k[0] or e[1] == k[1] for k in miss) and not (e == ('Hooly Android', 'version')):
            out.append('spurious assertion' + (' in row with aside' if g['distractors'] else ''))
    return out

if __name__ == '__main__':
    random.seed(0)
    for w in sys.argv[1:]:
        gold = [json.loads(l) for l in open(f'{DATA}/{GOLD[w]}/gold/rows.jsonl')]
        pred = {json.loads(l)['id']: json.loads(l) for l in open(f'/tmp/veridyct-evalsuite/forms/B/{w}.jsonl')}
        C, ex = Counter(), defaultdict(list)
        for g in gold:
            for c in causes(g, pred[g['id']]):
                C[c] += 1; ex[c].append(g)
        print(f'== {w}: {sum(C.values())} error atoms in {sum(1 for g in gold if causes(g, pred[g["id"]]))} rows')
        for c, n in C.most_common(10):
            print(f'{n:5d}  {c}')
            for g in random.sample(ex[c], min(2, len(ex[c]))):
                print('         e.g.', g['id'], '|', g['text'][:160])
                print('            G', [(f['subject'], f['attribute'], f['value'].get('value'), f['value'].get('op')) for f in g['form']][:3])
                print('            P', [(f['subject'], f['attribute'], f['value'].get('value'), f['value'].get('op')) for f in pred[g['id']]['assertions']][:3])
