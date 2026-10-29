"""A5 key density and time: rows per key, agreement, value changes over time, monotonicity, majority decidability."""
import sys; sys.path.insert(0, '/tmp/veridyct-rev')
import json, re, statistics as st
from collections import Counter, defaultdict
from rev_common import load, H

rows, lex = load()
K = defaultdict(list)  # key -> [(row, value)]
for r in rows:
    for f in r['facts']: K[H.key(f)].append((r, f['value']))
cnt = [len(v) for v in K.values()]
print(f'keys {len(K)}; rows per key mean {st.mean(cnt):.2f} median {st.median(cnt)} max {max(cnt)}; keys with 1 row {sum(c == 1 for c in cnt)} ({sum(c == 1 for c in cnt) / len(K):.3f})')
print('histogram', sorted(Counter(cnt).items()))
vk = lambda v: json.dumps(H._norm(v), sort_keys=True)
agree = change = multi = 0; mono = Counter(); kinds = Counter()
def num(v):
    k = v['kind']
    if k == 'version': return tuple(int(x) for x in re.findall(r'\d+', str(v['value'])))
    if k == 'date': return str(v['value'])
    if k == 'boolean': return int(v['value'])
    if k == 'name': return None
    return float(v['value'])
for key, L in K.items():
    T = sorted([(r['date'], r['n'], v) for r, v in L if r['label'] == 'true'])
    if len(T) < 2: continue
    multi += 1
    vals = {vk(v) for _, _, v in T}
    if len(vals) == 1: agree += 1; continue
    change += 1; kinds[T[0][2]['kind']] += 1
    seq = []
    for d, _, v in T:  # collapse runs
        if not seq or vk(seq[-1]) != vk(v): seq.append(v)
    xs = [num(v) for v in seq]
    if None in xs or len({type(x) for x in xs}) > 1 or any(vk({**a, 'value': 0}) != vk({**b, 'value': 0}) for a, b in zip(seq, seq[1:])):
        mono['not comparable (name or unit)'] += 1
    elif all(a < b for a, b in zip(xs, xs[1:])): mono['strictly up'] += 1
    elif all(a > b for a, b in zip(xs, xs[1:])): mono['strictly down'] += 1
    else: mono['up and down (returns to an old value)'] += 1
print(f'keys with >=2 true rows: {multi}; all true values agree: {agree} ({agree / multi:.3f}); value changes: {change} ({change / multi:.3f})')
print('changing keys by kind', dict(kinds)); print('direction of change over time (true rows sorted by date):', dict(mono))
# majority decidability, leave-one-out, labels unknown at test time: compare a row's value with the other rows' values of the key
out = Counter()
for r in rows:
    if r['label'] == 'unsure': continue
    res = []
    for f in r['facts']:
        others = [v for o, v in K[H.key(f)] if o['idx'] != r['idx']]
        if not others: res.append('none'); continue
        c = Counter(vk(v) for v in others); top, n = c.most_common(1)[0]
        tie = sum(1 for x in c.values() if x == n) > 1
        res.append('tie' if tie and vk(f['value']) != top and c[vk(f['value'])] == n else 'agree' if vk(f['value']) == top else 'disagree')
    pred = 'false' if 'disagree' in res else 'none' if all(x == 'none' for x in res) else 'tie' if 'tie' in res else 'true'
    out[(r['label'], pred)] += 1
for lab in ['false', 'true']:
    n = sum(v for (l, _), v in out.items() if l == lab)
    print(f'{lab} rows ({n}): ' + ', '.join(f'majority says {p}: {out[(lab, p)]} ({out[(lab, p)] / n:.3f})' for p in ['false', 'true', 'tie', 'none']))
# time-aware: nearest-date other row decides
out2 = Counter()
from datetime import date
D = lambda r: date.fromisoformat(r['date']).toordinal()
for r in rows:
    if r['label'] == 'unsure': continue
    res = []
    for f in r['facts']:
        others = sorted([(abs(D(o) - D(r)), o['n'], v) for o, v in K[H.key(f)] if o['idx'] != r['idx'] and o['page'] != r['page']], key=lambda t: t[:2])
        if not others: res.append('none'); continue
        res.append('agree' if vk(others[0][2]) == vk(f['value']) else 'disagree')
    pred = 'false' if 'disagree' in res else 'none' if all(x == 'none' for x in res) else 'true'
    out2[(r['label'], pred)] += 1
for lab in ['false', 'true']:
    n = sum(v for (l, _), v in out2.items() if l == lab)
    print(f'nearest-date other-page row of the key, {lab} rows: ' + ', '.join(f'{p}: {out2[(lab, p)]} ({out2[(lab, p)] / n:.3f})' for p in ['false', 'true', 'none']))

# ---- timeline tests (added): does a per-key dated timeline explain the labels, and how does accuracy grow with density?
import math, random
def rows_of(key, r, pool):  # other-page rows of the key: (days, value, label)
    return [(D(o) - D(r), v, o['label']) for o, v in pool[key] if o['page'] != r['page']]
def oracle(r, pool):  # labels known (leave-page-out): value of the latest TRUE row at or before the date, else the earliest after
    res = []
    for f in r['facts']:
        T = [(d, v) for d, v, l in rows_of(H.key(f), r, pool) if l == 'true']
        if not T: res.append('none'); continue
        prev = [t for t in T if t[0] <= 0]; nxt = [t for t in T if t[0] > 0]
        ref = max(prev, key=lambda t: t[0])[1] if prev else min(nxt, key=lambda t: t[0])[1]
        tol = {vk(ref)} | ({vk(min(nxt, key=lambda t: t[0])[1])} if nxt else set())
        res.append(('agree' if vk(f['value']) == vk(ref) else 'disagree', 'agree' if vk(f['value']) in tol else 'disagree'))
    return res
def summ(name, preds):
    tp = sum(1 for l, p in preds if l == 'false' and p == 'false'); fa = sum(1 for l, p in preds if l == 'true' and p == 'false')
    nf = sum(1 for l, _ in preds if l == 'false'); nt = sum(1 for l, _ in preds if l == 'true')
    acc = sum(1 for l, p in preds if l == p) / len(preds)
    print(f'  {name}: acc {acc:.3f} on {len(preds)} true+false rows; lies caught {tp}/{nf} ({tp / nf:.3f}); true rows wrongly flagged {fa}/{nt} ({fa / nt:.3f})')
    return acc
print('\nORACLE timeline (true values known from the OTHER pages, leave-page-out); predict false when the row disagrees with the latest true value at or before its date')
for j, name in [(0, 'strict (latest at-or-before)'), (1, 'tolerant (latest before OR next after)')]:
    P_ = []
    for r in rows:
        if r['label'] == 'unsure': continue
        o = oracle(r, K)
        P_.append((r['label'], 'false' if any(x != 'none' and x[j] == 'disagree' for x in o) else 'true'))
    summ(name, P_)
print('UNLABELLED time-weighted consistency: other-page rows of the key vote, weight exp(-|days|/tau); false when the share agreeing with the row < 0.5')
def unl(r, pool, tau):
    for f in r['facts']:
        O = rows_of(H.key(f), r, pool)
        if not O: continue
        w = [math.exp(-abs(d) / tau) for d, _, _ in O]; s = sum(wi for wi, (_, v, _) in zip(w, O) if vk(v) == vk(f['value']))
        if s / sum(w) < 0.5: return 'false'
    return 'true'
for tau in [7, 30, 90, 365]:
    summ(f'tau={tau:3d} days, all practice rows', [(r['label'], unl(r, K, tau)) for r in rows if r['label'] != 'unsure'])
print('DENSITY CURVE (tau=30): keep a random fraction of the OTHER rows as voters, 5 seeds; the hidden universe is ~10x practice')
for frac in [0.1, 0.25, 0.5, 1.0]:
    accs = []
    for seed in range(5 if frac < 1 else 1):
        rnd = random.Random(seed); keep = {r['idx'] for r in rows if rnd.random() < frac}
        pool = defaultdict(list)
        for key, L in K.items(): pool[key] = [(o, v) for o, v in L if o['idx'] in keep]
        P_ = [(r['label'], unl(r, {**pool}, 30)) for r in rows if r['label'] != 'unsure']
        accs.append(sum(1 for l, p in P_ if l == p) / len(P_))
    print(f'  voters = {frac:.2f} x practice ({frac * 4.67:.1f} rows/key): acc mean {st.mean(accs):.3f} (seeds {[round(a, 3) for a in accs]})')
nt = sum(r['label'] == 'true' for r in rows); nf = sum(r['label'] == 'false' for r in rows)
print(f'baseline always-true on true+false rows: {nt / (nt + nf):.3f}')
