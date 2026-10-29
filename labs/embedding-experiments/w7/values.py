"""Deterministic typed-value extractor for VERIDYCT claims: regex + small tables, no ML.
Portability: no backreferences or recursion, but it leans on lookarounds, so a Rust port needs fancy-regex or hand-written boundary checks.

    extract_values(text, lex, exclude=(), common=None) -> list of candidates, in text order:
        {'kind', 'value' (the claimed_value.schema.json dict), 'start', 'end', 'text', 'rule', 'flags'}
    flags (informational, never used to drop a candidate): 'neg' (negation earlier in the clause), 'approx', 'range' (the
    contract reads those as nothing), 'alt' (a weaker reading: a year inside an event name, a lone sentence-initial
    capitalised word, a speaker/label tag, a clause-level boolean), 'in_name', 'label', 'weak' (a boolean in a sentence that
    also holds a number or date).
    exclude: canonical entity names whose mentions are NOT emitted as name candidates (the fact's own subject).
    common: optional set of lower-cased words seen in lower case in some corpus; a single sentence-initial capitalised
    word is a name candidate only when it is not in this set (without it, such a word is flagged 'alt').
Entity mentions (lexicon names/aliases/events) are masked before numbers are read, so 'Pixel 10' or 'Cloud Next 2026'
never yield a count or a year; the version rule reads a decimal straight after an entity or a capitalised word.
Contract deviations on purpose (gold data decides): inch unit is 'inch' (contract table says 'in'); every reading is kept
as a candidate and flagged instead of dropped when the contract says it "reads as nothing"."""
import re

# ------------------------------------------------------------------ tables
_ONES = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
WORDS = {w: i for i, w in enumerate(_ONES)}
TENS = {w: 10 * (i + 2) for i, w in enumerate('twenty thirty forty fifty sixty seventy eighty ninety'.split())}
_DIGITW = '|'.join(_ONES[1:10])
NUMWORD = (rf'(?:(?:{"|".join(TENS)})(?:[- ](?:{_DIGITW}))?|{"|".join(sorted(_ONES, key=len, reverse=True))}'
           rf'|a dozen|a hundred|(?:{"|".join(list(TENS) + _ONES[1:])})[- ]hundred)')
MONTHS = {m: i + 1 for i, ms in enumerate(['jan january', 'feb february', 'mar march', 'apr april', 'may', 'jun june', 'jul july',
                                          'aug august', 'sep sept september', 'oct october', 'nov november', 'dec december'])
          for m in ms.split()}
MONTH_RE = r'(?:' + '|'.join(sorted(MONTHS, key=len, reverse=True)) + r')'
CUR = {'€': 'EUR', '$': 'USD', '£': 'GBP', 'US$': 'USD'}
ISO = 'EUR USD GBP CHF RON PLN CZK HUF SEK NOK DKK JPY CNY INR CAD AUD'.split()
CUR_WORD = {'euro': 'EUR', 'euros': 'EUR', 'dollar': 'USD', 'dollars': 'USD', 'lei': 'RON'}
SCALE = {'thousand': 1e3, 'k': 1e3, 'million': 1e6, 'M': 1e6, 'billion': 1e9, 'bn': 1e9}
PERIOD = {'month': 'month', 'mo': 'month', 'monthly': 'month', 'year': 'year', 'yr': 'year', 'yearly': 'year', 'annually': 'year',
          'annum': 'year', 'week': 'week', 'wk': 'week', 'weekly': 'week', 'day': 'day', 'daily': 'day'}
DUR = {'ms': 'ms', 'millisecond': 'ms', 'milliseconds': 'ms', 's': 's', 'sec': 's', 'secs': 's', 'second': 's', 'seconds': 's',
       'min': 'min', 'mins': 'min', 'minute': 'min', 'minutes': 'min', 'h': 'h', 'hr': 'h', 'hrs': 'h', 'hour': 'h', 'hours': 'h',
       'd': 'day', 'day': 'day', 'days': 'day', 'week': 'week', 'weeks': 'week', 'wk': 'week', 'wks': 'week', 'month': 'month',
       'months': 'month', 'mo': 'month', 'mth': 'month', 'mths': 'month', 'year': 'year', 'years': 'year', 'yr': 'year',
       'yrs': 'year'}
DUR_MULT = {'fortnight': ('week', 2), 'fortnights': ('week', 2), 'decade': ('year', 10), 'decades': ('year', 10)}
# physical units: written form -> (symbol). Case-sensitive entries listed first (the contract: m/M, mW/MW, B).
PHYS_CS = {'B': 'B', 'KB': 'KB', 'MB': 'MB', 'GB': 'GB', 'TB': 'TB', 'kB': 'KB', 'kb': 'KB', 'mb': 'MB', 'gb': 'GB', 'tb': 'TB',
           'mm': 'mm', 'cm': 'cm', 'm': 'm', 'km': 'km', 'in': 'inch', 'g': 'g', 'kg': 'kg', 'mAh': 'mAh', 'Hz': 'Hz',
           'kHz': 'kHz', 'MHz': 'MHz', 'GHz': 'GHz', 'mW': 'mW', 'W': 'W', 'kW': 'kW', '"': 'inch', '″': 'inch'}
PHYS_WORD = {'byte': 'B', 'bytes': 'B', 'kilobyte': 'KB', 'kilobytes': 'KB', 'megabyte': 'MB', 'megabytes': 'MB', 'gigabyte': 'GB',
             'gigabytes': 'GB', 'gig': 'GB', 'gigs': 'GB', 'terabyte': 'TB', 'terabytes': 'TB', 'millimetre': 'mm',
             'millimetres': 'mm', 'millimeter': 'mm', 'millimeters': 'mm', 'centimetre': 'cm', 'centimetres': 'cm',
             'centimeter': 'cm', 'centimeters': 'cm', 'metre': 'm', 'metres': 'm', 'meter': 'm', 'meters': 'm',
             'kilometre': 'km', 'kilometres': 'km', 'kilometer': 'km', 'kilometers': 'km', 'inch': 'inch', 'inches': 'inch',
             'gram': 'g', 'grams': 'g', 'gramme': 'g', 'grammes': 'g', 'kilogram': 'kg', 'kilograms': 'kg', 'kilo': 'kg',
             'kilos': 'kg', 'hertz': 'Hz', 'kilohertz': 'kHz', 'megahertz': 'MHz', 'gigahertz': 'GHz', 'milliwatt': 'mW',
             'milliwatts': 'mW', 'watt': 'W', 'watts': 'W', 'kilowatt': 'kW', 'kilowatts': 'kW'}
IRREGULAR = {'people': 'person', 'men': 'man', 'women': 'woman', 'children': 'child', 'feet': 'foot', 'mice': 'mouse'}
STOP = set('''a an the of in on at by for from to with without into onto over under about around per and or but nor so as than
then that this these those it its they them their we our us you your he she his her i my me is are was were be been being am
has have had do does did will would can could may might shall should must not no now today yet still already also just only
each every both all any some more most less least much many few other another such very too even ever never again once twice
here there when where while whom who whose which what how why if because since until after before during through across
between against up down out off whereas though although both either neither one ones etc'''.split())
ADJ = set('paying active new registered free monthly daily weekly yearly concurrent simultaneous unique total open live '
          'official supported daily annual extra additional different separate individual single'.split())
DET = set('a an the of our their its his her my your these those this that'.split())
NEG_RE = re.compile(r"\b(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|n't\b|n’t\b", re.I)
APPROX_BEFORE = re.compile(r'(?:\babout|\baround|\bapproximately|\bapprox\.?|\broughly|\bnearly|\balmost|\bcirca|\bca\.?|\bsome|'
                           r'\bestimated|\best\.?|\bclose to|\bmore or less|~|≈|±)\s*$', re.I)
APPROX_AFTER = re.compile(r'\s*(?:or so\b|give or take\b|-ish\b)', re.I)
OPS_BEFORE = [('gt', r'(?:over|more than|greater than|higher than|above|exceeding|in excess of|upwards of)'),
              ('lt', r'(?:under|less than|fewer than|lower than|below)'),
              ('le', r'(?:up to|at most|no more than|not more than|maximum(?: of)?|max\.?|within)'),
              ('ge', r'(?:at least|no less than|not less than|no fewer than|minimum(?: of)?)')]
OPS_BEFORE = [(o, re.compile(r'(?:^|[\s(])' + p + r'\s*$', re.I)) for o, p in OPS_BEFORE]
OPS_DATE = [('lt', re.compile(r'(?:^|\s)(?:before|prior to)\s*$', re.I)), ('gt', re.compile(r'(?:^|\s)after\s*$', re.I)),
            ('le', re.compile(r'(?:^|\s)(?:by|no later than|until)\s*$', re.I)), ('ge', re.compile(r'(?:^|\s)no earlier than\s*$', re.I))]
OPS_AFTER = [('le', re.compile(r'\s*(?:or (?:less|fewer|under|below|lower|shorter))\b', re.I)),
             ('ge', re.compile(r'(?:\s*\+|\s*or (?:more|higher|above|longer|over)\b)', re.I))]

# ------------------------------------------------------------------ helpers
_DIGITS = r'\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?'
NUM = rf'(?<![\w.,/\-])(?:{_DIGITS})(?!\d)(?![.,]\d)'
NUM_ANY = rf'(?:{NUMWORD}|{NUM})'
MULT = r'(?:\s?(?:thousand|million|billion|bn|k|M)\b)'
_NUM_RE = re.compile(NUM)
_AMBIG = re.compile(r'\d+\.\d{3}')  # '1.500' reads as nothing, except a percentage


def num_value(s):
    """'1,234.5' -> 1234.5; 'twenty-four' -> 24; 'a dozen' -> 12; 'three hundred' -> 300; None if not a number."""
    s = s.strip().lower()
    if re.fullmatch(_DIGITS, s):
        f = float(s.replace(',', ''))
        return int(f) if f == int(f) and '.' not in s else f
    if s == 'a dozen': return 12
    if s == 'a hundred': return 100
    m = re.fullmatch(r'(\w+)[- ]hundred', s)
    if m: return (WORDS.get(m.group(1)) or TENS.get(m.group(1), 0)) * 100
    m = re.fullmatch(r'(' + '|'.join(TENS) + r')(?:[- ](\w+))?', s)
    if m: return TENS[m.group(1)] + (WORDS.get(m.group(2), 0) if m.group(2) else 0)
    return WORDS.get(s)


def singular(w):
    w = w.lower()
    if w in IRREGULAR: return IRREGULAR[w]
    if w.endswith('ies') and len(w) > 4: return w[:-3] + 'y'
    if re.search(r'(?:ch|sh|ss|x|z)es$', w): return w[:-2]
    if w.endswith('s') and not w.endswith('ss') and len(w) > 3: return w[:-1]
    return w


def _clean(v):
    return int(v) if isinstance(v, float) and v == int(v) and abs(v) < 1e15 else v


class _Ctx:
    def __init__(self, text, ents):
        self.t, self.ents = text, ents
        self.mask = bytearray(len(text))  # 1 = entity span (numbers inside are not read)
        for s, e, _ in ents:
            for i in range(s, e): self.mask[i] = 1
        self.m = ''.join('\x00' if self.mask[i] else c for i, c in enumerate(text))  # masked copy, same length
        self.claimed = bytearray(len(text))
        self.out = []

    def free(self, s, e): return not any(self.claimed[s:e]) and not any(self.mask[s:e])

    def add(self, kind, value, s, e, rule, claim=True, flags=()):
        if claim:
            for i in range(s, e): self.claimed[i] = 1
        fl = list(flags)
        self.out.append(dict(kind=kind, value=dict(kind=kind, **value), start=s, end=e, text=self.t[s:e], rule=rule, flags=fl))

    def clause_before(self, s):
        """Text of the clause (back to . , ; : ! ? • · | or blank line) before s."""
        k = max([self.t.rfind(c, 0, s) for c in '.,;:!?•·|'] + [self.t.rfind('\n\n', 0, s)])
        return self.t[k + 1:s]

    def op(self, s, e, kind):
        pre = self.clause_before(s)
        for o, rx in OPS_BEFORE:
            if rx.search(pre) and not (kind == 'date' and o == 'le' and False): return o
        if kind == 'date':
            for o, rx in OPS_DATE:
                if rx.search(pre): return o
        for o, rx in OPS_AFTER:
            if rx.match(self.t, e): return o
        return None

    def flags(self, s, e):
        pre, fl = self.clause_before(s), []
        if NEG_RE.search(pre): fl.append('neg')
        if APPROX_BEFORE.search(pre) or APPROX_AFTER.match(self.t, e): fl.append('approx')
        if (re.match(r'\s*(?:–|—|-|to)\s*[€$£]?\d', self.t[e:e + 12]) or re.search(r'\bbetween\s+(?:[€$£]?\d[\d.,]*\s*(?:[A-Za-z]{1,12}\s+)?and\s*[€$£]?)?$', pre)
                or re.search(r'(?:\d[\d.,]*\s*(?:[A-Za-z]{1,12}\s+)?(?:to|–|—|-)|(?<![A-Za-z€$£%])\d[\d.,]*\s+or)\s*[€$£]?$', pre)): fl.append('range')
        return fl

    def num_op(self, kind, value, s, e, rule, **extra):
        v = dict(value=value, **extra)
        op = self.op(s, e, kind)
        if op: v['op'] = op
        self.add(kind, v, s, e, rule, flags=self.flags(s, e))


# ------------------------------------------------------------------ entities (lexicon names, aliases, events)
_ENT_CACHE = {}


def _entity_re(lex, strict_case):
    key = (id(lex), strict_case)
    if key not in _ENT_CACHE:
        names = {}
        for n, d in lex['subjects'].items():
            names[n] = n
            for a in d['aliases']: names.setdefault(a, n)
        for ev in lex.get('events', []): names.setdefault(ev, ev)
        for n, d in lex['subjects'].items(): names[n] = n  # names beat another subject's alias
        low = {k.lower().replace('’', "'"): v for k, v in names.items()}
        # ponytail: a one-word alias written with a capital ('Photos', 'Maps') is an ordinary word in lower case ('4.9 billion photos')
        cs = [k for k in names if strict_case and ' ' not in k and k[:1].isupper() and k.lower() in low and names[k] != k]
        alts = sorted(low, key=len, reverse=True)
        pre = r"(?<![\w])(?:"
        post = r")(?![\w])(?!\.\d)"
        rx = re.compile(pre + '|'.join(re.escape(a).replace(r'\ ', r'\s*') for a in alts) + post, re.I)
        rx_cs = re.compile(pre + '|'.join(re.escape(a[0]) + '(?i:' + re.escape(a[1:]) + ')' for a in sorted(cs, key=len, reverse=True)) + post) if cs else None
        _ENT_CACHE[key] = (rx, rx_cs, low, {c.lower() for c in cs})
    return _ENT_CACHE[key]


def find_entities(text, lex, strict_case=True):
    """Longest-first, non-overlapping, case-insensitive lexicon mentions -> [(start, end, canonical_name)].
    strict_case=True: a one-word capitalised alias ('Photos', 'Maps', 'Chrome') must keep its capital initial."""
    rx, rx_cs, low, cs = _entity_re(lex, strict_case)
    t = text.replace('’', "'")
    out = []
    for m in rx.finditer(t):
        g = re.sub(r'\s+', ' ', m.group(0).lower())
        if g in cs and not (rx_cs and rx_cs.fullmatch(m.group(0))): continue  # lower-case 'photos': an ordinary word
        out.append((m.start(), m.end(), low[g]))
    return out


# ------------------------------------------------------------------ passes
def _money(c):
    cur_pre = r'(?P<cur>US\$|€|\$|£|\b(?:' + '|'.join(ISO) + r')\b)\s?'
    amt = r'(?P<n>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+,\d{2}(?!\d)|\d+(?:\.\d+)?)(?!\d)'
    per = (r'(?P<per>\s*(?:/\s*|\bper\s+|\ba\s+|\bevery\s+|\beach\s+)(?:(?:user|seat|member|editor|terabyte|TB|gigabyte|GB|device)\s*(?:/\s*|(?:per|a|each|every)\s+)?)?'
           r'(?P<p>month|mo|year|yr|week|wk|day)\b|\s*(?P<p2>monthly|yearly|annually|weekly|daily)\b|\s+per\s+annum\b)')
    pats = [re.compile(cur_pre + amt + r'(?P<mult>\s?(?:thousand|million|billion|bn|k|M)\b)?' + per + '?', re.I if False else 0)]
    after_cur = r'(?P<cur2>' + '|'.join(ISO) + r'|euros?|dollars?|lei)\b'
    pats.append(re.compile(r'(?<![\w.,/\-])' + amt + r'(?P<mult>\s?(?:thousand|million|billion|bn|k|M)\b)?\s?' + after_cur + per + '?'))
    for rx in pats:
        for mt in rx.finditer(c.m):
            s, e = mt.start(), mt.end()
            if not c.free(s, e): continue
            cur = CUR.get(mt.groupdict().get('cur') or '') or (mt.groupdict().get('cur') or '').upper()
            if mt.groupdict().get('cur2'):
                w = mt.group('cur2')
                cur = CUR_WORD.get(w.lower(), w.upper())
            n = mt.group('n')
            if _AMBIG.fullmatch(n): continue
            val = float(n.replace(',', '.') if re.fullmatch(r'\d+,\d{1,2}', n) else n.replace(',', ''))
            if mt.group('mult'):
                val *= SCALE[mt.group('mult').strip()] if mt.group('mult').strip() in SCALE else SCALE[mt.group('mult').strip().lower()]
            per_v = PERIOD.get((mt.group('p') or mt.group('p2') or ('annum' if mt.group('per') and 'annum' in mt.group('per') else '')).lower())
            extra = dict(currency=cur)
            if per_v: extra['per'] = per_v
            c.num_op('money', _clean(round(val, 6)), s, e, 'money', **extra)


def _percent(c):
    rx = re.compile(rf'(?:(?P<n>{NUM})|(?P<w>{NUMWORD}))\s?(?:%|percent\b|per\s?cent\b)', re.I)
    for mt in rx.finditer(c.m):
        if c.free(mt.start(), mt.end()):
            v = num_value(mt.group('n') or mt.group('w'))
            c.num_op('percent', v, mt.start(), mt.end(), 'percent')


def _dates(c):
    t = c.m
    day = r'(?P<d>\d{1,2})(?:st|nd|rd|th)?'
    # 2026-03-12 / 2026-03
    for mt in re.finditer(r'(?<![\w.,/\-])((?:19|20)\d{2})-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?(?![\d\-])', t):
        if c.free(mt.start(), mt.end()):
            v = '-'.join(g for g in mt.groups() if g)
            c.num_op('date', v, mt.start(), mt.end(), 'date_iso')
    pats = [  # 12 March 2026 / the 12th of March 2026 / 12March 2026
        (rf'(?<![\w.,/\-])(?:the\s+)?{day}\s*(?:of\s+)?(?P<mo>{MONTH_RE})\b\.?,?\s*(?P<y>(?:19|20)\d{{2}})(?!\d)', 'dmy'),
        # March 12, 2026 / Mar 12th 2026
        (rf'(?<![\w])(?P<mo>{MONTH_RE})\b\.?\s*{day},?\s+(?P<y>(?:19|20)\d{{2}})(?!\d)', 'mdy'),
        # March 2026
        (rf'(?<![\w])(?P<mo>{MONTH_RE})\b\.?,?\s*(?P<y>(?:19|20)\d{{2}})(?![\d,]\d)', 'my')]
    for p, tag in pats:
        for mt in re.finditer(p, t, re.I):
            if not c.free(mt.start(), mt.end()): continue
            mo = MONTHS[mt.group('mo').lower()]
            y = mt.group('y')
            v = f'{y}-{mo:02d}' + (f'-{int(mt.group("d")):02d}' if tag != 'my' else '')
            if tag != 'my' and not 1 <= int(mt.group('d')) <= 31: continue
            c.num_op('date', v, mt.start(), mt.end(), 'date_' + tag)


def _bare_year(c):
    for es, ee, canon in c.ents:  # 'Hooly Cloud Next 2026' also states the year 2026 (gold reads it so)
        for mt in re.finditer(r'(?<![\w.,/\-])(?:19|20)\d{2}(?![\w])', c.t[es:ee]):
            c.add('date', dict(value=mt.group(0)), es + mt.start(), es + mt.end(), 'date_year_in_name', claim=False, flags=['alt', 'in_name'])
    for mt in re.finditer(r'(?<![\w.,/\-$€£])(?:19|20)\d{2}(?![\w])(?![.,]\d)', c.m):
        if not c.free(mt.start(), mt.end()): continue
        nxt = re.match(r'\s+([A-Za-z]+)', c.m[mt.end():])
        if re.search(r'\bQ[1-4]\s*$', c.m[max(0, mt.start() - 4):mt.start()]): continue  # 'Q4 2026' is not a date
        if nxt and nxt.group(1).lower() not in STOP and nxt.group(1).lower() not in MONTHS and nxt.group(1)[0].islower():
            # '2026 customers' is not read as a year by the contract, but gold wording is the judge: keep, flag
            c.num_op('date', mt.group(0), mt.start(), mt.end(), 'date_year_counted')
            c.out[-1]['flags'].append('alt')
            continue
        c.num_op('date', mt.group(0), mt.start(), mt.end(), 'date_year')


def _versions(c):
    t = c.m
    for mt in re.finditer(r'(?<![\w.])(?:v|ver\.?|version)\s?(\d+(?:\.\d+){0,3})(?![\d])(?!\.\d)', t, re.I):
        if c.free(mt.start(), mt.end()) and (mt.group(0)[0] in 'vV' or True):
            c.add('version', dict(value=mt.group(1)), mt.start(), mt.end(), 'version_v', flags=c.flags(mt.start(), mt.end()))
    for mt in re.finditer(r'(?<![\w.])\d+(?:\.\d+){2,3}(?![\d])', t):
        if c.free(mt.start(), mt.end()):
            c.add('version', dict(value=mt.group(0)), mt.start(), mt.end(), 'version_dots')
    # decimal straight after an entity or a capitalised word: 'Hooly Gemini 2.2', 'Android 16.1', 'Chrome 71.0'
    for mt in re.finditer(r'(?<=[A-Za-z0-9\x00]) (\d+\.\d+)(?![\d%])(?!\.\d)', c.t.replace('’', "'") if False else t):
        s, e = mt.start(1), mt.end(1)
        if not c.free(s, e): continue
        k = mt.start()
        w = re.search(r'([A-Za-z0-9\x00]+)$', t[:k])
        word = w.group(1) if w else ''
        after_entity = any(es <= k <= ee for es, ee, _ in c.ents if ee == k)
        if after_entity or (len(word) > 1 and word[:1].isupper() and word.lower() not in MONTHS and word.lower() not in STOP and not word.isdigit()):
            if re.match(r'\s?(?:%|percent\b|stars?\b)', c.t[e:e + 9]): continue
            c.add('version', dict(value=mt.group(1)), s, e, 'version_after_name')


def _duration(c):
    t = c.m
    uw = '|'.join(sorted(list(DUR) + list(DUR_MULT), key=len, reverse=True))
    rx = re.compile(rf'(?:(?P<n>{NUM})|(?P<w>{NUMWORD}))(?P<sep>\s?|-)(?P<u>{uw})\b(?![\w-]*\d)', re.I)
    for mt in rx.finditer(t):
        s, e = mt.start(), mt.end()
        if not c.free(s, e): continue
        u = mt.group('u')
        if mt.group('n') and _AMBIG.fullmatch(mt.group('n')): continue
        if len(u) == 1 and mt.group('sep') == '-': continue
        if len(u) == 1 and not u.islower(): continue  # single-letter unit in lower case only
        if u.lower() in ('mo', 'd', 's', 'h') and mt.group('w'): continue
        v = num_value(mt.group('n') or mt.group('w'))
        ul = u.lower()
        if ul in DUR_MULT: ul, v = DUR_MULT[ul][0], v * DUR_MULT[ul][1]
        else: ul = DUR[ul]
        c.num_op('duration', _clean(v), s, e, 'duration', unit=ul)
    # 'a/an' + unit only after these words
    rx = re.compile(rf'\b(?:under|within|in|for|over|than|at least|at most|to|only|just|about|around)\s+(?P<a>an?)\s+(?P<u>{uw})\b', re.I)
    for mt in rx.finditer(t):
        s, e = mt.start('a'), mt.end('u')
        if not c.free(s, e): continue
        ul = mt.group('u').lower()
        v = 1
        if ul in DUR_MULT: ul, v = DUR_MULT[ul][0], DUR_MULT[ul][1]
        else: ul = DUR[ul]
        c.num_op('duration', v, s, e, 'duration_a', unit=ul)


def _quantity(c):
    t = c.m
    phys = '|'.join(sorted(list(PHYS_WORD) + [re.escape(k) for k in PHYS_CS if k not in '"″'], key=len, reverse=True))
    rx = re.compile(rf'(?:(?P<n>{NUM})|(?P<w>{NUMWORD}))(?P<mult>{MULT})?(?P<sep>\s?|-)(?P<u>{phys}|"|″)(?![\w])', 0)
    for mt in rx.finditer(t):
        s, e = mt.start(), mt.end()
        if not c.free(s, e): continue
        u = mt.group('u')
        if mt.group('n') and _AMBIG.fullmatch(mt.group('n')): continue
        sym = PHYS_CS.get(u) or PHYS_WORD.get(u.lower())
        if sym is None:
            sym = PHYS_CS.get(u.lower()) if u.lower() in ('kb', 'mb', 'gb', 'tb') else None
        if sym is None: continue
        if u in ('in',) and mt.group('sep') == '': continue
        if mt.group('w') and len(u) <= 2 and u not in ('mm', 'cm', 'km', 'kg', 'mW', 'kW', 'GB', 'MB', 'TB', 'Hz'): continue
        v = num_value(mt.group('n') or mt.group('w'))
        if mt.group('mult'): v *= SCALE[mt.group('mult').strip()]
        c.num_op('quantity', _clean(v), s, e, 'quantity_phys', unit=sym)
    # counted nouns: number (+ scale) then up to two words, then the noun
    rx = re.compile(rf'(?:(?P<n>{NUM})|(?P<w>{NUMWORD}))(?P<mult>{MULT})?(?P<pm>\+)?(?P<gap>[\s-]+)(?=[A-Za-z])', 0)
    for mt in rx.finditer(t):
        s, e = mt.start(), mt.end() - len(mt.group('gap'))
        if not c.free(s, e): continue
        raw = mt.group('n') or mt.group('w')
        if mt.group('n') and _AMBIG.fullmatch(raw): continue
        if mt.group('n') and re.fullmatch(r'(?:19|20)\d{2}', raw) and not mt.group('mult'):
            continue  # a plain four-digit number is a year (bare-year pass)
        v = num_value(raw)
        if v is None: continue
        if mt.group('mult'): v *= SCALE[mt.group('mult').strip()]
        # the words straight after the number (blanks or hyphens only between them), at most 3 from the first non-stop word
        seq, pos = [], mt.end()
        for w in re.finditer(r"[A-Za-z][A-Za-z'’]*", t[mt.end():mt.end() + 60]):
            if t[pos:mt.end() + w.start()].strip(' -') or len(seq) >= 4: break
            seq.append((w.group(0), mt.end() + w.start())); pos = mt.end() + w.end()
        i0 = next((i for i, (w, _) in enumerate(seq[:3]) if w.lower() not in STOP), None)
        if i0 is None: continue
        run = []
        for w, off in seq[i0:i0 + 3]:
            if w.lower() in STOP: break
            run.append((w, off))
        # head noun: the first plural-looking word of the run ('4 storage tiers' -> tier, '1,200 paying customers' -> customer),
        # else the first word that is not a modifier ('1 office'); ponytail: no POS tagger, '-ing/-ed/ADJ' list is the ceiling
        plural = [x for x in run if x[0].lower() in IRREGULAR or (x[0].lower().endswith('s') and not x[0].lower().endswith('ss') and len(x[0]) > 3)]
        head = plural[0] if plural else run[0]
        if not plural and len(run) > 1 and (head[0].lower().endswith(('ing', 'ed')) or head[0].lower() in ADJ): head = run[1]
        w, off = head
        op = c.op(s, mt.end(), 'quantity') or ('ge' if mt.group('pm') else None)
        value = dict(value=_clean(v), unit=singular(w))
        if op: value['op'] = op
        c.add('quantity', value, s, off + len(w), 'quantity_noun', flags=c.flags(s, off + len(w)))


def _booleans(c):
    t = c.t
    # sentences: end at . ! ? before a space (abbreviations aside) or a blank line
    abbr = ('e.g', 'i.e', 'vs', 'approx', 'Inc', 'Ltd', 'Co', 'Corp', 'Dr', 'Mr', 'Mrs', 'Ms', 'Prof', 'St', 'No')
    ends = [m.end() for m in re.finditer(r'[.!?]+(?=\s)|\n\s*\n', t)
            if not (t[m.start()] == '.' and (re.search(r'(?:^|[\s(])(?:' + '|'.join(re.escape(a) for a in abbr) + r'|[A-Z])$', t[:m.start()])))]
    bounds, prev = [], 0
    for e in ends + [len(t)]:
        if t[prev:e].strip(): bounds.append((prev, e))
        prev = e
    typed = [(x['start'], x['end']) for x in c.out if x['kind'] not in ('name', 'boolean')]
    for s, e in bounds:
        sent = t[s:e]
        neg = bool(NEG_RE.search(sent))
        weak = any(a >= s and b <= e for a, b in typed)
        c.add('boolean', dict(value=not neg), s, e, 'bool_sentence', claim=False, flags=['weak'] if weak else [])
        # clauses whose polarity differs from the sentence's
        for cs, ce in _clauses(sent):
            cneg = bool(NEG_RE.search(sent[cs:ce]))
            if cneg != neg and len(sent[cs:ce].split()) >= 2:
                c.add('boolean', dict(value=not cneg), s + cs, s + ce, 'bool_clause', claim=False, flags=['alt'])


def _clauses(sent):
    parts, k = [], 0
    for m in re.finditer(r'[,;:](?=\s)|\s(?:but|though|while|whereas|yet)\s|\sand\s(?=(?:the|a|an|it|they|he|she|we|[A-Z]))', sent):
        parts.append((k, m.start())); k = m.end()
    parts.append((k, len(sent)))
    return [(a, b) for a, b in parts if b > a]


STOP_NAME = set(('the a an our we it this that these those yes no today now here there then and but or so if when while as of in on at '
                 'by for from to with without is are was were be he she they i you his her its their my your what who how why '
                 'also still only just once after before during since until sadly thanks thank see please hello hi okay ok one two '
                 'three four five six seven eight nine ten monday tuesday wednesday thursday friday saturday sunday '
                 'january february march april may june july august september october november december').split())


def _names(c, exclude=(), common=None):
    t = c.t
    ex = set(exclude)
    for s, e, canon in c.ents:
        if canon in ex: continue
        c.add('name', dict(value=canon), s, e, 'name_lexicon', claim=False, flags=['neg'] if NEG_RE.search(c.clause_before(s)) else [])
    # capitalised runs outside entities: 'Gavin Bellson', 'Kestrel Bank', 'Frankfurt'
    ent_mask = c.mask
    CAPW = r"[A-Z][A-Za-z'’]+(?:-[A-Z][A-Za-z]+)*"
    for mt in re.finditer(r"(?<![\w'’])" + CAPW + r"(?:\s+(?:de |van |von |of )?" + CAPW + r")*", t):
        s, e = mt.start(), mt.end()
        if any(ent_mask[s:e]):
            # trim entity parts out of the run: take capitalised words not in the mask
            parts = [(m2.start(), m2.end()) for m2 in re.finditer(CAPW, mt.group(0)) if not ent_mask[s + m2.start()]]
            runs, cur = [], []
            for a, b in parts:
                if cur and t[s + cur[-1][1]:s + a].strip() == '': cur.append((a, b))
                else:
                    if cur: runs.append(cur)
                    cur = [(a, b)]
            if cur: runs.append(cur)
            spans = [(s + r[0][0], s + r[-1][1]) for r in runs]
        else:
            spans = [(s, e)]
        for a, b in spans:
            txt = t[a:b]
            start_sent = not t[:a].strip() or re.search(r'[.!?:]\s*$', t[:a]) is not None or re.search(r'^\s*[\"“”]$', t[max(0, a - 2):a]) is not None
            while ' ' in txt:  # peel leading function words ('Our') and role abbreviations ('CTO') off a multi-word run
                w1 = txt.split()[0]
                if w1.lower().rstrip("'’s") in STOP_NAME or re.fullmatch(r'[A-Z]{2,4}', w1):
                    k = len(txt) - len(txt[len(w1):].lstrip()); a, txt = a + k, txt[k:]
                else: break
            if txt.lower().rstrip("'’s") in STOP_NAME or re.fullmatch(r'[A-Z]{2,5}', txt): continue  # function words, acronyms (CTO, EU)
            if txt in ex or txt.lower() in {x.lower() for x in ex}: continue
            label = re.match(r'\s*:', t[a + len(txt):]) is not None and start_sent  # 'Gavin: ...', 'Venue: ...' speaker/label tags
            fl = ['neg'] if NEG_RE.search(c.clause_before(a)) else []
            if label: fl += ['alt', 'label']
            elif start_sent and ' ' not in txt and (common is None or txt.lower() in common): fl += ['alt']  # 'Doors open ...': a plain word
            c.add('name', dict(value=txt), a, a + len(txt), 'name_cap' + ('_start' if start_sent else ''), claim=False, flags=fl)


# ------------------------------------------------------------------ public API
def extract_values(text, lex, exclude=(), common=None):
    text = text.replace('­', '')
    ents = find_entities(text, lex)
    c = _Ctx(text, ents)
    _money(c); _percent(c); _dates(c); _versions(c); _duration(c); _quantity(c); _bare_year(c)
    _names(c, exclude, common); _booleans(c)
    return sorted(c.out, key=lambda x: (x['start'], x['end'], x['kind']))


def _selftest():
    import json, os
    L = json.load(open('/tmp/veridyct-emb/common/lexicon.json', encoding='utf-8'))
    lex = dict(subjects={s['name']: dict(aliases=s['aliases'], attributes=s['attributes']) for s in L['subjects']}, events=L['events'])
    def has(text, want):
        vs = [x['value'] for x in extract_values(text, lex)]
        assert want in vs, (text, want, vs)
    has('128 GB of storage', dict(kind='quantity', value=128, unit='GB'))
    has('128GB', dict(kind='quantity', value=128, unit='GB'))
    has('2 terabytes', dict(kind='quantity', value=2, unit='TB'))
    has('a 5,000 mAh battery', dict(kind='quantity', value=5000, unit='mAh'))
    has('weighs 1.2 kg', dict(kind='quantity', value=1.2, unit='kg'))
    has('a 65-watt charger', dict(kind='quantity', value=65, unit='W'))
    has('speaks 40 languages', dict(kind='quantity', value=40, unit='language'))
    has('speaks forty languages', dict(kind='quantity', value=40, unit='language'))
    has('1.2 million users', dict(kind='quantity', value=1200000, unit='user'))
    has('10k steps', dict(kind='quantity', value=10000, unit='step'))
    has('twenty-four engineers', dict(kind='quantity', value=24, unit='engineer'))
    has('a dozen partners', dict(kind='quantity', value=12, unit='partner'))
    has('over 10,000 customers', dict(kind='quantity', value=10000, unit='customer', op='gt'))
    has('10,000+ customers', dict(kind='quantity', value=10000, unit='customer', op='ge'))
    has('uploads up to 25 MB', dict(kind='quantity', value=25, unit='MB', op='le'))
    has('€49 a month', dict(kind='money', value=49, currency='EUR', per='month'))
    has('49 euros per month', dict(kind='money', value=49, currency='EUR', per='month'))
    has('€49,99 a month', dict(kind='money', value=49.99, currency='EUR', per='month'))
    has('€10 per user per month', dict(kind='money', value=10, currency='EUR', per='month'))
    has('€490 per annum', dict(kind='money', value=490, currency='EUR', per='year'))
    has('$299.99', dict(kind='money', value=299.99, currency='USD'))
    has('a €12M seed round', dict(kind='money', value=12000000, currency='EUR'))
    has('€1.2bn', dict(kind='money', value=1200000000, currency='EUR'))
    has('1,999 lei', dict(kind='money', value=1999, currency='RON'))
    has('under $300', dict(kind='money', value=300, currency='USD', op='lt'))
    has('99.99% uptime', dict(kind='percent', value=99.99))
    has('fifty percent', dict(kind='percent', value=50))
    has('over 99% accuracy', dict(kind='percent', value=99, op='gt'))
    has('12th March 2026', dict(kind='date', value='2026-03-12'))
    has('March 12, 2026', dict(kind='date', value='2026-03-12'))
    has('since 1 Mar. 2026', dict(kind='date', value='2026-03-01'))
    has('Sept 2026', dict(kind='date', value='2026-09'))
    has('founded in 2025', dict(kind='date', value='2025'))
    has('2026-03-12', dict(kind='date', value='2026-03-12'))
    has('before March 2026', dict(kind='date', value='2026-03', op='lt'))
    has('v2.3', dict(kind='version', value='2.3'))
    has('version 2.3', dict(kind='version', value='2.3'))
    has('2.3.1', dict(kind='version', value='2.3.1'))
    has('Hooly Gemini 2.2', dict(kind='version', value='2.2'))
    has('a 14-day trial', dict(kind='duration', value=14, unit='day'))
    has('two weeks', dict(kind='duration', value=2, unit='week'))
    has('for a fortnight', dict(kind='duration', value=2, unit='week'))
    has('24h', dict(kind='duration', value=24, unit='h'))
    has('500 ms', dict(kind='duration', value=500, unit='ms'))
    has('answers in under a second', dict(kind='duration', value=1, unit='s', op='lt'))
    has('within an hour', dict(kind='duration', value=1, unit='h', op='le'))
    has('The app isn\'t SOC 2 certified', dict(kind='boolean', value=False))
    has('Hooly passed its SOC 2 audit', dict(kind='boolean', value=True))
    has('founded by Gavin Bellson', dict(kind='name', value='Gavin Bellson'))
    for bad, kind in (('1,5 GB', 'quantity'), ('99,9% uptime', 'percent'), ('1.500 mAh', 'quantity'), ('12/03/2026', 'date')):
        got = [x for x in extract_values(bad, lex) if x['kind'] == kind]
        assert not got, (bad, got)
    print('values.py selftest: OK')


if __name__ == '__main__':
    _selftest()
