"""Hypotheses from public notes (a)-(e): multiples, stale values, never-changing keys, page genre, unsure tails.
Reference value of a key at a date = latest TRUE value at or before the date on another page, else the earliest after (oracle,
labels known); values unit-normalised (rev_common.canon)."""
import sys; sys.path.insert(0, '/tmp/veridyct-rev')
import re
from collections import Counter, defaultdict
from datetime import date
from rev_common import load, H, V, canon

rows, lex = load()
D = lambda r: date.fromisoformat(r['date']).toordinal()
NUMK = {'quantity', 'money', 'percent', 'duration'}
K = defaultdict(list)
for r in rows:
    for f in r['facts']: K[H.key(f)].append((r, f['value']))
TRUE_REFS = lambda r, f: [(D(o), canon(v)) for o, v in K[H.key(f)] if o['label'] == 'true' and o['page'] != r['page']]
def ref_at(r, f):
    T = TRUE_REFS(r, f)
    if not T: return None
    prev = [t for t in T if t[0] <= D(r)]
    return max(prev, key=lambda t: t[0])[1] if prev else min(T, key=lambda t: t[0])[1]
def pr(name, fires, target):
    """fires, target: sets of row idx. -> precision/recall line"""
    tp = len(fires & target)
    return f'{name}: fires {len(fires)}, hits {tp}; precision {tp / len(fires) if fires else 0:.3f}, recall {tp / len(target):.3f}'
FALSE = {r['idx'] for r in rows if r['label'] == 'false'}; UNS = {r['idx'] for r in rows if r['label'] == 'unsure'}
TRUE = {r['idx'] for r in rows if r['label'] == 'true'}
OUT = []
def say(*a):
    s = ' '.join(str(x) for x in a); print(s); OUT.append(s)

# (a) exact multiples
B = [0.1, 0.2, 0.4, 0.5, 2, 2.5, 5, 10]
def decimals(x):
    s = repr(float(x)); return 0 if s.endswith('.0') else len(s.split('.')[1])
def multiple(fv, tv):
    if tv == 0 or fv == 0: return None
    for b in B:
        e = tv * b
        if abs(fv - e) <= max(0.01 * abs(e), 0.5 * 10 ** -decimals(fv)): return b
    return None
say('(a) EXACT MULTIPLES x0.1 x0.2 x0.4 x0.5 x2 x2.5 x5 x10 of the reference true value at the row date (1% or display rounding)')
num_false, hit_false, bucket = set(), set(), Counter()
fires = set()
for r in rows:
    for f in r['facts']:
        if f['value']['kind'] not in NUMK: continue
        ref = ref_at(r, f)
        if ref is None: continue
        ck, cv = canon(f['value'])
        if ref[0] != ck or ref[1] == cv: continue
        b = multiple(cv, ref[1])
        if r['label'] == 'false': num_false.add(r['idx'])
        if b:
            fires.add(r['idx'])
            if r['label'] == 'false': hit_false.add(r['idx']); bucket[b] += 1
say(f'  numeric false rows whose value differs from the reference: {len(num_false)}; in a multiple bucket: {len(hit_false)} ({len(hit_false) / len(num_false):.3f}); buckets {dict(sorted(bucket.items()))}')
tm = set(); pairs = 0
for r in rows:
    if r['label'] != 'true': continue
    for f in r['facts']:
        if f['value']['kind'] not in NUMK: continue
        ck, cv = canon(f['value'])
        others = [c for o, v in K[H.key(f)] if o['label'] == 'true' and o['idx'] != r['idx'] for c in [canon(v)] if c[0] == ck and c[1] != cv]
        if any(multiple(cv, ov) for _, ov in others): tm.add(r['idx'])
ntn = sum(1 for r in rows if r['label'] == 'true' and any(f['value']['kind'] in NUMK for f in r['facts']))
say(f'  TRUE numeric rows whose value is such a multiple of ANOTHER true value of the same key: {len(tm)} of {ntn} ({len(tm) / ntn:.3f})')
say('  ' + pr('rule "value is a listed multiple of the reference true value" -> false', fires, FALSE))

# (b) stale values
say('(b) STALE: the row repeats an OLD true value of the key after a different true value appeared (change date <= row date)')
def stale(r, f):
    T = sorted(TRUE_REFS(r, f)); cv = canon(f['value'])
    olds = [d for d, c in T if c == cv and d < D(r)]
    if not olds: return False
    cur = [c for d, c in T if d <= D(r)]
    latest = max((t for t in T if t[0] <= D(r)), key=lambda t: t[0])[1]
    changed_after_old = any(c != cv and min(olds) < d <= D(r) for d, c in T)
    return latest != cv and changed_after_old
S = {r['idx'] for r in rows for f in r['facts'] if stale(r, f)}
say(f'  false rows stale: {len(S & FALSE)} of {len(FALSE)} ({len(S & FALSE) / len(FALSE):.3f}); true rows stale: {len(S & TRUE)} of {len(TRUE)} ({len(S & TRUE) / len(TRUE):.3f}); unsure stale: {len(S & UNS)}')
say('  ' + pr('rule "stale old value" -> false', S, FALSE))
def premature(r, f):
    T = sorted(TRUE_REFS(r, f)); cv = canon(f['value'])
    prev = [t for t in T if t[0] <= D(r)]
    return bool(prev) and max(prev, key=lambda t: t[0])[1] != cv and any(c == cv and d > D(r) for d, c in T) and not any(c == cv and d <= D(r) for d, c in T)
Pm = {r['idx'] for r in rows for f in r['facts'] if premature(r, f)}
say(f'  (companion) premature, a value first true LATER than the row: false {len(Pm & FALSE)}, true {len(Pm & TRUE)}, unsure {len(Pm & UNS)}')
say('  ' + pr('rule "premature future value" -> false', Pm, FALSE))

# (c) keys that never changed
say('(c) KEYS WHOSE TRUE VALUE NEVER CHANGED (>= 2 true rows, one unit-normalised value)')
cls = {}
for k, L in K.items():
    T = {repr(canon(v)) for o, v in L if o['label'] == 'true'}; n = sum(1 for o, v in L if o['label'] == 'true')
    cls[k] = 'no true row' if n == 0 else 'one true row' if n == 1 else 'stable' if len(T) == 1 else 'changing'
rc = defaultdict(Counter)
for r in rows:
    c = {cls[H.key(f)] for f in r['facts']}
    g = 'changing' if 'changing' in c else 'stable' if c == {'stable'} else 'one true row' if 'one true row' in c and 'stable' not in c else 'mixed stable/one' if 'stable' in c else 'no true row'
    rc[g][r['label']] += 1
for g, c in rc.items():
    n = sum(c.values()); say(f'  rows touching {g:18s}: {n:4d} rows, false {c["false"]:3d} ({c["false"] / n:.3f}), unsure {c["unsure"]} ({c["unsure"] / n:.3f})')
say(f'  keys: ' + str(dict(Counter(cls.values()))))
stable_rows = {r['idx'] for r in rows if {cls[H.key(f)] for f in r['facts']} == {'stable'}}
say('  ' + pr('rule "all facts on never-changing keys" -> TRUE', stable_rows, TRUE))

# (d) page genre
say('(d) PAGE GENRE: first person / social-post style')
F = dict(fp_singular=re.compile(r"\b(I|I'm|I've|me|my|myself)\b"), fp_plural=re.compile(r"\b(we|We|our|Our|us|ours)\b"),
         exclamation=re.compile(r'!'), speaker_tag=re.compile(r'^[A-Z][a-z]+(?: [A-Z][a-z]+)?: '),
         hype=re.compile(r"\b(best|more than any|nobody|no one|record|ever|greatest|incredible|amazing|unmatched|world's|number one|"
                         r"personal best|not even|vertical|impossible|regrets?|every one|all humans|greatness|perfect|the rest are)\b", re.I))
P = defaultdict(list)
for r in rows: P[r['page']].append(r)
def mix(sel):
    c = Counter(r['label'] for r in sel); n = len(sel)
    return f"n={n:4d} false {c['false'] / n:.3f} unsure {c['unsure'] / n:.3f}" if n else 'n=0'
for name, rx in list(F.items()) + [('social (fp_singular|exclamation|hype)', None)]:
    hit = (lambda r: bool(F['fp_singular'].search(r['text']) or F['exclamation'].search(r['text']) or F['hype'].search(r['text']))) if rx is None else (lambda r, rx=rx: bool(rx.search(r['text'])))
    rows_hit = [r for r in rows if hit(r)]; pages_hit = {p for p, L in P.items() if any(hit(r) for r in L)}
    on = [r for r in rows if r['page'] in pages_hit]; off = [r for r in rows if r['page'] not in pages_hit]
    say(f'  {name:38s} rows with it: {mix(rows_hit)} | rows on its {len(pages_hit):3d} pages: {mix(on)} | rest: {mix(off)}')
    if rx is None:
        say('  ' + pr('rule "row is on a social-genre page" -> false', {r["idx"] for r in on}, FALSE))
        say('  ' + pr('rule "row itself has the social style" -> false', {r["idx"] for r in rows_hit}, FALSE))

# (e) unsure rows
say('(e) UNSURE: single rules over all rows (precision, recall on the 39 unsure)')
VALS = {r['idx']: V.extract_values(r['text'], lex) for r in rows}
def tail_words(r):  # words after the last non-boolean value or subject mention
    ends = [c['end'] for c in VALS[r['idx']] if c['kind'] != 'boolean' and 'alt' not in c['flags']]
    return len(r['text'][max(ends):].split()) if ends else 0
JOKE = re.compile(r"(,| and| which| while| though| but)\s.*\b(I|me|my|we|our|nobody|no one|not one|every one|all humans|poetry|tired|personal best|"
                  r"vertical|impossible|coffee|for you|the rest|regrets?|greatness|friends|asked|told)\b")
UNDERCUT = re.compile(r"\b(not live|in the beta|beta|preview|pilot|starts today|questions go to|I have been told|told me|reportedly|rumou?r|may|might|"
                      r"if|would|could|planned|expected)\b", re.I)
def date_conflict(r):
    for c in VALS[r['idx']]:
        if c['kind'] == 'date' and len(str(c['value']['value'])) == 10:
            d = date.fromisoformat(c['value']['value']).toordinal()
            if (re.search(r'\btoday\b', r['text'], re.I) and d != D(r)) or d > D(r): return True
    return False
gold_named = lambda r: bool({f['subject'] for f in r['facts']} & {n for _, _, n in V.find_entities(r['text'], lex)})
R = dict(joke_tail=lambda r: bool(JOKE.search(r['text'])), undercutting_clause=lambda r: bool(UNDERCUT.search(r['text'])),
         long_tail_after_value=lambda r: tail_words(r) >= 5, missing_subject=lambda r: not gold_named(r),
         date_in_text_contradicts_row_date=date_conflict,
         no_true_value_at_or_before_date=lambda r: any(not [t for t in TRUE_REFS(r, f) if t[0] <= D(r)] for f in r['facts']))
for name, fn in R.items():
    fires_u = {r['idx'] for r in rows if fn(r)}
    say('  ' + pr(f'{name:34s} -> unsure', fires_u, UNS) + f'; false rows hit {len(fires_u & FALSE)}, true rows hit {len(fires_u & TRUE)}')
open('/tmp/veridyct-rev/hyp_out.txt', 'w').write('\n'.join(OUT) + '\n')
