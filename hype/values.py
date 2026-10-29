"""Rule-based value candidates from one sentence, following contracts/value-forms.md.

extract(text, masks=(), known_units=None) -> [{"v": value dict, "s": start, "e": end}]
Values read nothing when approximate, negated in their clause, a range end, ambiguous or next to an invisible char.
"""
import re

INVIS = "​‌‍⁠﻿­⁢⁣"
MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
MON_RE = r"(?i:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
WORDNUM = {w: i for i, w in enumerate(ONES)}
for i, t in enumerate(TENS):
    if i >= 2:
        WORDNUM[t] = i * 10
        for j in range(1, 10):
            WORDNUM[f"{t}-{ONES[j]}"] = i * 10 + j
            WORDNUM[f"{t} {ONES[j]}"] = i * 10 + j
WORDNUM.update({"a dozen": 12, "a hundred": 100, "dozen": 12})
for j in range(1, 10):
    WORDNUM[f"{ONES[j]} hundred"] = j * 100
_w = "|".join(sorted(map(re.escape, WORDNUM), key=len, reverse=True))
NUM = rf"(?:(?i:{_w})(?![A-Za-z])|\d[\d.,]*\d|\d)"
SCALE = r"(?:\s?(?i:thousand|million|billion)(?![A-Za-z])|(?-i:M|bn|k)(?![A-Za-z]))"
SCALEV = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "m": 1e6, "bn": 1e9, "k": 1e3}

DATA = {"B": "B", "KB": "KB", "MB": "MB", "GB": "GB", "TB": "TB", "kB": "KB", "kb": "KB", "mb": "MB", "gb": "GB", "tb": "TB"}
DATA_W = {"byte": "B", "kilobyte": "KB", "megabyte": "MB", "gigabyte": "GB", "gig": "GB", "terabyte": "TB"}
SYM = {**DATA, "mm": "mm", "cm": "cm", "m": "m", "km": "km", "mAh": "mAh", "g": "g", "kg": "kg",
       "Hz": "Hz", "kHz": "kHz", "MHz": "MHz", "GHz": "GHz", "mW": "mW", "W": "W", "kW": "kW",
       "ms": "ms", "s": "s", "h": "h", "d": "day"}
WORD = {**DATA_W, "millimetre": "mm", "millimeter": "mm", "centimetre": "cm", "centimeter": "cm", "metre": "m", "meter": "m",
        "kilometre": "km", "kilometer": "km", "inch": "inch", "inche": "inch", "gram": "g", "gramme": "g", "kilogram": "kg", "kilo": "kg",
        "hertz": "Hz", "kilohertz": "kHz", "megahertz": "MHz", "gigahertz": "GHz", "milliwatt": "mW", "watt": "W", "kilowatt": "kW",
        "sec": "s", "second": "s", "min": "min", "minute": "min", "hr": "h", "hour": "h", "day": "day", "week": "week", "wk": "week",
        "month": "month", "mo": "month", "mth": "month", "year": "year", "yr": "year"}
DUR_UNITS = {"ms", "s", "min", "h", "day", "week", "month", "year"}
_sym = "|".join(sorted(SYM, key=len, reverse=True))
_wrd = "|".join(sorted(list(WORD) + ["fortnight", "decade"], key=len, reverse=True))
UNIT = rf"(?:(?-i:{_sym})(?![A-Za-z])|(?i:{_wrd})(?:e?s)?(?![A-Za-z]))"
STOP = set("of our the a an and to in for on at by with is are was were that this these those it its their his her as or but from "
           "into over under than each every per been be has have had will can who which when where while so such also only just "
           "more most less least very now today then there here your my we they you he she i not no".split())
PLUR_IRREG = {"people": "person", "men": "man", "women": "woman", "children": "child", "centres": "centre", "ides": "ide"}

CUR = {"€": "EUR", "$": "USD", "£": "GBP", "US$": "USD"}
ISO = "EUR USD GBP CHF RON PLN CZK HUF SEK NOK DKK JPY CNY INR CAD AUD".split()
CUR_W = {"euro": "EUR", "euros": "EUR", "dollar": "USD", "dollars": "USD", "lei": "RON"}
PERIOD = {"month": "month", "mo": "month", "day": "day", "week": "week", "year": "year", "yr": "year", "annum": "year", "monthly": "month", "annually": "year", "daily": "day", "weekly": "week", "yearly": "year"}

NEGW = re.compile(r"\b(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|n[’']t\b", re.I)
KEEPNEG = re.compile(r"\b(?:no|not)\s+(?:more|less|fewer|later|earlier)\s+than\b", re.I)
CLAUSE = re.compile(r"[.,;:!?•·|]|\n\s*\n")
APPROX_B = re.compile(r"(?:\b(?:about|around|approximately|approx|roughly|nearly|almost|circa|ca|some|estimated|est|close to|more or less)\b\.?|[~≈±])\s*$", re.I)
APPROX_A = re.compile(r"^\s*(?:or so\b|give or take\b|-ish\b)", re.I)
OPB = [(r"(?:over|more than|greater than|higher than|above|exceeding|in excess of|upwards of)", "gt"),
       (r"(?:under|less than|fewer than|lower than|below)", "lt"),
       (r"(?:up to|at most|no more than|not more than|maximum(?: of)?|max)", "le"),
       (r"(?:at least|no less than|not less than|no fewer than|minimum(?: of)?)", "ge")]
OPB = [(re.compile(r"\b" + p + r"\s*(?:a |an )?$", re.I), o) for p, o in OPB]
OPDATE = [(re.compile(r"\b(?:before|prior to)\s*$", re.I), "lt"), (re.compile(r"\bafter\s*$", re.I), "gt"),
          (re.compile(r"\b(?:by|no later than)\s*$", re.I), "le"), (re.compile(r"\bno earlier than\s*$", re.I), "ge")]
OPWITHIN = re.compile(r"within\s*(?:a |an )?$", re.I)
OPA = [(re.compile(r"^\s*or (?:less|fewer|under|below|lower|shorter)\b", re.I), "le"),
       (re.compile(r"^\s*or (?:more|higher|above|longer|over)\b", re.I), "ge"), (re.compile(r"^\+"), "ge")]
RANGE_B = re.compile(r"(?:\bbetween\s+(?:\S+\s+){1,2}and\s+|\bbetween\s+|\d\s+or\s+|\d\s*(?:[-–—]|to)\s*[€$£]?\s*)$", re.I)
RANGE_A = re.compile(r"^\s*(?:[-–—]|to)\s*[€$£]?\d|^\s*or\s+\d+\s*[a-zA-Z]", re.I)


def parse_num(tok, money=False, pct=False):
    if tok.lower() in WORDNUM:
        return float(WORDNUM[tok.lower()])
    if tok.count(".") > 1 or tok.endswith((",", ".")):
        return None
    if "," in tok:
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", tok):
            return float(tok.replace(",", ""))
        if money and re.fullmatch(r"\d+,\d{2}", tok):
            return float(tok.replace(",", "."))
        return None
    if "." in tok:
        a, b = tok.split(".")
        if len(b) == 3 and not pct and a != "0":
            return None
        return float(tok)
    return float(tok)


def _clean(x):
    return int(x) if x == int(x) else round(x, 12)


def _sing(w):
    w = w.lower()
    if w in PLUR_IRREG:
        return PLUR_IRREG[w]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("ches", "shes", "xes", "sses")):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _op(before, after, kind, unit=None):
    pre = before[-40:]
    if kind == "date":
        for r, o in OPDATE:
            if r.search(pre):
                return o
        return None
    if kind == "duration" and OPWITHIN.search(pre):
        return "le"
    for r, o in OPB:
        if r.search(pre):
            return o
    for r, o in OPA:
        if r.search(after[:20]):
            return o
    return None


def _mk(kind, val, op=None, **kw):
    v = {"kind": kind, "value": val, **kw}
    if op:
        v["op"] = op
    return v


def extract(text, masks=(), known_units=None, known_unit_map=None):
    """masks: (start,end) spans (subject mentions) where bare numbers/years are not values."""
    raw = text
    text = re.sub(r"(?<=[A-Za-z])­(?=[A-Za-z])", "", raw)
    text = "".join("\0" if c in INVIS else c for c in text)
    if len(text) != len(raw):
        masks = ()  # offsets shifted; masks only affect bare numbers
    taken = []
    out = []
    n = len(text)

    def free(s, e):
        return not any(s < b and a < e for a, b in taken)

    def masked(s, e):
        return any(s < b and a < e for a, b in masks)

    def add(s, e, v, check_neg=True, check_apx=True, claim=True, kind=None):
        if not free(s, e):
            return False
        if claim:
            taken.append((s, e))
        before, after = text[:s], text[e:]
        if "\0" in text[max(0, s - 1):s] + text[s:e] + text[e:e + 1]:
            return False
        if check_apx and (APPROX_B.search(before[-25:]) or APPROX_A.search(after[:15])):
            return False
        if RANGE_B.search(before[-14:]) or RANGE_A.search(after[:16]):
            return False
        if check_neg:
            cl = CLAUSE.split(before)[-1]
            cl = KEEPNEG.sub(" ", cl)
            if NEGW.search(cl):
                return False
        op = _op(before, after, v["kind"])
        if op:
            v = dict(v, op=op)
        out.append({"v": v, "s": s, "e": e})
        return True

    # numeric dates: consumed, read as nothing
    for m in re.finditer(r"(?<![\d.])\d{1,2}[./]\d{1,2}[./]\d{2,4}(?![\d])", text):
        taken.append(m.span())
    # ISO dates
    for m in re.finditer(r"(?<![\d.\-])(\d{4})-(\d{2})(?:-(\d{2}))?(?![\d\-])", text):
        y, mo, d = m.group(1), m.group(2), m.group(3)
        if 1 <= int(mo) <= 12 and (d is None or 1 <= int(d) <= 31):
            add(*m.span(), _mk("date", "-".join(x for x in (y, mo, d) if x)))
    # textual dates
    mon = lambda s: MONTHS[s.lower()[:3]]
    pats = [(rf"(?<![\d.])(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s*({MON_RE})\.?,?\s+(\d{{4}})(?!\d)", lambda m: (m[3], m[2], m[1])),
            (rf"\b({MON_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\d)", lambda m: (m[3], m[1], m[2])),
            (rf"\b({MON_RE})\.?,?\s+(\d{{4}})(?!\d)", lambda m: (m[2], m[1], None))]
    for p, f in pats:
        for m in re.finditer(p, text):
            y, mo, d = f(m)
            if d is not None and not 1 <= int(d) <= 31:
                continue
            add(*m.span(), _mk("date", f"{y}-{mon(mo):02d}" + (f"-{int(d):02d}" if d else "")))
    # versions
    for m in re.finditer(r"(?<![\w.])(?:v|ver\.?|version)\s?(\d+(?:\.\d+)*)(?![\w]|\.\d)", text, re.I):
        if m.group(0)[0] in "vV" and m.group(0)[1:2].isalpha() and not re.match(r"(?i)ver", m.group(0)):
            continue
        add(*m.span(), _mk("version", m.group(1)), check_apx=False)
    for m in re.finditer(r"(?<![\w.])\d+\.\d+(?:\.\d+)+(?![\w]|\.\d)", text):
        add(*m.span(), _mk("version", m.group(0)), check_apx=False)
    for m in re.finditer(rf"\b[A-Z][A-Za-z]+\s(\d+\.\d+)(?!\d)(?!\.\d)(?!\s?(?:%|percent|per cent|stars?\b|{UNIT}))", text):
        if free(m.start(1), m.end(1)) and not NEGW.search(CLAUSE.split(text[:m.start()])[-1]):
            add(m.start(1), m.end(1), _mk("version", m.group(1)), check_apx=False)
    # money
    cur = r"(?:US\$|[€$£]|\b(?:" + "|".join(ISO) + r")\b)"
    per = r"(?:\s*(?:per user|/\s?seat|per seat|a user|per [a-z]+))?\s*(?:/\s?|per\s+|a\s+|an\s+|each\s+|every\s+)?(month|mo|day|week|year|yr|annum)\b|\s*(monthly|annually|daily|weekly|yearly)\b"
    money = [(rf"({cur})\s?({NUM})({SCALE})?", "pre"), (rf"({NUM})({SCALE})?\s?({cur}|(?i:euros?|dollars?|lei)\b)", "post")]
    for p, mode in money:
        for m in re.finditer(p, text):
            if mode == "pre":
                c, num, sc = m.group(1), m.group(2), m.group(3)
            else:
                num, sc, c = m.group(1), m.group(2), m.group(3)
            val = parse_num(num, money=True)
            if val is None:
                continue
            if sc:
                val *= SCALEV[sc.strip().lower()] if sc.strip().lower() in SCALEV else SCALEV[sc.strip()]
            code = CUR.get(c) or CUR_W.get(c.lower()) or c.upper()
            e = m.end()
            pm = re.match(per, text[e:], re.I)
            kw = {"currency": code}
            if pm:
                kw["per"] = PERIOD[(pm.group(1) or pm.group(2)).lower()]
                e += pm.end()
            # a second "€x"-like cap: "€5 on the other hand" is fine
            add(m.start(), e, _mk("money", _clean(val), **kw))
    # percent
    for m in re.finditer(rf"({NUM})\s?(?:%|(?i:per ?cent|percent)\b)", text):
        val = parse_num(m.group(1), pct=True)
        if val is not None:
            add(*m.span(), _mk("percent", _clean(val)))
    # quantities / durations with units
    for m in re.finditer(rf"(?<![\w.,/$€£-])({NUM})({SCALE})?[-\s]?(?:({UNIT})|(?:(?<=\d)[\"″]))", text):
        num, sc, unit = m.group(1), m.group(2), m.group(3)
        if unit is None:
            unit = "inch"
        val = parse_num(num)
        if val is None or not free(m.start(), m.end()):
            continue
        if sc:
            k = sc.strip().lower() if sc.strip().lower() in SCALEV else sc.strip()
            val *= SCALEV[k]
        if unit in SYM:
            u = SYM[unit]
        else:
            w = unit.lower()
            if w in ("fortnight", "fortnights"):
                u, val = "week", val * 2
            elif w in ("decade", "decades"):
                u, val = "year", val * 10
            else:
                u = WORD.get(w) or WORD.get(w[:-1]) or WORD.get(w[:-2])
            if u is None:
                continue
        if u == "m" and unit == "m" and re.match(r"\s*[A-Za-z]", text[m.end():]) and False:
            continue
        add(m.start(), m.end(), _mk("duration" if u in DUR_UNITS else "quantity", _clean(val), unit=u))
    # "a/an" durations
    for m in re.finditer(r"\b(?:under|within|in|for|over|than|at least|at most|to|only|just|about|around)\s+(?:a|an)\s+((?i:second|minute|hour|day|week|month|year|fortnight|decade))\b", text):
        u = m.group(1).lower()
        a, b = m.start(1) - 2 if text[m.start(1) - 2:m.start(1) - 1] == "a" else m.start(1) - 3, m.end(1)
        a = m.start(1) - (2 if text[m.start(1) - 2] == "a" else 3)
        v = 1; uu = {"second": "s", "minute": "min", "hour": "h"}.get(u, u)
        if u == "fortnight":
            v, uu = 2, "week"
        elif u == "decade":
            v, uu = 10, "year"
        add(a, b, _mk("duration", v, unit=uu))
    # counted nouns and bare years
    for m in re.finditer(rf"(?<![\w.,/$€£-])({NUM})({SCALE})?(?=[-\s]|$)", text):
        s, e = m.span()
        num = m.group(1)
        if not free(s, e) or masked(s, e):
            continue
        isword = num.lower() in WORDNUM
        if re.fullmatch(r"(19|20)\d\d", num):
            if not re.match(r"\s*(?i:[a-z])", text[e:e + 3]) or True:
                add(s, e, _mk("date", num), check_apx=False)
            continue
        val = parse_num(num)
        if val is None:
            continue
        if m.group(2):
            k = m.group(2).strip().lower() if m.group(2).strip().lower() in SCALEV else m.group(2).strip()
            val *= SCALEV[k]
        rest = text[e:]
        ws = re.match(r"(?:[-\s]+([A-Za-z][A-Za-z'’-]*)){1,3}", rest)
        words = re.findall(r"[-\s]+([A-Za-z][A-Za-z'’]*)", rest[:60])
        # take consecutive words until punctuation
        cand, pos = [], 0
        for wm in re.finditer(r"[-\s]+([A-Za-z][A-Za-z'’]*)", rest):
            if wm.start() != pos:
                break
            cand.append((wm.group(1), wm.end())); pos = wm.end()
            if len(cand) == 3:
                break
        nouns = []
        for w, ep in cand:
            sw = _sing(w)
            if known_units is not None and sw in known_units:
                nouns.append((sw, e + ep))
        if not nouns and cand:
            w, ep = cand[0]
            if w.lower() not in STOP and w[0].islower():
                nouns.append((_sing(w), e + ep))
        done = 0
        for noun, endpos in nouns:
            if add(s, endpos, _mk("quantity", _clean(val), unit=noun), claim=False):
                done = max(done, endpos)
        if done:
            taken.append((s, done))
    out.sort(key=lambda c: c["s"])
    return out


def has_negation(text):
    t = KEEPNEG.sub(" ", text)
    return bool(NEGW.search(t))


if __name__ == "__main__":
    T = [("speaks 40 languages and never misses a beat", ("quantity", 40, "language")),
         ("we do not offer 99.9% uptime", None), ("over 10,000 customers", ("quantity", 10000, "customer")),
         ("€49,99 a month", ("money", 49.99, "EUR")), ("about 10,000 customers", None), ("10-20 GB", None),
         ("12 March 2026", ("date", "2026-03-12")), ("Hooly Gemini 2.2", ("version", "2.2")), ("1.500 mAh", None),
         ("a 6.1\" display", ("quantity", 6.1, "inch")), ("answers in under a second", ("duration", 1, "s")),
         ("1,000 requests a day", ("quantity", 1000, "request")), ("a twelve month trial", None)]
    for t, exp in T:
        r = extract(t)
        print(t, "->", [c["v"] for c in r])
