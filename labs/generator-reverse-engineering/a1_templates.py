"""A1 template inventory: placeholder templates (rev_common.template), counts, Good-Turing, sharing, loose variant."""
import sys; sys.path.insert(0, "/tmp/veridyct-rev")
import json, re, statistics as st
from collections import Counter, defaultdict
from rev_common import load, template, loose

rows, lex = load()
for r in rows:
    r['tpl'] = template(r, lex); r['loose'] = loose(r['tpl'])
    r['slots'] = ' '.join(re.findall(r'<[A-Z]+>', r['tpl']))
N = len(rows)
res = {}

def inventory(field):
    c = Counter(r[field] for r in rows)
    n1 = sum(1 for v in c.values() if v == 1)
    by_page = defaultdict(set)
    for r in rows: by_page[r[field]].add(r['page'])
    seen_elsewhere = sum(1 for r in rows if len(by_page[r[field]] - {r['page']}) > 0)
    sf = [r for r in rows if len(r['facts']) == 1]
    attrs_of = defaultdict(set); per_attr = defaultdict(Counter)
    for r in sf:
        a = r['facts'][0]['attribute']; attrs_of[r[field]].add(a); per_attr[a][r[field]] += 1
    shared = [t for t, A in attrs_of.items() if len(A) > 1]
    rows_shared = sum(1 for r in sf if r[field] in set(shared))
    tpa = [len(c2) for c2 in per_attr.values()]
    rpa = [sum(c2.values()) for c2 in per_attr.values()]
    all_unique = sum(1 for c2 in per_attr.values() if len(c2) == sum(c2.values()))
    return dict(rows=N, distinct=len(c), singletons=n1, rows_in_singletons=n1, good_turing_p_unseen=round(n1 / N, 4),
                rows_in_templates_ge2=N - n1, leave_page_out_hit=round(seen_elsewhere / N, 4),
                sf_rows=len(sf), sf_templates=len(attrs_of), templates_multi_attr=len(shared), sf_rows_in_multi_attr=rows_shared,
                attrs=len(per_attr), templates_per_attr_median=st.median(tpa), templates_per_attr_mean=round(st.mean(tpa), 2),
                rows_per_attr_median=st.median(rpa), attrs_all_rows_unique_template=all_unique,
                distinct_ratio=round(len(c) / N, 4)), c, attrs_of

out = {}
for f in ['text', 'tpl', 'loose', 'slots']:
    m, c, attrs_of = inventory(f)
    out[f] = m
    print(f'== {f}:', json.dumps(m))
    if f in ('tpl', 'loose', 'slots'):
        print(f'   top 30 {f}:')
        for t, k in c.most_common(30):
            print(f'   {k:4d}  {t}   attrs={sorted(attrs_of.get(t, []))[:6]}')
# templates.txt: every placeholder template seen >= 2 times, then the top 30 loose and slot signatures
c = Counter(r['tpl'] for r in rows); cl = Counter(r['loose'] for r in rows); cs = Counter(r['slots'] for r in rows)
with open('/tmp/veridyct-rev/templates.txt', 'w') as fh:
    fh.write(f'# placeholder templates (rev_common.template), {len(c)} distinct over {N} rows; listed: count >= 2\n')
    for t, k in c.most_common():
        if k >= 2: fh.write(f'{k}\t{t}\n')
    fh.write(f'\n# loose templates (lower, digits->0, no punctuation), {len(cl)} distinct; top 30\n')
    for t, k in cl.most_common(30): fh.write(f'{k}\t{t}\n')
    fh.write(f'\n# slot signatures (placeholder sequence only), {len(cs)} distinct; all\n')
    for t, k in cs.most_common(): fh.write(f'{k}\t{t}\n')
# exact duplicate texts: which labels
dup = Counter(r['text'] for r in rows)
print('exact duplicate texts:', sum(1 for v in dup.values() if v > 1), 'texts,', sum(v for v in dup.values() if v > 1), 'rows')
for t, k in dup.most_common(10):
    if k > 1: print('  ', k, t, [ (r['id'], r['label']) for r in rows if r['text'] == t])
json.dump(out, open('/tmp/veridyct-rev/a1.json', 'w'), indent=1)
