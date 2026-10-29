"""A5c: timeline consistency with unit-normalised values. A row is CONSISTENT with its key when its value equals the
nearest earlier or nearest later reference value, or (numeric) lies between them. Oracle = references are TRUE rows of
other pages (labels known); unlabelled = references are ALL other-page rows. Density curve subsamples the references."""
import sys; sys.path.insert(0, '/tmp/veridyct-rev')
import json, random, statistics as st
from collections import Counter, defaultdict
from datetime import date
from rev_common import load, H, canon

rows, lex = load()
D = lambda r: date.fromisoformat(r['date']).toordinal()
K = defaultdict(list)
for r in rows:
    for f in r['facts']: K[H.key(f)].append((r, f['value']))
def status(r, f, refs):
    """refs: [(days, value)] of the key on other pages. -> equal | between | outside | none"""
    if not refs: return 'none'
    ck, cv = canon(f['value'])
    prev = [t for t in refs if t[0] <= 0]; nxt = [t for t in refs if t[0] > 0]
    near = ([max(prev, key=lambda t: t[0])] if prev else []) + ([min(nxt, key=lambda t: t[0])] if nxt else [])
    cn = [canon(v) for _, v in near]
    if any(c == (ck, cv) for c in cn): return 'equal'
    if len(cn) == 2 and all(c[0] == ck for c in cn) and f['value']['kind'] not in ('boolean', 'name'):
        lo, hi = sorted([cn[0][1], cn[1][1]])
        if lo < cv < hi: return 'between'
    return 'outside'
def evaluate(ref_filter, keep=None, rule=('outside',)):
    out = Counter()
    for r in rows:
        if r['label'] == 'unsure': continue
        S = []
        for f in r['facts']:
            refs = [(D(o) - D(r), v) for o, v in K[H.key(f)] if o['page'] != r['page'] and ref_filter(o) and (keep is None or o['idx'] in keep)]
            S.append(status(r, f, refs))
        pred = 'false' if any(s in rule for s in S) else 'true'
        out[(r['label'], pred)] += 1
        out[('status', r['label'], 'outside' if 'outside' in S else 'between' if 'between' in S else 'equal' if 'equal' in S else 'none')] += 1
    nt, nf = out[('true', 'true')] + out[('true', 'false')], out[('false', 'true')] + out[('false', 'false')]
    return out, (out[('true', 'true')] + out[('false', 'false')]) / (nt + nf), out[('false', 'false')] / nf, out[('true', 'false')] / nt
for name, flt in [('ORACLE (refs = true rows of other pages)', lambda o: o['label'] == 'true'), ('UNLABELLED (refs = all other-page rows)', lambda o: True)]:
    out, acc, catch, fa = evaluate(flt)
    print(f'{name}: acc {acc:.3f}; lies caught {catch:.3f}; true rows flagged {fa:.3f}')
    for lab in ['true', 'false']:
        n = sum(v for k, v in out.items() if k[0] == 'status' and k[1] == lab)
        print(f'   {lab} rows ({n}): ' + ', '.join(f'{s} {out[("status", lab, s)]} ({out[("status", lab, s)] / n:.3f})' for s in ['equal', 'between', 'outside', 'none']))
print('DENSITY CURVE, unlabelled refs, random fraction of the other rows kept as references (5 seeds):')
for frac in [0.1, 0.25, 0.5, 0.75, 1.0]:
    R = []
    for seed in range(5 if frac < 1 else 1):
        rnd = random.Random(seed); keep = {r['idx'] for r in rows if rnd.random() < frac}
        _, acc, catch, fa = evaluate(lambda o: True, keep); R.append((acc, catch, fa))
    print(f'  refs {frac:.2f} x practice (~{frac * 4.67:.1f} rows/key): acc {st.mean(a for a, _, _ in R):.3f}, lies caught {st.mean(c for _, c, _ in R):.3f}, true flagged {st.mean(f for _, _, f in R):.3f}')
nt = sum(r['label'] == 'true' for r in rows); nf = sum(r['label'] == 'false' for r in rows)
print(f'always-true baseline on the 1,858 true+false rows: {nt / (nt + nf):.3f}')

# ---- (added) unsure rows under the oracle timeline; agreement/change with unit-normalised values; value re-use vs density
st_u = Counter()
for r in rows:
    if r['label'] != 'unsure': continue
    S = [status(r, f, [(D(o) - D(r), v) for o, v in K[H.key(f)] if o['page'] != r['page'] and o['label'] == 'true']) for f in r['facts']]
    st_u['outside' if 'outside' in S else 'between' if 'between' in S else 'equal' if 'equal' in S else 'none'] += 1
print('unsure rows (39) under the ORACLE timeline:', dict(st_u))
multi = agree = 0; dist, nrow = [], []
for key, L in K.items():
    T = [canon(v) for o, v in L if o['label'] == 'true']
    if len(T) < 2: continue
    multi += 1; agree += len(set(map(repr, T))) == 1; dist.append(len(set(map(repr, T)))); nrow.append(len(T))
print(f'unit-normalised: keys with >=2 true rows {multi}; all agree {agree} ({agree / multi:.3f}); change {multi - agree} ({(multi - agree) / multi:.3f})')
print(f'  distinct true values per such key: mean {st.mean(dist):.2f}, median {st.median(dist)}; true rows per key mean {st.mean(nrow):.2f}; rows per distinct value {sum(nrow) / sum(dist):.2f}')
tv = Counter((H.key(f), repr(canon(f['value']))) for r in rows if r['label'] == 'true' for f in r['facts'])
pages_of = defaultdict(set)
for r in rows:
    if r['label'] == 'true':
        for f in r['facts']: pages_of[(H.key(f), repr(canon(f['value'])))].add(r['page'])
n1 = sum(1 for k, c in tv.items() if c == 1); N = sum(tv.values())
print(f'true facts {N}; (key, value) pairs {len(tv)}; pairs stated once {n1}; Good-Turing P(a new true fact states an unseen value of its key) = {n1 / N:.3f}')
print('re-use vs density: share of TRUE facts whose exact (key, value) is stated on another page, references subsampled:')
for frac in [0.1, 0.25, 0.5, 0.75, 1.0]:
    R = []
    for seed in range(5 if frac < 1 else 1):
        rnd = random.Random(seed); keep = {r['idx'] for r in rows if rnd.random() < frac}
        seen = Counter(); tot = 0
        idx_pages = defaultdict(set)
        for r in rows:
            if r['idx'] in keep:
                for f in r['facts']: idx_pages[(H.key(f), repr(canon(f['value'])))].add(r['page'])
        for r in rows:
            if r['label'] != 'true': continue
            for f in r['facts']:
                tot += 1; seen['y'] += bool(idx_pages[(H.key(f), repr(canon(f['value'])))] - {r['page']})
        R.append(seen['y'] / tot)
    print(f'  refs {frac:.2f} x practice: {st.mean(R):.3f}')

# ---- (added) do lies support each other? false facts whose (key, value) is not a true value of the key, repeated on other pages
truekv = {(H.key(f), repr(canon(f['value']))) for r in rows if r['label'] == 'true' for f in r['facts']}
fk = defaultdict(set)
for r in rows:
    if r['label'] == 'false':
        for f in r['facts']:
            kv = (H.key(f), repr(canon(f['value'])))
            if kv not in truekv: fk[kv].add(r['page'])
print(f'false (key, value) pairs never true for the key: {len(fk)}; stated on >= 2 pages: {sum(1 for p in fk.values() if len(p) > 1)}')
