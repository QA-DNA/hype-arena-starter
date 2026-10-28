"""POST-HOC v2 of extract.py: three dev-derived fixes written AFTER the v1 final run (not a clean held-out test); writes B/forms-v2/.
Worker B form extractor: universe.csv (public only) -> forms/B/<world>.jsonl.
Trained only on data/practice.csv + lexicon. Optional input signal: the world's Rust assertions.csv (paired subject/attribute).
Pipeline per row: interval prefix -> clauses (sentence / ';' / ', and' / ' and <subject>') -> aside filter -> candidate subjects
(mentions, within-row pronouns, previous row) -> joint (subject, attribute) score = practice TF-IDF+LinearSVC + attribute-word
overlap + value-kind compatibility (+ Rust pair bonus) -> typed value from values.py of the attribute's practice kind.
Usage: python -I extract.py --world dev [--rust]"""
import argparse, csv, json, os, re, sys, time
from collections import Counter, defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
import values as V
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import make_union
from sklearn.svm import LinearSVC

DATA = '/Users/mogaeduard/Downloads/evaluation-data'
REPO = '/Users/mogaeduard/VERIDYCT'
WORLDS = {'dev': 'realistic-v1/development-20000', 'cal': 'realistic-v1/calibration-20000', 'sealed': 'realistic-v1/sealed-20000',
          'diag': 'realistic-v1/diagnostic-6000', 'pilot': 'realistic-v1/pilot-500', 'prac': 'realistic-v1/practice-1897',
          'extdev': 'realistic-v1/external-development', 'extcal': 'realistic-v1/external-calibration',
          'extsealed': 'realistic-v1/external-sealed', 'synth': 'realistic-synthetic-20000', 'clean': 'realistic-clean-input'}
RUST = {'dev': 'realistic-run-development', 'cal': 'realistic-run-calibration', 'sealed': 'realistic-run-sealed',
        'synth': 'realistic-run-synthetic', 'clean': 'realistic-run-clean'}

# ------------------------------------------------------------------ lexicon
L = json.load(open(f'{REPO}/data/lexicon.json', encoding='utf-8'))
LEX = dict(subjects={s['name']: dict(aliases=list(s['aliases']), attributes=s['attributes']) for s in L['subjects']}, events=L['events'])
# partial names: a multi-word name without its 'Hooly ' prefix ('AI Pro', 'Pixel 10 Pro') when no other subject owns it
_own = {a.lower() for d in LEX['subjects'].values() for a in d['aliases']} | {n.lower() for n in LEX['subjects']}
for n, d in LEX['subjects'].items():
    if n.startswith('Hooly ') and ' ' in n[6:] and n[6:].lower() not in _own:
        d['aliases'].append(n[6:])
SUBJ = list(LEX['subjects'])
ATTRS = sorted({a for d in LEX['subjects'].values() for a in d['attributes']})
AI = {a: i for i, a in enumerate(ATTRS)}
PHYS_UNITS = set(V.PHYS_CS.values()) | set(V.PHYS_WORD.values())
PERSON = {s for s, d in LEX['subjects'].items() if {'joined', 'previous_employer', 'team_size', 'chairs', 'independent_director',
                                                       'desks_managed'} & set(d['attributes'])}

# ------------------------------------------------------------------ practice-trained artifacts
def mask_subjects(text, ents, keep=()):
    out, k = [], 0
    for s, e, n in ents:
        out.append(text[k:s]); out.append(' SUBJ ' if n not in keep else text[s:e]); k = e
    out.append(text[k:])
    return ''.join(out)


def train():
    rows = list(csv.DictReader(open(f'{REPO}/data/practice.csv', encoding='utf-8')))
    kind, units = {}, defaultdict(Counter)
    X, y = [], []
    for r in rows:
        facts = json.loads(r['form'])
        for f in facts:
            kind[f['attribute']] = f['value']['kind']
            if 'unit' in f['value']: units[f['attribute']][f['value']['unit']] += 1
        if len(facts) == 1:
            X.append(mask_subjects(r['text'], V.find_entities(r['text'], LEX))); y.append(facts[0]['attribute'])
    for a in ATTRS:  # lexicon-derived description (harness describe() without the subject): every class has its own words
        X.append('SUBJ ' + a.replace('_', ' ')); y.append(a)
    vec = make_union(TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5), sublinear_tf=True), TfidfVectorizer(ngram_range=(1, 2)))
    clf = LinearSVC(C=3).fit(vec.fit_transform(X), y)
    return vec, clf, kind, units


# ------------------------------------------------------------------ text rules
MON = r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
DATE_RX = (rf'(?:(?:the\s+)?(?P<d1>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<m1>{MON})\.?,?\s+(?P<y1>\d{{4}})'
           rf'|(?P<m2>{MON})\.?\s+(?P<d2>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y2>\d{{4}})|(?P<y3>\d{{4}})-(?P<m3>\d\d)-(?P<d3>\d\d))')
INTERVAL = re.compile(rf'^\s*(?:from|between)\s+(?P<a>{DATE_RX})\s*(?:through|thru|to|until|till|and|-|–)\s+(?P<b>{DATE_RX.replace("?P<", "?P<b_")})\s*,?\s*', re.I)


def _d(m, p=''):
    g = lambda k: m.group(p + k)
    if g('y3'): return date(int(g('y3')), int(g('m3')), int(g('d3')))
    y, mo, d = (g('y1'), g('m1'), g('d1')) if g('y1') else (g('y2'), g('m2'), g('d2'))
    return date(int(y), V.MONTHS[mo.lower().rstrip('.')], int(d))


def parse_interval(text):
    m = INTERVAL.match(text)
    if not m: return None, 0
    try:
        a, b = _d(m), _d(m, 'b_')
    except (ValueError, KeyError):
        return None, 0
    return [a.isoformat(), (b + timedelta(days=1)).isoformat()], m.end()


def stem(w): return w[:4] if len(w) > 3 else w  # ponytail: prefix stem; a real stemmer if prefixes collide


# English paraphrases of attribute words (added after dev inspection, generic wording, see REPORT.md)
SYN = [(re.compile(p), w) for p, w in [(r'\b(?:yearly|annually|a year|per year)\b', 'annual'), (r'\blasts\b', 'life'),
                                       (r'\bstarts at\b', 'minimum'), (r'\bup to\b', 'maximum'),
                                       (r'\b(?:costs?|pay|pays|paid)\b', 'price')]]  # v2 fix 3


SENT_END = re.compile(r'(?<!\bInc)(?<!\bLtd)(?<!\bCo)(?<!\bDr)(?<!\bMr)(?<!\bMs)(?<!\bSt)(?<!\bvs)[.!?]+(?=\s|$)')  # v2 fix 1: 'Series A.' ends a sentence
ADJUNCT_VERB = re.compile(r'\s+(?:is|are|was|has|have|had|does|did|costs?|comes?|runs?|lists?|keeps?|holds?|lasts?|gets?|includes?|'
                          r'supports?|covers?|starts?|went|offers?|promises?|serves?|employs?|takes?|weighs?|sold|brought|drew|answers?)\b')
PRON = re.compile(r"\b(?:it|its|it's|he|she|his|her|him)\b", re.I)  # singular only: generic 'they have X on ...' is not a subject
FIRST = re.compile(r"\b(?:I|my|me|mine|I'm|I'd|I've|someone|anyway)\b", re.I)
VALUE_FIRST = re.compile(r'\bis the [a-z0-9 \-]+? (?:at|for|of|to) ')
CMP = [(o, re.compile(r'\b(?:' + p + r')\s*$', re.I)) for o, p in [  # comparatives values.py leaves out (versions, dates, ...)
    ('le', r'no (?:newer|later|higher|more|greater) than|not (?:newer|later|higher|more) than|at most|up to'),
    ('ge', r'no (?:older|earlier|lower|less|fewer) than|not (?:older|earlier|lower|less) than|at least'),
    ('lt', r'older than|earlier than|lower than|less than|fewer than|below|before'),
    ('gt', r'newer than|later than|higher than|more than|greater than|above|after')]]
DOWN = re.compile(r'\bdown (?:for|as)\b', re.I)


def clauses(text, start, ents):
    """-> [(s, e)] clause spans of text[start:], split at sentence ends, ';', ', and', ', but', ' and <subject|pronoun>'."""
    ment_starts = {s for s, _, _ in ents}
    seps = []
    for m in SENT_END.finditer(text, start): seps.append((m.start(), m.end()))
    for m in re.finditer(r';\s*|,\s+(?:and|but|while|whereas)\s+|\s+(?:but|whereas)\s+', text[start:]): seps.append((start + m.start(), start + m.end()))
    for m in re.finditer(r',?\s+and\s+', text[start:]):
        e = start + m.end()
        pm = PRON.match(text, e)
        if e in ment_starts or (pm and pm.start() == e): seps.append((start + m.start(), e))
    seps.sort()
    out, k = [], start
    for s, e in seps:
        if s < k: continue
        if text[k:s].strip(): out.append((k, s))
        k = e
    if text[k:].strip(): out.append((k, len(text)))
    return out


def is_aside(ct, has_ment, has_pron):
    if has_ment: return False
    if FIRST.search(ct) and not DOWN.search(ct): return True
    return not has_pron  # caller decides for subject-less rows


# ------------------------------------------------------------------ Rust pairs (optional input signal)
def load_rust(world):
    out = defaultdict(list)
    if world not in RUST: return out
    p = f'{DATA}/{RUST[world]}/assertions.csv'
    if not os.path.exists(p): return out
    csv.field_size_limit(10 ** 8)
    for r in csv.DictReader(open(p, encoding='utf-8')):
        if r['status'] == 'paired' and r['subject'] and r['attribute']:
            spans = [(s['start'], s['end']) for s in json.loads(r['source_spans_json'] or '[]')]
            out[r['id']].append((r['subject'], r['attribute'], spans))
    return out


# ------------------------------------------------------------------ main extraction
class Extractor:
    def __init__(self, use_rust_pairs=None):
        self.vec, self.clf, self.kind, self.units = train()
        self.cls = list(self.clf.classes_)
        self.ci = {a: i for i, a in enumerate(self.cls)}
        self.rust = use_rust_pairs or {}
        self.aw = {a: [stem(w) for w in a.split('_')] for a in ATTRS}

    def overlap(self, ct, a):
        low = ct.lower()
        for rx, w in SYN: low = rx.sub(r'\g<0> ' + w, low)
        words = {stem(w) for w in re.findall(r'[a-z0-9]+', low)}
        aw = self.aw[a]
        hit = sum(w in words for w in aw)
        return hit / len(aw) + 0.2 * hit if aw else 0.0  # ponytail: + per-word bonus prefers the more specific attribute on ties

    def prep(self, r):
        """Label-free per-row structures; texts to classify: per clause, one variant per mentioned subject (only that subject
        masked) plus one unmasked variant for pronoun antecedents."""
        text = r['text'].replace('\u00ad', '')
        interval, off = parse_interval(text)
        ents = [x for x in V.find_entities(text, LEX) if not (text[x[0]:x[1]].islower() and ' ' not in text[x[0]:x[1]]
                and re.search(r'\b(?:a|an|any|no|major|minor|another)\s+(?:\w+\s+)?$', text[max(0, x[0] - 30):x[0]], re.I))]
        text = re.sub(r'(?<=[\s(])-(?=\d)', '\u2212', text)  # ' -29.58%': values.py skips a hyphen-led number; same length
        cands = V.extract_values(text, LEX)
        for x in cands:  # negative numbers
            if x['start'] and text[x['start'] - 1] == '\u2212' and isinstance(x['value'].get('value'), (int, float)) \
                    and not isinstance(x['value']['value'], bool):
                x['value']['value'] = -x['value']['value']
        taken = [(x['start'], x['end']) for x in cands if x['kind'] not in ('boolean', 'name')]
        for m in re.finditer(r'(?<![\w.,])v?(\d+(?:\.\d+){1,3})(?![\w%])(?!\.\d)', text):  # bare decimals nobody read: version
            if not any(a < m.end() and b > m.start() for a, b in taken) and not any(es < m.end() and ee > m.start() for es, ee, _ in ents):
                cands.append(dict(kind='version', value=dict(kind='version', value=m.group(1)), start=m.start(), end=m.end(),
                                  text=m.group(0), rule='version_bare', flags=['alt']))
        cl = []
        for cs, ce in clauses(text, off, ents):
            ct = text[cs:ce]
            ment = [(s - cs, e - cs, n) for s, e, n in ents if s >= cs and e <= ce]
            pron = PRON.search(ct)
            if not ment and FIRST.search(ct) and not DOWN.search(ct): continue  # first-person narrator aside
            cl.append(dict(cs=cs, ce=ce, ct=ct, ment=ment, pron=pron))
        if any(c['ment'] or c['pron'] for c in cl):
            cl = [c for c in cl if c['ment'] or c['pron']]  # subject-less clauses beside real ones are asides
        else:
            cl = cl[:1]  # a bare fragment row: its first clause continues the previous row
        texts = []
        for c in cl:
            c['var'] = {}
            for n in dict.fromkeys(m[2] for m in c['ment']):
                c['var'][n] = len(texts); texts.append(mask_subjects(c['ct'], [m for m in c['ment'] if m[2] == n]))
            c['var'][None] = len(texts); texts.append(c['ct'])
        return dict(id=r['id'], text=text, interval=interval, cands=cands, cl=cl), texts

    def resolve(self, P, S, prev_subjects):
        rust = self.rust.get(P['id'], [])
        out, row_subj = [], []
        for c in P['cl']:
            cs, ce, ct, ment, pm = c['cs'], c['ce'], c['ct'], c['ment'], c['pron']
            vc = [x for x in P['cands'] if x['start'] >= cs and x['end'] <= ce and x['kind'] != 'boolean']
            kinds = {x['kind'] for x in vc}
            # v2 fix 2: a mention used as a noun adjunct ('on Android version') after an earlier reference is not a candidate
            first = min([s for s, e, n in ment] + ([pm.start()] if pm else []), default=None)
            refs = [(s, [n]) for s, e, n in ment
                    if not (s > first and re.match(r'\s+[a-z]', ct[e:]) and not ADJUNCT_VERB.match(ct[e:]))]
            if pm or not refs:
                ante = list(dict.fromkeys(reversed(row_subj))) or list(prev_subjects)
                if pm and re.fullmatch(r'(?i)he|she|his|her|him', pm.group(0)):
                    ante = [n for n in ante if n in PERSON] or ante
                refs.append((pm.start() if pm else 10 ** 6, ante))
            # value-position constructions: 'I have V down for S...', 'V is the role at/for/of S' -> S is referenced first
            piv = DOWN.search(ct) or VALUE_FIRST.search(ct)
            refs.sort(key=lambda x: x[0] + (10 ** 7 if piv and x[0] < piv.end() else 0))
            pri = {}
            for rank, (_, ns) in enumerate(refs):
                for k, n in enumerate(ns): pri.setdefault(n, (1.0 if rank == 0 else 0.5) * (1.0 - 0.03 * k))
            if not pri: continue
            rb = [(s_, a_) for s_, a_, sp in rust if any(a < P['cs0'] + ce and b > P['cs0'] + cs for a, b in sp)] if rust else []
            best = None
            for n, p in pri.items():
                sv = S[c['var'].get(n, c['var'][None])]
                mt = mask_subjects(ct, [m for m in ment if m[2] == n]).replace(' SUBJ ', ' ')
                for a in LEX['subjects'][n]['attributes']:
                    k = self.kind[a]
                    sc = sv[self.ci[a]] + 1.5 * self.overlap(mt, a) + 2.0 * np.log(p)
                    if k == 'boolean':
                        sc -= 0.8 if kinds - {'name'} else 0.0
                    elif k == 'name':
                        if not any(x['kind'] == 'name' and x['value']['value'] != n for x in vc): sc -= 2.0
                    elif k not in kinds:
                        sc -= 2.0
                    if (n, a) in rb: sc += 3.0
                    if best is None or sc > best[0]: best = (sc, n, a)
            sc, n, a = best
            val = self.value(ct, cs, ce, vc, n, a)
            if val is None: continue
            out.append(dict(subject=n, attribute=a, value=val, conf=round(float(1 / (1 + np.exp(-sc))), 4)))
            row_subj.append(n)
        subj = list(dict.fromkeys(x['subject'] for x in out)) or prev_subjects
        return dict(id=P['id'], assertions=out, interval=P['interval']), subj

    def run_rows(self, rows):
        preps, texts = [], []
        for r in rows:
            P, t = self.prep(r)
            P['base'], P['cs0'] = len(texts), 0
            preps.append(P); texts += t
        S = self.clf.decision_function(self.vec.transform(texts)) if texts else None
        prev = []
        for P in preps:
            n = sum(len(c['var']) for c in P['cl'])
            o, prev = self.resolve(P, S[P['base']:P['base'] + n] if n else None, prev)
            yield o

    def value(self, ct, cs, ce, vc, subj, a):
        k = self.kind[a]
        if k == 'boolean':
            return dict(kind='boolean', value=not V.NEG_RE.search(ct))
        cs_ = [c for c in vc if c['kind'] == k]
        if k == 'name':
            cs_ = [c for c in cs_ if c['value']['value'] != subj and 'label' not in c['flags']]
            cs_.sort(key=lambda c: ('alt' in c['flags'], c['rule'] != 'name_lexicon' and len(c['value']['value'].split()) < 2))
        elif k == 'quantity' and self.units[a]:
            known = self.units[a]
            cs_.sort(key=lambda c: -known.get(c['value'].get('unit'), 0))
        elif k == 'date':
            cs_.sort(key=lambda c: 'alt' in c['flags'])
        if not cs_: return None
        v = dict(cs_[0]['value'])
        before = ct[:max(0, cs_[0]['start'] - cs)][-40:]
        if 'op' not in v and k != 'name':
            for op, rx in CMP:
                if rx.search(before): v['op'] = op; break
        # 'goes up to 353 seats' on a max attribute: the bound is the attribute itself (gold has no op)
        if v.get('op') == 'le' and set(a.split('_')) & {'max', 'maximum', 'limit', 'cap'} and re.search(r'\bup to\s*$', before):
            del v['op']
        # 6. counted noun outside the practice unit set of a one-unit attribute -> the practice (canonical) unit
        if k == 'quantity' and v.get('unit') not in self.units[a] and len(self.units[a]) == 1 and v.get('unit') not in PHYS_UNITS:
            only = next(iter(self.units[a]))
            if only not in PHYS_UNITS: v['unit'] = only
        return v


def run(world, use_rust=True):
    path = f'{DATA}/{WORLDS[world]}/public/universe.csv'
    rows = list(csv.DictReader(open(path, encoding='utf-8')))
    t0 = time.time()
    ex = Extractor(load_rust(world) if use_rust else None)
    t1 = time.time()
    os.makedirs('/tmp/veridyct-evalsuite/forms/B', exist_ok=True)
    os.makedirs(f'{HERE}/forms-v2', exist_ok=True)
    with open(f'{HERE}/forms-v2/{world}.jsonl', 'w', encoding='utf-8') as f:
        for o in ex.run_rows(rows):
            f.write(json.dumps(o, ensure_ascii=False) + '\n')
    t2 = time.time()
    print(json.dumps(dict(world=world, rows=len(rows), train_s=round(t1 - t0, 2), extract_s=round(t2 - t1, 2),
                          rust=bool(use_rust and world in RUST))))


def _selftest():
    assert parse_interval('From the 1st of October 2025 through the 31st of January 2026, Pixel 10 x.')[0] == ['2025-10-01', '2026-02-01']
    assert parse_interval('From February 1, 2026 through June 30, 2026, Hooly x.')[0] == ['2026-02-01', '2026-07-01']
    assert parse_interval('From 1 July 2026 through 29 October 2026, I have x.')[0] == ['2026-07-01', '2026-10-30']
    t = 'Hooly Pixel Watch does not have a cellular option; Hooly Pixel Watch has sold 152,133 watchs. Anyway, I lost it.'
    sp = clauses(t, 0, V.find_entities(t, LEX))
    assert [t[a:b] for a, b in sp][:2] == ['Hooly Pixel Watch does not have a cellular option', 'Hooly Pixel Watch has sold 152,133 watchs'], sp
    print('extract.py selftest OK')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--world'); ap.add_argument('--rust', action='store_true', help='add the Rust pair bonus (hurt dev: off by default)'); ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest: _selftest()
    else: run(a.world, a.rust)
