"""A2 lie signature: compare every false row's gold facts with TRUE values of the same key elsewhere in practice."""
import sys; sys.path.insert(0, '/tmp/veridyct-rev')
import json, math, re
from collections import Counter, defaultdict
from datetime import date
from rev_common import load, H

rows, lex = load()
D = lambda r: date.fromisoformat(r['date']).toordinal()
NUMK = {'quantity', 'money', 'percent', 'duration'}
true_by_key, true_by_attr, true_by_subj, true_vals = defaultdict(list), defaultdict(list), defaultdict(list), []
for r in rows:
    if r['label'] != 'true': continue
    for f in r['facts']:
        t = (r, f); true_by_key[H.key(f)].append(t); true_by_attr[f['attribute']].append(t); true_by_subj[f['subject']].append(t); true_vals.append(t)
EQ = lambda a, b: H.value_equal(a, b)
unitless = lambda v: {k: x for k, x in v.items() if k not in ('value', 'op')}

def dfix(s): return date.fromisoformat((str(s) + '-01-01')[:10] if len(str(s)) == 4 else (str(s) + '-01')[:10] if len(str(s)) == 7 else str(s)).toordinal()
def ver(s): return tuple(int(x) for x in re.findall(r'\d+', str(s)))
def roundness(x):
    x = abs(float(x))
    if x != int(x): return -len(repr(x).split('.')[1])
    x, z = int(x), 0
    while x and x % 10 == 0: x //= 10; z += 1
    return z
def digit_change(a, b):
    sa, sb = repr(a).rstrip('0').rstrip('.') if isinstance(a, float) else str(a), repr(b).rstrip('0').rstrip('.') if isinstance(b, float) else str(b)
    if len(sa) != len(sb): return False
    diff = [i for i in range(len(sa)) if sa[i] != sb[i]]
    return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and sa[diff[0]] == sb[diff[1]] and sa[diff[1]] == sb[diff[0]])

def classify(r, f):
    v = f['value']; k = v['kind']
    T = sorted([t for t in true_by_key[H.key(f)] if t[0]['idx'] != r['idx']], key=lambda t: (abs(D(t[0]) - D(r)), D(t[0])))
    tags = {}
    tags['other_subject_same_attr_true'] = any(EQ(v, g['value']) for o, g in true_by_attr[f['attribute']] if g['subject'] != f['subject'])
    tags['same_subject_other_attr_true'] = any(EQ(v, g['value']) for o, g in true_by_subj[f['subject']] if g['attribute'] != f['attribute'])
    tags['any_true_fact_same_value'] = any(EQ(v, g['value']) for o, g in true_vals if o['idx'] != r['idx'])
    if not T: return 'no_true_counterpart', None, tags, T
    t = T[0][1]['value']
    tags['days_to_nearest_true'] = D(T[0][0]) - D(r)
    if EQ(v, t): return 'equal_to_nearest_true', t, tags, T
    same_key_other = [o for o, g in T if EQ(v, g['value'])]
    if same_key_other:
        tags['same_key_value_dates'] = [D(o) - D(r) for o in same_key_other]
        return ('same_key_value_from_earlier_date' if min(D(o) for o in same_key_other) < D(r) else 'same_key_value_from_later_date'), t, tags, T
    if tags['other_subject_same_attr_true']: return 'swap_other_subject_same_attr', t, tags, T
    if tags['same_subject_other_attr_true']: return 'swap_same_subject_other_attr', t, tags, T
    if k in NUMK:
        if v.get('op') or t.get('op'):
            if v['value'] == t['value']: return 'comparison_op_changed', t, tags, T
        if unitless(v) != unitless(t):
            return ('unit_or_period_change_same_number' if v['value'] == t['value'] else 'unit_or_period_change_and_number'), t, tags, T
        a, b = float(v['value']), float(t['value'])
        if b == 0 or a == 0: return 'numeric_zero_involved', t, tags, T
        q = a / b; tags['ratio'] = q; tags['larger'] = a > b
        if digit_change(v['value'], t['value']): tags['digit_change'] = True
        if roundness(v['value']) > roundness(t['value']) and abs(q - 1) <= 0.15: return 'rounding_of_true', t, tags, T
        if abs(q - 2) < 0.04: return 'ratio_x2', t, tags, T
        if abs(q - 0.5) < 0.01: return 'ratio_x0.5', t, tags, T
        if abs(q - 10) < 0.2 or abs(q - 0.1) < 0.002: return 'ratio_x10_or_x0.1', t, tags, T
        if tags.get('digit_change'): return 'single_digit_change', t, tags, T
        if 0.9 <= q <= 1.1: return 'ratio_within_10pct', t, tags, T
        if 0.5 <= q <= 1.5: return 'ratio_within_50pct', t, tags, T
        return 'ratio_other', t, tags, T
    if k == 'boolean': return 'boolean_flipped', t, tags, T
    if k == 'version':
        tags['larger'] = ver(v['value']) > ver(t['value']); return 'version_changed', t, tags, T
    if k == 'date':
        dd = dfix(v['value']) - dfix(t['value'])
        if len(str(v['value'])) != len(str(t['value'])): tags['date_precision_changed'] = True
        tags['date_shift_days'] = dd; tags['larger'] = dd > 0; return 'date_shifted', t, tags, T
    if k == 'name': return 'name_replaced', t, tags, T
    return 'other', t, tags, T

PRI = ['equal_to_nearest_true', 'no_true_counterpart']
row_cat, fact_cat, details = Counter(), Counter(), []
for r in rows:
    if r['label'] != 'false': continue
    res = [classify(r, f) + (f,) for f in r['facts']]
    fact_cat.update(c for c, *_ in res)
    diff = [x for x in res if x[0] not in PRI]
    if diff: pick = diff[0]
    elif any(x[0] == 'equal_to_nearest_true' for x in res): pick = next(x for x in res if x[0] == 'equal_to_nearest_true')
    else: pick = res[0]
    row_cat[pick[0]] += 1
    details.append(dict(id=r['id'], date=r['date'], text=r['text'], cat=pick[0], fact=pick[4], true=pick[1], tags=pick[2], nfacts=len(r['facts']),
                        all_cats=[x[0] for x in res], n_true_same_key=len(pick[3])))
n = sum(row_cat.values())
print(f'false rows: {n}; facts in false rows: {sum(fact_cat.values())}')
print('ROW-LEVEL categories (first fact that differs from its key\'s true values; else equal; else no counterpart):')
for c, k in row_cat.most_common(): print(f'  {c:40s} {k:4d}  {k / n:.3f}')
print('FACT-LEVEL categories:')
for c, k in fact_cat.most_common(): print(f'  {c:40s} {k:4d}')
# kind breakdown of row categories
kc = Counter((d['fact']['value']['kind'], d['cat']) for d in details)
print('kind x category:'); [print(f'  {a:9s} {b:40s} {k}') for (a, b), k in sorted(kc.items())]
# direction
dirs = Counter(d['tags'].get('larger') for d in details if 'larger' in d['tags'])
print('direction (False value larger than nearest true?):', dict(dirs))
rat = sorted(round(d['tags']['ratio'], 3) for d in details if 'ratio' in d['tags'])
print('numeric ratios false/true (n=%d):' % len(rat), rat)
print('most common ratios:', Counter(rat).most_common(12))
print('date shifts (days):', sorted(d['tags']['date_shift_days'] for d in details if 'date_shift_days' in d['tags']))
print('false value equals SOME true fact value anywhere:', sum(d['tags']['any_true_fact_same_value'] for d in details), 'of', n)
print('  equals a true value of same attr, other subject:', sum(d['tags']['other_subject_same_attr_true'] for d in details))
print('  equals a true value of same subject, other attr:', sum(d['tags']['same_subject_other_attr_true'] for d in details))
# copies
txt = defaultdict(list)
for r in rows: txt[r['text']].append(r)
cop = [r for r in rows if r['label'] == 'false' and len(txt[r['text']]) > 1]
print('false rows whose exact text occurs on another row:', len(cop), [(r['id'], [(o['id'], o['label'], o['date']) for o in txt[r['text']] if o is not r]) for r in cop])
# equal-to-nearest: why false? print them
print('\nEQUAL-to-nearest-true false rows (why false?):')
for d in details:
    if d['cat'] == 'equal_to_nearest_true':
        print(f"  {d['id']} {d['date']} days_to_true={d['tags'].get('days_to_nearest_true')} n_same_key_true={d['n_true_same_key']} | {d['text'][:110]} | {json.dumps(d['fact'])[:140]}")
print('\nSAMPLE per category:')
seen = Counter()
for d in details:
    if seen[d['cat']] < 4 and d['cat'] != 'equal_to_nearest_true':
        seen[d['cat']] += 1
        print(f"  [{d['cat']}] {d['id']} {d['date']} | {d['text'][:100]} | F={json.dumps(d['fact']['value'])} T={json.dumps(d['true'])} tags={ {k: v for k, v in d['tags'].items() if k not in ('any_true_fact_same_value',)} }")
json.dump(details, open('/tmp/veridyct-rev/a2_details.json', 'w'), indent=1, default=str)
