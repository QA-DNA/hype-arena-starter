"""A5b: TRUE rows that disagree with the latest TRUE row of the same key at or before their date (other page): what are they?"""
import sys; sys.path.insert(0, '/tmp/veridyct-rev')
import json, random
from collections import Counter, defaultdict
from datetime import date
from rev_common import load, H

rows, lex = load()
D = lambda r: date.fromisoformat(r['date']).toordinal()
vk = lambda v: json.dumps(H._norm(v), sort_keys=True)
K = defaultdict(list)
for r in rows:
    for f in r['facts']: K[H.key(f)].append((r, f['value']))
conf, gaps, same_day = [], Counter(), 0
for r in rows:
    if r['label'] != 'true': continue
    for f in r['facts']:
        prev = [(D(o), o, v) for o, v in K[H.key(f)] if o['label'] == 'true' and o['page'] != r['page'] and D(o) <= D(r)]
        if not prev: continue
        d0, o, v = max(prev, key=lambda t: (t[0], t[1]['n']))
        if vk(v) != vk(f['value']):
            later_same = any(vk(v2) == vk(f['value']) and o2['label'] == 'true' and D(o2) < d0 for o2, v2 in K[H.key(f)])
            conf.append((r, f, o, v, D(r) - d0, later_same))
            if D(r) == d0: same_day += 1
print(f'true facts disagreeing with the latest earlier true fact of the key: {len(conf)}; same-day conflicts: {same_day}')
print('gap in days to that earlier true row: quartiles', sorted(c[4] for c in conf)[len(conf) // 4], sorted(c[4] for c in conf)[len(conf) // 2], sorted(c[4] for c in conf)[3 * len(conf) // 4])
print('row value equals an OLDER true value of the key (A..B..A pattern):', sum(c[5] for c in conf))
print('kinds:', Counter(c[1]['value']['kind'] for c in conf).most_common())
random.seed(1)
for r, f, o, v, gap, ls in random.sample(conf, 14):
    print(f"\n  {r['id']} {r['date']} TRUE | {r['text'][:120]} | {f['subject']}.{f['attribute']}={json.dumps(f['value'])}")
    print(f"  {o['id']} {o['date']} TRUE (gap {gap} d) | {o['text'][:120]} | value={json.dumps(v)}")
