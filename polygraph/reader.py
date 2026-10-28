"""Stage 1: the value parser, a clone of the referee's contracts/value-forms.md.

It does two jobs:
- reads the values in every input sentence (for labelling), and
- reads our own claim texts back (validate.py), so a claim the referee would not read
  never ships.

parse_values(text, skip) returns every value the text states, in reading order. Booleans
and names are not read here: a yes/no depends on the attribute's words, and a name on the
lexicon, so the attributor reads those.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .model import ValueSpan

IMPLEMENTED = True

# ---- words --------------------------------------------------------------------------------
MONTH_NUM = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
             "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
MONTH = (r"(?P<mon>January|February|March|April|May|June|July|August|September|October|November|December"
         r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?")

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
        "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
WORD_NUM = {w: i for i, w in enumerate(ONES)} | {w: 20 + 10 * i for i, w in enumerate(TENS)}
WORD_NUM_RE = re.compile(
    r"(?<![A-Za-z-])(?:(?P<h>a|one|two|three|four|five|six|seven|eight|nine)\s+hundred"
    r"|(?P<dozen>a\s+dozen)"
    r"|(?P<tens>" + "|".join(TENS) + r")(?:[-\s](?P<tu>one|two|three|four|five|six|seven|eight|nine))?"
    r"|(?P<ones>" + "|".join(ONES) + r"))(?![A-Za-z])", re.I)

DIGIT_RE = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*")

NEGATION_RE = re.compile(r"\b(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|\w+n[’']t\b", re.I)
NEG_EXEMPT_RE = re.compile(r"\b(?:no|not)\s+(?:more|less|fewer|later|earlier)\s+than\b", re.I)
CLAUSE_END_RE = re.compile(r"[,;:!?•·|]|\.(?=\s|$)|\n\s*\n")

APPROX_BEFORE_RE = re.compile(r"(?:\b(?:about|around|approximately|approx\.?|roughly|nearly|almost|circa|ca\.?"
                              r"|some|estimated|est\.?|close\s+to|more\s+or\s+less)|[~≈±])\s*$", re.I)
APPROX_AFTER_RE = re.compile(r"^(?:\s*(?:or\s+so|give\s+or\s+take)\b|-ish\b)", re.I)

OP_BEFORE = [
    ("le", r"no more than|not more than|up to|at most|maximum|max"),
    ("ge", r"no less than|not less than|no fewer than|at least|minimum"),
    ("gt", r"more than|greater than|higher than|in excess of|upwards of|exceeding|over|above"),
    ("lt", r"less than|fewer than|lower than|under|below"),
]
OP_BEFORE_RE = [(op, re.compile(r"\b(?:" + words + r")\s*$", re.I)) for op, words in OP_BEFORE]
WITHIN_RE = re.compile(r"\bwithin\s*$", re.I)
DATE_OP_BEFORE = [("le", r"no later than|by"), ("ge", r"no earlier than"), ("lt", r"before|prior to"), ("gt", r"after")]
DATE_OP_RE = [(op, re.compile(r"\b(?:" + w + r")\s*$", re.I)) for op, w in DATE_OP_BEFORE]
OP_AFTER_RE = re.compile(r"^\s*or\s+(?P<w>less|fewer|under|below|lower|shorter|more|higher|above|longer|over)\b", re.I)

SCALE_RE = re.compile(r"^\s*(?:(?P<w>(?i:thousand|million|billion))\b|(?P<bn>(?i:bn))\b|(?P<M>M)(?![A-Za-z])|(?P<k>k)(?![A-Za-z]))")
SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9}

PERCENT_RE = re.compile(r"^\s*(?:%|percent\b|per\s+cent\b)", re.I)
ISO = "EUR|USD|GBP|CHF|RON|PLN|CZK|HUF|SEK|NOK|DKK|JPY|CNY|INR|CAD|AUD"
CUR_BEFORE_RE = re.compile(r"(?:(?P<sym>US\$|[€$£])|\b(?P<iso>" + ISO + r"))\s*$")
CUR_AFTER_RE = re.compile(r"^\s*(?:(?P<iso>" + ISO + r")\b|(?P<word>euros?|dollars?|lei)\b)", re.I)
SYMBOL_CUR = {"€": "EUR", "$": "USD", "£": "GBP", "US$": "USD"}
WORD_CUR = {"euro": "EUR", "euros": "EUR", "dollar": "USD", "dollars": "USD", "lei": "RON"}
PERIOD_RE = re.compile(
    r"^\s*(?:(?:per\s+(?!month|day|week|year|annum)[A-Za-z]+|/\s*seat|/\s*user)\s*)?"
    r"(?:/\s*(?P<slash>month|mo|day|week|year|yr)\b|(?:a|per|each|every)\s+(?P<per>month|day|week|year|annum)\b"
    r"|(?P<adv>monthly|daily|weekly|yearly|annually))", re.I)
PERIOD = {"mo": "month", "yr": "year", "annum": "year", "annually": "year", "monthly": "month",
          "daily": "day", "weekly": "week", "yearly": "year"}

DURATION_RE = re.compile(
    r"^(?:\s*|-)(?:(?P<ci>milliseconds?|ms|secs?|seconds?|mins?|minutes?|hrs?|hours?|days?|weeks?|wks?"
    r"|fortnights?|months?|mths?|mo|years?|yrs?|decades?)|(?P<cs>[shd]))(?![A-Za-z])", re.I)
DURATION_UNIT = {"millisecond": "ms", "ms": "ms", "sec": "s", "second": "s", "s": "s", "min": "min",
                 "minute": "min", "hr": "h", "hour": "h", "h": "h", "day": "day", "d": "day", "week": "week",
                 "wk": "week", "fortnight": "week", "month": "month", "mth": "month", "mo": "month",
                 "year": "year", "yr": "year", "decade": "year"}
A_DURATION_RE = re.compile(
    r"\b(?:under|within|in|for|over|than|at\s+least|at\s+most|to|only|just)\s+(?P<a>an?)\s+"
    r"(?P<u>millisecond|second|minute|hour|day|week|fortnight|month|year|decade)(?![A-Za-z])", re.I)

UNIT_SYMBOL_RE = re.compile(r"^(?:\s*|-)(?P<u>mAh|kHz|MHz|GHz|Hz|kW|mW|W|KB|kB|kb|MB|mb|GB|gb|TB|tb|B|mm|cm|km|kg|g|m)(?![A-Za-z0-9])")
UNIT_IN_RE = re.compile(r"^(?:in(?=[^A-Za-z]|$)|\s*in(?=[.,;:!?]|$)|\s*[\"″])")
UNIT_WORD_RE = re.compile(
    r"^(?:\s*|-)(?P<u>bytes?|kilobytes?|megabytes?|gigabytes?|gigs?|terabytes?|millimet(?:re|er)s?|centimet(?:re|er)s?"
    r"|kilomet(?:re|er)s?|met(?:re|er)s?|inch(?:es)?|grammes?|grams?|kilograms?|kilos?|kilohertz|megahertz|gigahertz"
    r"|hertz|milliwatts?|kilowatts?|watts?)(?![A-Za-z])", re.I)
UNIT_SYMBOL = {"kb": "KB", "mb": "MB", "gb": "GB", "tb": "TB", "kB": "KB"}
UNIT_WORD = [("kilobyte", "KB"), ("megabyte", "MB"), ("gigabyte", "GB"), ("gig", "GB"), ("terabyte", "TB"),
             ("byte", "B"), ("millimet", "mm"), ("centimet", "cm"), ("kilomet", "km"), ("met", "m"), ("inch", "in"),
             ("kilogram", "kg"), ("kilo", "kg"), ("gram", "g"), ("kilohertz", "kHz"), ("megahertz", "MHz"),
             ("gigahertz", "GHz"), ("hertz", "Hz"), ("milliwatt", "mW"), ("kilowatt", "kW"), ("watt", "W")]

NOUN_WORDS_RE = re.compile(r"^\s*-?([A-Za-z][A-Za-z'’-]*)(?:\s+([A-Za-z][A-Za-z'’-]*))?(?:\s+([A-Za-z][A-Za-z'’-]*))?")
STOP = {"of", "our", "the", "a", "an", "and", "or", "in", "at", "to", "per", "than", "is", "are", "was", "were",
        "has", "have", "had", "for", "on", "with", "its", "their", "his", "her", "my", "your", "this", "that",
        "these", "those", "by", "from", "as", "it", "be", "been", "will", "so", "far", "now", "today", "each",
        "every", "more", "most", "less", "all", "into", "across", "out", "up", "off", "after", "before", "since",
        "until", "who", "which", "while", "when", "where", "what", "we", "they", "you", "he", "she", "i", "but",
        "not", "no", "never", "also", "only", "just", "still", "already", "about", "over", "under", "times"}
IRREGULAR_SINGULAR = {"people": "person", "children": "child", "men": "man", "women": "woman", "feet": "foot",
                      "indices": "index", "series": "series", "news": "news"}


@lru_cache(maxsize=100_000)
def singular(word: str) -> str:
    w = word.lower().replace("’", "'")
    if w in IRREGULAR_SINGULAR:
        return IRREGULAR_SINGULAR[w]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if re.search(r"(ches|shes|sses|xes|zzes)$", w):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 2:
        return w[:-1]
    return w


# ---- helpers ------------------------------------------------------------------------------
def _clean(x: float):
    x = round(x, 9)
    return int(x) if float(x).is_integer() else x


def _parse_digits(s: str) -> tuple[float | None, str]:
    """(number, restriction): restriction is "" (reads anywhere), "price" (decimal comma)
    or "percent" (three decimals). None when the number reads as nothing."""
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", s):
        return float(s.replace(",", "")), ""
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        if "." in s and len(s.split(".")[1]) == 3:
            return float(s), "percent"
        return float(s), ""
    if re.fullmatch(r"\d+,\d{2}", s):
        return float(s.replace(",", ".")), "price"
    return None, ""


def _negated(text: str, start: int) -> bool:
    clause_start = 0
    for m in CLAUSE_END_RE.finditer(text, 0, start):
        clause_start = m.end()
    clause = NEG_EXEMPT_RE.sub(" ", text[clause_start:start])
    return bool(NEGATION_RE.search(clause))


def _mask(text: str, skip) -> str:
    if not skip:
        return text
    chars = list(text)
    for a, b in skip:
        for i in range(max(0, a), min(len(chars), b)):
            if not chars[i].isspace():
                chars[i] = "N"
    return "".join(chars)


def _op_before(prefix: str) -> str | None:
    for op, rx in OP_BEFORE_RE:
        if rx.search(prefix):
            return op
    return None


# ---- dates --------------------------------------------------------------------------------
DATE_RES = [
    re.compile(r"(?<![\d-])(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})(?![\d-])"),
    re.compile(r"(?<![\d-])(?P<y>\d{4})-(?P<m>\d{2})(?![\d-])"),
    re.compile(r"(?<![\w])(?:the\s+)?(?P<d>\d{1,2})(?:st|nd|rd|th)?(?:\s+of)?\s*" + MONTH + r",?\s+(?P<y>\d{4})(?![\d])", re.I),
    re.compile(r"(?<![\w])" + MONTH + r"\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>\d{4})(?![\d])", re.I),
    re.compile(r"(?<![\w])" + MONTH + r",?\s+(?P<y>\d{4})(?![\d])", re.I),
]


def _dates(text: str, taken: list) -> list[ValueSpan]:
    out = []
    for rx in DATE_RES:
        for m in rx.finditer(text):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            y = int(m.group("y"))
            if "mon" in rx.groupindex and m.group("mon"):
                mo = MONTH_NUM[m.group("mon").lower().rstrip(".")[:4] if m.group("mon").lower().startswith("sept") else m.group("mon").lower()[:3]]
            elif "m" in rx.groupindex and m.group("m"):
                mo = int(m.group("m"))
            else:
                mo = None
            d = int(m.group("d")) if "d" in rx.groupindex and m.group("d") else None
            if mo is not None and not 1 <= mo <= 12 or d is not None and not 1 <= d <= 31:
                continue
            val = f"{y:04d}" + (f"-{mo:02d}" if mo else "") + (f"-{d:02d}" if d else "")
            out.append(ValueSpan(_with_date_op({"kind": "date", "value": val}, text[:m.start()]), m.start(), m.end()))
            taken.append((m.start(), m.end()))
    return out


def _with_date_op(v: dict, prefix: str) -> dict:
    for op, rx in DATE_OP_RE:
        if rx.search(prefix):
            v["op"] = op
            break
    return v


# ---- versions -----------------------------------------------------------------------------
VERSION_RES = [
    re.compile(r"(?<![A-Za-z])(?:v\s?|version\s+|ver\.?\s*)(?P<v>\d+(?:\.\d+)*)(?![\d.]\d)", re.I),
    re.compile(r"(?<![\w.])(?P<v>\d+\.\d+\.\d+(?:\.\d+)*)(?![\w.]\w)"),
    re.compile(r"(?<![\w])[A-Z][A-Za-z0-9/&'’-]*\s(?P<v>\d+\.\d+)(?![\d.,]?\d|\s*(?:%|percent|per\s+cent))"),
]


def _versions(text: str, taken: list) -> list[ValueSpan]:
    out = []
    for i, rx in enumerate(VERSION_RES):
        for m in rx.finditer(text):
            a, b = m.start("v") if i == 2 else m.start(), m.end()
            if any(x < b and a < y for x, y in taken):
                continue
            vs = ValueSpan({"kind": "version", "value": m.group("v")}, a, b)
            if i == 2:
                # "Hooly Pixel Fold 4.1 stars" may also be a count: keep it as another reading
                n, _ = _parse_digits(m.group("v"))
                q = _read_number(text, (a, b, n, "", True, m.group("v")))
                if q is not None and q.value["kind"] != "date":
                    vs.alts = [q.value, *q.alts]
            out.append(vs)
            taken.append((a, b))
    return out


# ---- numbers ------------------------------------------------------------------------------
def _number_tokens(text: str, taken: list):
    """(start, end, number, restriction, from_digits) for every number not inside a date/version."""
    toks = []
    for m in DIGIT_RE.finditer(text):
        if any(a < m.end() and m.start() < b for a, b in taken):
            continue
        n, restr = _parse_digits(m.group(0))
        toks.append((m.start(), m.end(), n, restr, True, m.group(0)))
    for m in WORD_NUM_RE.finditer(text):
        if any(a < m.end() and m.start() < b for a, b in taken):
            continue
        g = m.groupdict()
        if g["h"]:
            n = 100 * (1 if g["h"].lower() == "a" else WORD_NUM[g["h"].lower()])
        elif g["dozen"]:
            n = 12
        elif g["tens"]:
            n = WORD_NUM[g["tens"].lower()] + (WORD_NUM[g["tu"].lower()] if g["tu"] else 0)
        else:
            n = WORD_NUM[g["ones"].lower()]
        toks.append((m.start(), m.end(), float(n), "", False, m.group(0)))
    toks.sort()
    return toks


def _read_number(text: str, tok) -> ValueSpan | None:
    start, end, n, restr, digits, raw = tok
    if n is None:
        return None
    rest = text[end:]
    before = text[:start]
    alts = []
    # a scale: 1.2 million, 10k, 1M, €1.2bn
    sm = SCALE_RE.match(rest)
    if sm and (digits or sm.group("w")):
        n *= SCALE[sm.group("w").lower()] if sm.group("w") else 1e9 if sm.group("bn") else 1e6 if sm.group("M") else 1e3
        end += sm.end()
        rest = text[end:]
    plus = rest.startswith("+")
    if plus:
        end += 1
        rest = text[end:]
    value = None
    vstart = start
    # money
    cb = CUR_BEFORE_RE.search(before)
    ca = CUR_AFTER_RE.match(rest)
    if cb or ca:
        if cb:
            cur = SYMBOL_CUR[cb.group("sym")] if cb.group("sym") else cb.group("iso")
            vstart = cb.start()
        else:
            cur = ca.group("iso").upper() if ca.group("iso") else WORD_CUR[ca.group("word").lower()]
            end += ca.end()
            rest = text[end:]
        value = {"kind": "money", "value": _clean(n), "currency": cur}
        pm = PERIOD_RE.match(rest)
        if pm:
            p = (pm.group("slash") or pm.group("per") or pm.group("adv")).lower()
            value["per"] = PERIOD.get(p, p)
            end += pm.end()
    elif restr == "price":
        return None
    elif PERCENT_RE.match(rest):
        value = {"kind": "percent", "value": _clean(n)}
        end += PERCENT_RE.match(rest).end()
    elif restr == "percent":
        return None
    else:
        dm = DURATION_RE.match(rest)
        um = UNIT_SYMBOL_RE.match(rest) if digits else None
        uw = UNIT_WORD_RE.match(rest)
        ui = UNIT_IN_RE.match(rest) if digits else None
        if dm:
            word = (dm.group("ci") or dm.group("cs")).lower()
            base = re.sub(r"s$", "", word) if word not in ("s", "ms") else word
            unit = DURATION_UNIT.get(base, DURATION_UNIT.get(word))
            mult = 2 if base.startswith("fortnight") else 10 if base.startswith("decade") else 1
            value = {"kind": "duration", "value": _clean(n * mult), "unit": unit}
            end += dm.end()
        elif um:
            u = um.group("u")
            value = {"kind": "quantity", "value": _clean(n), "unit": UNIT_SYMBOL.get(u, u)}
            end += um.end()
        elif uw:
            w = uw.group("u").lower()
            unit = next(u for prefix, u in UNIT_WORD if w.startswith(prefix))
            value = {"kind": "quantity", "value": _clean(n), "unit": unit}
            end += uw.end()
        elif ui:
            value = {"kind": "quantity", "value": _clean(n), "unit": "in"}
            end += ui.end()
        else:
            # a plain four-digit number from 1900 to 2099 is a year, never a count
            if digits and re.fullmatch(r"(?:19|20)\d\d", raw):
                if re.search(r"(?:\b[QH][1-4]|[/.]\d{1,2}[/.]?)\s*$", before):
                    return None
                return ValueSpan(_with_date_op({"kind": "date", "value": raw}, before), start, end)
            nm = NOUN_WORDS_RE.match(rest)
            if not nm:
                return None
            words = [w for w in nm.groups() if w]
            # the sentence may end inside the window: only words before any punctuation count
            span_text = rest[: nm.end()]
            cut = re.search(r"[.,;:!?]", span_text)
            if cut:
                words = [w for w in words if rest.find(w) < cut.start()]
            if not words:
                return None
            nouns = [singular(w) for w in words if w.lower() not in STOP]
            if not nouns:
                return None
            plural_first = next((singular(w) for w in words if w.lower() not in STOP and re.search(r"[^s]s$|people$", w.lower())), None)
            noun = plural_first or nouns[0]
            value = {"kind": "quantity", "value": _clean(n), "unit": noun}
            alts = [{"kind": "quantity", "value": _clean(n), "unit": u} for u in dict.fromkeys(nouns) if u != noun]
            end = end + len(rest[: rest.find(words[0]) + len(words[0])]) if words else end
    # comparison words
    op = _op_before(text[:vstart])
    if value["kind"] == "duration" and op is None and WITHIN_RE.search(text[:vstart]):
        op = "le"
    oa = OP_AFTER_RE.match(text[end:])
    if oa:
        w = oa.group("w").lower()
        op = "le" if w in ("less", "fewer", "under", "below", "lower", "shorter") else "ge"
    if plus:
        op = "ge"
    if op:
        value["op"] = op
        for a in alts:
            a["op"] = op
    return ValueSpan(value, vstart, end, alts=alts)


def _a_durations(text: str, taken: list) -> list[ValueSpan]:
    out = []
    for m in A_DURATION_RE.finditer(text):
        if any(a < m.end() and m.start("a") < b for a, b in taken):
            continue
        u = m.group("u").lower()
        mult = 2 if u == "fortnight" else 10 if u == "decade" else 1
        value = {"kind": "duration", "value": mult, "unit": DURATION_UNIT[u]}
        prefix = text[: m.start("a")]
        op = _op_before(prefix)
        if op is None and WITHIN_RE.search(prefix):
            op = "le"
        if op:
            value["op"] = op
        out.append(ValueSpan(value, m.start("a"), m.end()))
    return out


# ---- the parser ---------------------------------------------------------------------------
def parse_values(text: str, skip: list[tuple[int, int]] | tuple = ()) -> list[ValueSpan]:
    """Every value the text states, in reading order, each with its span.

    skip: spans to ignore (the names of subjects: a value written inside a name, like the
    2026 of `Hooly I/O 2026`, states nothing).

    A value reads as value-forms.md says: whole, with its comparison words (as `op`) and its
    unit. Approximations, range ends and ambiguous numbers read as nothing. A value after a
    negation in its clause comes back with negated=True (the referee ignores it).
    """
    t = _mask(text, skip)
    taken: list[tuple[int, int]] = []
    out: list[ValueSpan] = []
    out += _dates(t, taken)
    out += _versions(t, taken)
    toks = _number_tokens(t, taken)
    read = []
    for tok in toks:
        vs = _read_number(t, tok)
        read.append((tok, vs))
    # ranges and approximations
    drop = set()
    for i, (tok, vs) in enumerate(read):
        start, end = tok[0], tok[1]
        before = t[:start]
        if APPROX_BEFORE_RE.search(re.sub(r"(?:US\$|[€$£])\s*$", "", before)):
            drop.add(i)
        vend = vs.end if vs else end
        if APPROX_AFTER_RE.match(t[vend:]):
            drop.add(i)
        if re.search(r"\bbetween\s+(?:US\$|[€$£])?\s*$", before, re.I) and i + 1 < len(read):
            drop.update({i, i + 1})
        nxt = read[i + 1][0] if i + 1 < len(read) else None
        if nxt is not None:
            gap = t[vend:nxt[0]]
            gap_bare = t[end:nxt[0]]
            from_ctx = re.search(r"\bfrom\s+(?:US\$|[€$£])?\s*$", before, re.I)
            if re.fullmatch(r"\s*(?:-|–|—)\s*(?:US\$|[€$£])?\s*", gap) or (
                    re.fullmatch(r"\s*to\s+(?:US\$|[€$£])?\s*", gap) and not from_ctx):
                drop.update({i, i + 1})
            elif re.fullmatch(r"\s*or\s+", gap_bare) and (vs is None or vs.end == end or vs.value.get("kind") == "quantity" and vs.end == end):
                drop.update({i, i + 1})
            elif vs is not None and vs.end == end and re.fullmatch(r"\s*or\s+", gap_bare):
                drop.update({i, i + 1})
    for i, (tok, vs) in enumerate(read):
        if vs is not None and i not in drop and not any(a < vs.end and vs.start < b for a, b in taken):
            out.append(vs)
            taken.append((vs.start, vs.end))
    out += _a_durations(t, taken)
    for v in out:
        v.negated = _negated(t, v.start)
    out.sort(key=lambda v: v.start)
    return out


def sentences(text: str) -> list[tuple[int, int]]:
    """Spans of the sentences of a text: a sentence ends at . ! or ? before a space, or at a
    blank line; abbreviations (e.g., Inc., Dr., an initial, No. before a number) end nothing."""
    abbrev = re.compile(r"(?:\be\.g|\bi\.e|\bvs|\bapprox|\bInc|\bLtd|\bCo|\bCorp|\bDr|\bMr|\bMrs|\bMs|\bProf|\bSt|\b[A-Z])\.$")
    spans, start = [], 0
    for m in re.finditer(r"[.!?](?=\s)|\n\s*\n", text):
        if m.group(0) == "." and abbrev.search(text[start:m.end()]):
            continue
        if m.group(0) == "." and re.search(r"\bNo\.$", text[start:m.end()]) and re.match(r"\s*\d", text[m.end():]):
            continue
        spans.append((start, m.end()))
        start = m.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans
