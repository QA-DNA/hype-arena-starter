"""Shared pieces for worker C: row segmentation, interval prefix, lexicon, value picking, joint decode.
A row is  [From <date> through <date>, ] piece (SEP piece)* [SEP aside...] [.]  with SEP in '; ', ', and ', '. '
(measured on the training material: gaps between gold assertion spans are exactly these three strings, asides only trail)."""
import json, re, datetime, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import values as V

HERE = os.path.dirname(os.path.abspath(__file__))
_L = json.load(open(os.path.join(HERE, 'lexicon.json'), encoding='utf-8'))
LEX = dict(subjects={s['name']: dict(aliases=s['aliases'], attributes=s['attributes']) for s in _L['subjects']}, events=_L['events'])
SUBJECTS = list(LEX['subjects']) + [e for e in LEX['events'] if e not in LEX['subjects']]
ATTRS_OF = {s: set(d['attributes']) for s, d in LEX['subjects'].items()}

# ponytail: no single-capital 'initial' rule: training spans only ever hold 'Inc. ', and 'Series A. Bertram' must split
_ABBR = re.compile(r'(?:^|[\s(])(?:Inc|Ltd|Co|Corp|Dr|Mr|Mrs|Ms|Prof|St|vs|approx|e\.g|i\.e)$')
_SEP = re.compile(r'; |, and |\. ')
_PREFIX = re.compile(r'^\s*From (?P<a>.{4,40}?\d{4}) (?:through|to|until) (?P<b>.{4,40}?\d{4}),\s*')
PRON = re.compile(r"\b(?:it|its|it's|he|his|him|she|her|they|their|them)\b", re.I)


def _date(s):
    ds = [c['value']['value'] for c in V.extract_values(s, LEX) if c['kind'] == 'date' and len(c['value']['value']) == 10]
    return ds[0] if ds else None


def segment(text):
    """-> (interval or None, [(start, end)] pieces in char offsets of text)."""
    interval, s0 = None, 0
    m = _PREFIX.match(text)
    if m:
        a, b = _date(m.group('a')), _date(m.group('b'))
        if a and b:
            end = datetime.date.fromisoformat(b) + datetime.timedelta(days=1)
            interval, s0 = [a, end.isoformat()], m.end()
    e0 = len(text.rstrip())
    while e0 > s0 and text[e0 - 1] in '.!? ':
        e0 -= 1
    pieces, k = [], s0
    for mt in _SEP.finditer(text, s0, e0):
        if mt.group(0) == '. ' and _ABBR.search(text[s0:mt.start()]):
            continue
        if mt.start() > k:
            pieces.append((k, mt.start()))
        k = mt.end()
    if e0 > k:
        pieces.append((k, e0))
    return interval, pieces


def norm(t):
    return re.sub(r'\d', '0', t.lower().replace('’', "'"))


def mentions(t):
    return list(dict.fromkeys(c for _, _, c in V.find_entities(t, LEX)))


def prefix_words(t, start, n=3):
    return ' '.join(re.findall(r"[a-z']+", t[:start].lower())[-n:])


def num_eq(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))
    return a == b


def val_eq(g, p):
    """Typed-value equality: same keys, numbers compared with a relative 1e-6 tolerance (gold carries float noise)."""
    if g is None or p is None or set(g) != set(p):
        return False
    return all(num_eq(g[k], p[k]) for k in g)


_VER = re.compile(r'(?<![\w.])\d+(?:\.\d+)+(?![\d.]\d)')
_PCT = re.compile(r'(?<![\w.])(-?\d+(?:\.\d+)?)\s?%')


def candidates(t, subject, kind):
    """Grammar candidates of one kind in a piece, minus readings inside names, plus two fallbacks the grammar lacks."""
    cs = [c for c in V.extract_values(t, LEX, exclude=(subject,)) if c['kind'] == kind and 'in_name' not in c['flags']]
    if kind == 'name':
        al = {subject.lower()} | {a.lower() for a in LEX['subjects'].get(subject, {}).get('aliases', [])}
        cs = [c for c in cs if c['value']['value'].lower() not in al and c['value']['value'] != 'I']
    if kind == 'version' and not cs:
        cs = [dict(kind='version', value=dict(kind='version', value=m.group(0)), start=m.start(), end=m.end(), flags=[]) for m in _VER.finditer(t)]
    if kind == 'percent':
        for m in _PCT.finditer(t):  # negative percentages: the grammar reads '-26.62%' as nothing
            if m.group(1).startswith('-'):
                v = float(m.group(1)); v = int(v) if v == int(v) and '.' not in m.group(1) else v
                cs = [c for c in cs if not (c['start'] <= m.start(1) + 1 < c['end'])]
                cs.append(dict(kind='percent', value=dict(kind='percent', value=v), start=m.start(1), end=m.end(), flags=[]))
    return sorted(cs, key=lambda c: ('alt' in c['flags'], c['start']))


def feats(art, ps):
    """ps: dicts with t (raw piece), n (norm), ment (bool), pos (index in row)."""
    import numpy as np
    from scipy import sparse
    n = [p['n'] for p in ps]
    ex = sparse.csr_matrix(np.array([[p['ment'], bool(PRON.search(p['t'])), p['pos'] > 0, p['t'][:1].islower()] for p in ps], float).reshape(len(ps), 4))
    return sparse.hstack([art['vw'].transform(n), art['vc'].transform(n), ex]).tocsr()


def toks(t):
    return [w for w in re.findall(r"[a-z]+", t.lower()) if w not in V.STOP and len(w) > 1]


def coverage(t, vocab):
    """Share of a piece's content words seen in training assertion pieces (asides never feed the vocabulary)."""
    ts = toks(t)
    return sum(w in vocab for w in ts) / len(ts) if ts else 1.0


STRONG = re.compile(r"\b(?:It|Its|They|Their|He|His|She|Her)\b|^(?:it|its|they|their|he|his|she|her)\b")
TYPED = {'money', 'percent', 'date', 'duration', 'version', 'quantity'}


def typed_kinds(t):
    return {c['kind'] for c in V.extract_values(t, LEX) if 'in_name' not in c['flags']} & TYPED


def keep_piece(t, vocab):
    """A non-first piece without a lexicon mention is an assertion only if it refers back by pronoun: a strong reference
    (capitalised or piece-initial pronoun, the generator's substitution) with some attribute words or a typed value, or any
    pronoun with mostly known attribute words. Measured: no training aside names a subject; the only pronoun asides score <= 0.25."""
    cov = coverage(t, vocab)
    if STRONG.search(t) and (cov >= 0.25 or typed_kinds(t)):
        return True
    return bool(PRON.search(t)) and cov >= 0.5
