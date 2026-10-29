"""A3 unsure signature: print the 39 unsure rows, test text and key/time features, report precision/recall of rules."""
import sys; sys.path.insert(0, '/tmp/veridyct-rev')
import re
from collections import Counter, defaultdict
from datetime import date
from rev_common import load, H, V

rows, lex = load()
D = lambda r: date.fromisoformat(r['date']).toordinal()
by_page = defaultdict(list)
for r in rows: by_page[r['page']].append(r)
by_key = defaultdict(list)
for r in rows:
    for f in r['facts']: by_key[H.key(f)].append(r)
HEDGE = re.compile(r"\b(about|around|reportedly|roughly|may|might|could|expected|expects?|planned|plans?|up to|likely|probably|should|"
                   r"will|aims?|aiming|target(?:s|ed)?|estimated?|rumou?red|said to|allegedly|apparently|hopes?|intends?|soon|"
                   r"preview|beta|pilot|trial|testing|tests|early|leak(?:ed)?|unconfirmed|sources?|if|would|next)\b", re.I)
FUT = re.compile(r"\b(will|going to|next (?:week|month|year|quarter)|plans? to|expected to|set to|due to|coming|upcoming|later this)\b", re.I)
feats = {}
for r in rows:
    p = by_page[r['page']]; pos = p.index(r)
    keys = [H.key(f) for f in r['facts']]
    others = [o for k in keys for o in by_key[k] if o['idx'] != r['idx']]
    tru = [o for o in others if o['label'] == 'true']
    cands = V.extract_values(r['text'], lex)
    feats[r['idx']] = dict(
        hedge=bool(HEDGE.search(r['text'])), future=bool(FUT.search(r['text'])),
        approx_flag=any('approx' in c['flags'] or 'range' in c['flags'] for c in cands),
        gold_op=any('op' in f['value'] for f in r['facts']),
        key_no_other_row=not others, key_no_true_row=not tru,
        no_true_before=not any(D(o) <= D(r) for o in tru), no_true_after=not any(D(o) >= D(r) for o in tru),
        first=pos == 0, last=pos == len(p) - 1, single_row_page=len(p) == 1,
        no_subject_mention=not any(n in {f['subject'] for f in r['facts']} for _, _, n in V.find_entities(r['text'], lex)),
        multi_fact=len(r['facts']) > 1, kind=r['facts'][0]['value']['kind'])
U = [r for r in rows if r['label'] == 'unsure']
print(f'UNSURE rows: {len(U)}')
for r in U:
    f = feats[r['idx']]; fa = r['facts'][0]
    near = sorted(((D(o) - D(r), o['label'], H.value_equal(o['facts'][[H.key(x) for x in o['facts']].index(H.key(fa))]['value'], fa['value']))
                   for o in by_key[H.key(fa)] if o['idx'] != r['idx']), key=lambda t: abs(t[0]))[:4]
    print(f"{r['id']:7s} {r['date']} pos={by_page[r['page']].index(r)}/{len(by_page[r['page']])} | {r['text']} | {fa['subject']}.{fa['attribute']}={fa['value']}"
          f" | same-key rows (days,label,same_value): {near}")
print('\nfeature: unsure share / true share / false share, and precision/recall for unsure')
lab = {r['idx']: r['label'] for r in rows}
n_l = Counter(lab.values())
for k in ['hedge', 'future', 'approx_flag', 'gold_op', 'key_no_other_row', 'key_no_true_row', 'no_true_before', 'no_true_after',
          'first', 'last', 'single_row_page', 'no_subject_mention', 'multi_fact']:
    hit = Counter(lab[i] for i, f in feats.items() if f[k])
    tp = hit['unsure']; npos = sum(hit.values())
    print(f"  {k:20s} unsure {tp / n_l['unsure']:.3f}  true {hit['true'] / n_l['true']:.3f}  false {hit['false'] / n_l['false']:.3f}  "
          f"P={tp / npos if npos else 0:.3f} R={tp / n_l['unsure']:.3f} (fires on {npos})")
print('kind x label:', sorted(Counter((f['kind'], lab[i]) for i, f in feats.items() if lab[i] == 'unsure').items()))
print('unsure share by kind:', {k: round(sum(1 for i, f in feats.items() if f['kind'] == k and lab[i] == 'unsure') /
      sum(1 for f in feats.values() if f['kind'] == k), 3) for k in sorted({f['kind'] for f in feats.values()})})
# unsure vs same-key rows: does an unsure row disagree with a true row of its key?
agree = Counter()
for r in U:
    fa = r['facts'][0]
    t = [o for o in by_key[H.key(fa)] if o['idx'] != r['idx'] and o['label'] == 'true']
    vals = [x['value'] for o in t for x in o['facts'] if H.key(x) == H.key(fa)]
    agree['no true row of key' if not t else 'equals some true value' if any(H.value_equal(v, fa['value']) for v in vals) else 'differs from all true values'] += 1
print('unsure vs true rows of same key:', dict(agree))
