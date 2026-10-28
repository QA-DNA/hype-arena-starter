"""A3b: does a first-person / boastful voice mark unsure or false rows? Row-level and page-level label mix."""
import sys; sys.path.insert(0, '/tmp/veridyct-rev')
import re
from collections import Counter, defaultdict
from rev_common import load

rows, lex = load()
FP = re.compile(r"\b(I|I'm|I've|me|my|myself)\b")
SPEAKER = re.compile(r"^[A-Z][a-z]+( [A-Z][a-z]+)?: ")
P = defaultdict(list)
for r in rows: P[r['page']].append(r)
def mix(sel):
    c = Counter(r['label'] for r in sel); n = len(sel)
    return f"n={n} true {c['true'] / n:.3f} false {c['false'] / n:.3f} unsure {c['unsure'] / n:.3f}" if n else 'n=0'
print('all rows            ', mix(rows))
print('first person (I/me/my)', mix([r for r in rows if FP.search(r['text'])]))
print('speaker tag "Name: "  ', mix([r for r in rows if SPEAKER.match(r['text'])]))
fp_pages = {p for p, L in P.items() if any(FP.search(r['text']) for r in L)}
print(f'rows on pages with >=1 first-person row ({len(fp_pages)} pages)', mix([r for r in rows if r['page'] in fp_pages]))
print('rows on other pages', mix([r for r in rows if r['page'] not in fp_pages]))
U = [r for r in rows if r['label'] == 'unsure']
print('unsure rows on a first-person page:', sum(r['page'] in fp_pages for r in U), 'of', len(U))
# page label purity
bad = [(p, Counter(r['label'] for r in L)) for p, L in P.items()]
print('pages where >=50% of rows are not true (size >= 3):', [(P[p][0]['id'], P[p][-1]['id'], dict(c)) for p, c in bad if len(P[p]) >= 3 and c['true'] / len(P[p]) <= 0.5])
# label mix per block of 100 ids: did the generator lay pages out by source?
print('id block: n, false share, unsure share, first-person rows')
for b in range(0, 1900, 100):
    L = [r for r in rows if b < r['n'] <= b + 100]
    if L: print(f"  p-{b + 1:<4d}..{b + 100:<4d} n={len(L):3d} false {sum(r['label'] == 'false' for r in L) / len(L):.2f} unsure {sum(r['label'] == 'unsure' for r in L) / len(L):.2f} first-person {sum(bool(FP.search(r['text'])) for r in L)}")
