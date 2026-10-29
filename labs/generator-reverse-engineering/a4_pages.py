"""A4 page structure: sizes, false/unsure clustering, positions, subjects per page, anaphora, connectors, ids, dates."""
import sys; sys.path.insert(0, '/tmp/veridyct-rev')
import re, statistics as st
from collections import Counter, defaultdict
from rev_common import load, V

rows, lex = load()
P = defaultdict(list)
for r in rows: P[r['page']].append(r)
sizes = [len(p) for p in P.values()]
print('pages', len(P), 'size min/median/mean/max', min(sizes), st.median(sizes), round(st.mean(sizes), 2), max(sizes))
print('size histogram', sorted(Counter(sizes).items()))
def gini(x):
    x = sorted(x); n = len(x); s = sum(x)
    return sum((2 * i - n + 1) * v for i, v in enumerate(x)) / (n * s) if s else 0
for lab in ['false', 'unsure']:
    c = [sum(r['label'] == lab for r in p) for p in P.values()]
    top = sorted(c, reverse=True)[:round(len(c) * 0.1)]
    print(f'{lab} per page histogram', sorted(Counter(c).items()), f'gini {gini(c):.3f}', f'share in top 10% pages ({len(top)}): {sum(top) / sum(c):.3f}',
          f'pages with >=1: {sum(1 for v in c if v)}')
    # null: shuffle labels across rows, same page sizes
    import random; random.seed(0); labs = [r['label'] for r in rows]; g = []
    for _ in range(200):
        random.shuffle(labs); it = iter(labs); cc = [sum(next(it) == lab for _ in p) for p in P.values()]; g.append(gini(cc))
    print(f'   gini under random labels: mean {st.mean(g):.3f}, max of 200 {max(g):.3f}')
for lab in ['true', 'false', 'unsure']:
    pos = Counter()
    for p in P.values():
        for i, r in enumerate(p):
            if r['label'] == lab and len(p) > 1: pos['first' if i == 0 else 'last' if i == len(p) - 1 else 'middle'] += 1
    n = sum(pos.values()); print(f'position of {lab} rows (pages with >1 row):', {k: f'{v} ({v / n:.3f})' for k, v in pos.items()})
subj = [len({f['subject'] for r in p for f in r['facts']}) for p in P.values()]
print('distinct gold subjects per page: median', st.median(subj), 'histogram', sorted(Counter(subj).items()))
dom = [max(Counter(f['subject'] for r in p for f in r['facts']).values()) / sum(len(r['facts']) for r in p) for p in P.values()]
print('share of a page\'s facts about its most frequent subject: median', round(st.median(dom), 3), 'pages where it is 1.0:', sum(d == 1 for d in dom))
# subject-less rows: is the gold subject named earlier in the page?
less = earlier = earlier_any = 0
for p in P.values():
    named = set()
    for r in p:
        ments = {n for _, _, n in V.find_entities(r['text'], lex)}
        gs = {f['subject'] for f in r['facts']}
        if not (gs & ments):
            less += 1; earlier += bool(gs <= named); earlier_any += bool(gs & named)
        named |= ments
print(f'rows not naming their gold subject: {less}; all gold subjects named earlier on the same page: {earlier} ({earlier / less:.3f}); at least one: {earlier_any} ({earlier_any / less:.3f})')
CONN = re.compile(r"^(It also|Also|Meanwhile|The same|And |It |Its |He |She |They |This |That |There |Plus|On top|Then|Still|But )", re.I)
first = [p[0] for p in P.values()]; rest = [r for p in P.values() for r in p[1:]]
print(f'connector/pronoun opener: page-first rows {sum(bool(CONN.match(r["text"])) for r in first) / len(first):.3f}, later rows {sum(bool(CONN.match(r["text"])) for r in rest) / len(rest):.3f}')
ns = sorted(r['n'] for r in rows)
print('ids: format', Counter(re.sub(r'\d+', 'N', r['id']) for r in rows), 'min', ns[0], 'max', ns[-1], 'count', len(ns), 'gaps', ns[-1] - ns[0] + 1 - len(ns))
dec = sum(1 for a, b in zip(rows, rows[1:]) if b['date'] < a['date']); same = sum(1 for a, b in zip(rows, rows[1:]) if b['date'] == a['date'])
print(f'date in id order: decreases {dec}, increases {len(rows) - 1 - dec - same}, same {same}; page boundaries {len(P) - 1}')
pd = [p[0]['date'] for p in sorted(P.values(), key=lambda p: p[0]['n'])]
print('page dates: distinct', len(set(pd)), 'of', len(pd), '; page-to-page date decreases', sum(1 for a, b in zip(pd, pd[1:]) if b < a), 'range', min(pd), max(pd))
# (added) the subject-less rows whose subject is not named earlier: named later on the page, or nowhere on it?
later = nowhere = 0; ex = []
for p in P.values():
    M = [{n for _, _, n in V.find_entities(r['text'], lex)} for r in p]
    for i, r in enumerate(p):
        gs = {f['subject'] for f in r['facts']}
        if gs & M[i] or gs <= set().union(*M[:i]): continue
        if gs & set().union(*M[i + 1:]): later += 1
        else: nowhere += 1; ex.append(r['text'][:70] + ' -> ' + '/'.join(sorted(gs)))
print(f'subject not named earlier: subject named LATER on the page {later}, named NOWHERE on the page {nowhere}; examples: {ex[:6]}')
