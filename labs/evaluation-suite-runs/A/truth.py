"""Deterministic timeline truth engine over the shared forms format. Reads public/ only.

Engines:
  interval  anchors with an interval give known values over [start, end); point anchors
            (interval null) give evidence at their row date only. No known value at the
            target date -> unknown -> unsure.
  point     ablation: ignore intervals, every true anchor is a point fact at its row date;
            value at d = latest true anchor value at or before d, else earliest after.
  point-jitter  like point, but an interval anchor is dated on a fixed pseudo-random day
            inside its stated interval (suite anchors sit exactly on change points; real
            point statements do not).
Row label: any false atom -> false; else any unknown atom -> unsure; else true.

Usage: python -I truth.py --world dev --forms forms.jsonl --out preds.csv [--engine point]
"""
import argparse
import bisect
import csv
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suite  # noqa: E402

# ---------------------------------------------------------------- value canonicalisation
F = Fraction
DATA_U = {"b": 1, "byte": 1, "kb": 10**3, "kilobyte": 10**3, "mb": 10**6, "megabyte": 10**6,
          "gb": 10**9, "gig": 10**9, "gigabyte": 10**9, "tb": 10**12, "terabyte": 10**12}
LEN_U = {"mm": F(1, 1000), "millimetre": F(1, 1000), "millimeter": F(1, 1000), "cm": F(1, 100),
         "centimetre": F(1, 100), "centimeter": F(1, 100), "m": 1, "metre": 1, "meter": 1,
         "km": 1000, "kilometre": 1000, "kilometer": 1000, "in": F(254, 10000),
         "inch": F(254, 10000), '"': F(254, 10000), "″": F(254, 10000)}
MASS_U = {"g": 1, "gram": 1, "gramme": 1, "kg": 1000, "kilogram": 1000, "kilo": 1000}
FREQ_U = {"hz": 1, "hertz": 1, "khz": 10**3, "kilohertz": 10**3, "mhz": 10**6, "megahertz": 10**6,
          "ghz": 10**9, "gigahertz": 10**9}
POW_U = {"mw": F(1, 1000), "milliwatt": F(1, 1000), "w": 1, "watt": 1, "kw": 1000, "kilowatt": 1000}
BATT_U = {"mah": 1}
DIMS = (("data", DATA_U), ("length", LEN_U), ("mass", MASS_U), ("freq", FREQ_U), ("power", POW_U),
        ("charge", BATT_U))
FIXED_T = {"ms": F(1, 1000), "millisecond": F(1, 1000), "s": 1, "sec": 1, "second": 1, "min": 60,
           "minute": 60, "h": 3600, "hr": 3600, "hour": 3600, "d": 86400, "day": 86400,
           "week": 604800, "wk": 604800, "fortnight": 1209600}
CAL_T = {"month": 1, "mo": 1, "mth": 1, "year": 12, "yr": 12, "decade": 120}
CURRENCY = {"€": "EUR", "$": "USD", "£": "GBP", "us$": "USD", "euro": "EUR", "dollar": "USD", "lei": "RON"}
PER = {"month": "month", "mo": "month", "monthly": "month", "year": "year", "yr": "year",
       "annum": "year", "annually": "year", "yearly": "year", "annual": "year", "week": "week",
       "weekly": "week", "day": "day", "daily": "day", "": "once", "once": "once", "one-off": "once",
       "none": "once"}
IRREGULAR = {"people": "person", "children": "child", "men": "man", "women": "woman"}


def singular(w):
    w = w.strip().lower()
    if w in IRREGULAR:
        return IRREGULAR[w]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith(("ches", "shes", "sses", "xes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def num(v):
    if isinstance(v, bool):
        raise ValueError("bool is not a number")
    if isinstance(v, (int, float)):
        return F(repr(v)) if isinstance(v, float) else F(v)
    return F(str(v).replace(",", "").strip())


def day_range(s):
    """Partial ISO date -> half-open ordinal day range."""
    s = str(s).strip()
    p = [int(x) for x in s.split("-")]
    if len(p) == 1:
        return date(p[0], 1, 1).toordinal(), date(p[0] + 1, 1, 1).toordinal()
    if len(p) == 2:
        nxt = date(p[0] + (p[1] == 12), p[1] % 12 + 1, 1)
        return date(p[0], p[1], 1).toordinal(), nxt.toordinal()
    d = date(p[0], p[1], p[2]).toordinal()
    return d, d + 1


def name_key(s):
    return re.sub(r"\s+", "", str(s).lower())


def canon(v, names):
    """Typed value -> (cls, x). cls must match to compare; x is a Fraction, tuple or range.
    Raises on malformed values (caller treats the atom as unknown)."""
    kind = v.get("kind")
    unit = str(v.get("unit") or "").strip()
    ul = unit.lower()
    if kind == "quantity" and singular(ul) in {**FIXED_T, **CAL_T} and ul not in ("m", "in", "min"):
        kind = "duration"  # extractor put a time unit on a quantity
    if kind == "quantity":
        for dim, table in DIMS:
            key = ul if ul in table else singular(ul)
            if key in table and not (dim == "data" and unit == "b"):  # 'b' alone is not a byte
                return ("q:" + dim, num(v["value"]) * table[key])
        return ("q:#" + singular(ul), num(v["value"]))
    if kind == "duration":
        key = ul if ul in FIXED_T or ul in CAL_T else singular(ul)
        if key in FIXED_T:
            return ("dur:fixed", num(v["value"]) * FIXED_T[key])
        if key in CAL_T:
            return ("dur:cal", num(v["value"]) * CAL_T[key])
        raise ValueError(f"duration unit {unit!r}")
    if kind == "money":
        cur = str(v.get("currency") or "").strip()
        cur = CURRENCY.get(cur.lower(), cur.upper())
        per = PER.get(str(v.get("per") or "").strip().lower().lstrip("/"), str(v.get("per")).lower())
        return (f"money:{cur}:{per}", num(v["value"]))
    if kind == "percent":
        return ("percent", num(v["value"]))
    if kind == "date":
        return ("date", day_range(v["value"]))
    if kind == "version":
        s = re.sub(r"^(v|ver\.?|version)\s*", "", str(v["value"]).strip(), flags=re.I)
        try:
            parts = tuple(int(x) for x in s.split("."))
        except ValueError:
            return ("version:raw", s)
        return ("version", parts + (0,) * (4 - len(parts)))
    if kind == "name":
        k = name_key(v["value"])
        return ("name", names.get(k, k))
    if kind == "boolean":
        b = v["value"]
        if isinstance(b, str):
            b = {"true": True, "yes": True, "false": False, "no": False}[b.strip().lower()]
        return ("bool", bool(b))
    raise ValueError(f"kind {kind!r}")


def same_family(c1, c2):
    """Same value kind but different class (unit dimension, money period/currency,
    fixed vs calendar duration): the stated value differs from the declared one."""
    return c1.split(":")[0] == c2.split(":")[0]


SET = {"eq": lambda s1, s2: (s1, s2), "gt": lambda s1, s2: (s2, math.inf),
       "lt": lambda s1, s2: (-math.inf, s1), "ge": lambda s1, s2: (s1, math.inf),
       "le": lambda s1, s2: (-math.inf, s2)}


def compare(known, stated, op):
    """-> 'true' | 'false' | 'unknown' for stated (with op) against known."""
    (kc, kx), (sc, sx) = known, stated
    op = (op or "eq").lower()
    if kc != sc:
        return "false" if same_family(kc, sc) and op == "eq" else "unknown"
    if op not in SET:
        return "unknown"
    if kc == "date":  # partial dates are day sets; claim holds iff every known day satisfies
        p1, p2 = SET[op](*sx)
        k1, k2 = kx
        if p1 <= k1 and k2 <= p2:
            return "true"
        return "false" if k2 <= p1 or k1 >= p2 else "unknown"
    if op == "eq":
        return "true" if kx == sx else "false"
    if kc in ("bool", "name", "version:raw"):
        return "unknown"
    ok = {"gt": kx > sx, "lt": kx < sx, "ge": kx >= sx, "le": kx <= sx}.get(op)
    return "unknown" if ok is None else ("true" if ok else "false")


# ---------------------------------------------------------------- evidence
def alias_map(lexicon):
    m = {}
    for s in lexicon.get("subjects", []):
        for n in [s["name"], *s.get("aliases", [])]:
            m.setdefault(name_key(n), s["name"])
    for e in lexicon.get("events", []):
        m.setdefault(name_key(e), e)
    return m


def slot_key(a, subjects):
    subj = subjects.get(name_key(a.get("subject", "")), str(a.get("subject", "")).strip())
    attr = re.sub(r"[\s-]+", "_", str(a.get("attribute", "")).strip().lower())
    return subj, attr


def ordinal(s):
    y, m, d = (int(x) for x in str(s)[:10].split("-"))
    return date(y, m, d).toordinal()


def parse_interval(iv):
    if not iv or len(iv) != 2:
        return None
    try:
        return ordinal(iv[0]), ordinal(iv[1])
    except (ValueError, TypeError):
        return None


def atoms(rec, subjects, names):
    """[(slot, canon|None, op, conf)] for a forms record."""
    out = []
    for a in rec.get("assertions") or []:
        if not isinstance(a, dict):
            continue
        v = a.get("value") if isinstance(a.get("value"), dict) else {}
        try:
            c = canon(v, names)
        except (ValueError, KeyError, TypeError, ZeroDivisionError, ArithmeticError):
            c = None
        out.append((slot_key(a, subjects), c, v.get("op"), conf_of(a)))
    return out


def conf_of(d):
    """Optional extractor confidence in [0, 1]; missing or malformed -> 1.0."""
    try:
        return min(max(float(d.get("conf")), 0.0), 1.0) if d.get("conf") is not None else 1.0
    except (TypeError, ValueError):
        return 1.0


def majority(vals):
    """Most common canonical value; tie -> latest-listed. -> (value, n_distinct)."""
    cnt = Counter(vals)
    best = max(cnt.values())
    for v in reversed(vals):
        if cnt[v] == best:
            return v, len(cnt)


class Evidence:
    def __init__(self, engine):
        self.engine = engine
        self.iv = defaultdict(list)      # slot -> [(start, end, value)]
        self.pt = defaultdict(lambda: defaultdict(list))  # slot -> day -> [value]
        self.neg = defaultdict(set)      # (slot, day) -> {value} stated false by a 1-atom anchor
        self.days = {}                   # slot -> sorted days (point engine)

    def add(self, label, day, interval, ats):
        if label == "true":
            for slot, c, op, _ in ats:
                if c is None or (op or "eq") != "eq":
                    continue
                if self.engine == "interval" and interval:
                    self.iv[slot].append((interval[0], interval[1], c))
                else:
                    self.pt[slot][day].append(c)
        elif label == "false" and len(ats) == 1 and ats[0][1] is not None and (ats[0][2] or "eq") == "eq":
            if not interval or self.engine == "point":
                self.neg[(ats[0][0], day)].add(ats[0][1])

    def finish(self):
        self.days = {s: sorted(d) for s, d in self.pt.items()}

    def value_at(self, slot, day):
        """-> (value|None, strength in [0,1], conflict)."""
        if self.engine == "interval":
            cover = [c for s, e, c in self.iv.get(slot, ()) if s <= day < e]
            if cover:
                v, nd = majority(cover)
                return v, 0.995, nd > 1
            here = self.pt.get(slot, {}).get(day)
            if here:
                v, nd = majority(here)
                return v, 0.97, nd > 1
            return None, 0.0, False
        days = self.days.get(slot)
        if not days:
            return None, 0.0, False
        i = bisect.bisect_right(days, day)
        d = days[i - 1] if i else days[0]
        v, nd = majority(self.pt[slot][d])
        gap = abs(day - d)
        return v, 0.6 + 0.39 * math.exp(-gap / 120.0), nd > 1


# ---------------------------------------------------------------- prediction
def predict(world, forms_path, engine="interval"):
    """-> list of (id, label, confidence|None) for the world's hidden targets."""
    universe = suite.read_universe(world)
    lex = suite.read_lexicon(world)
    subjects = alias_map(lex)
    names = subjects  # name values resolve through the same published spellings
    forms = {}
    for rec in suite.read_jsonl(forms_path):
        forms.setdefault(str(rec.get("id")), rec)  # first record per id wins
    ev = Evidence("point" if engine == "point-jitter" else engine)
    for r in universe:
        if r["label"] and r["id"] in forms:
            rec = forms[r["id"]]
            iv, day = parse_interval(rec.get("interval")), ordinal(r["date"])
            if engine == "point-jitter" and iv and iv[1] > iv[0]:
                # ablation: the anchor is a point statement on a fixed pseudo-random day of its interval
                day = iv[0] + int(hashlib.sha1(r["id"].encode()).hexdigest(), 16) % (iv[1] - iv[0])
            ev.add(r["label"].strip().lower(), day, iv, atoms(rec, subjects, names))
    ev.finish()
    out = []
    for r in universe:
        if r["label"]:
            continue
        rec = forms.get(r["id"])
        ats = atoms(rec, subjects, names) if rec else []
        if not ats:
            out.append((r["id"], "unsure", None))
            continue
        day = ordinal(r["date"])
        verdicts = []
        for slot, c, op, aconf in ats:
            if c is None:
                verdicts.append(("unknown", 0.0))
                continue
            known, strength, conflict = ev.value_at(slot, day)
            if known is None:
                verdict = "false" if (op or "eq") == "eq" and c in ev.neg.get((slot, day), ()) else "unknown"
                verdicts.append((verdict, 0.9 * aconf))
                continue
            verdicts.append((compare(known, c, op), strength * (0.7 if conflict else 1.0) * aconf))
        rconf = conf_of(rec)
        falses = [p for v, p in verdicts if v == "false"]
        if falses:
            out.append((r["id"], "false", round(max(falses) * rconf, 4)))
        elif any(v == "unknown" for v, _ in verdicts):
            out.append((r["id"], "unsure", None))
        else:
            out.append((r["id"], "true", round(math.prod(p for _, p in verdicts) * rconf, 4)))
    return out


def write_preds(rows, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "label", "confidence"])
        for rid, lab, conf in rows:
            w.writerow([rid, lab, "" if conf is None else conf])


def _selfcheck():
    n = {}
    q = lambda v, u, op=None: {"kind": "quantity", "value": v, "unit": u, **({"op": op} if op else {})}
    assert compare(canon(q(1, "GB"), n), canon(q(1000, "MB"), n), None) == "true"
    assert compare(canon(q(130, "GB"), n), canon(q(120, "GB"), n), "gt") == "true"
    assert compare(canon(q(40, "language"), n), canon(q(40, "languages"), n), None) == "true"
    d = lambda v, op=None: {"kind": "date", "value": v, **({"op": op} if op else {})}
    assert compare(canon(d("2025-05-15"), n), canon(d("2025-05-15"), n), "gt") == "false"
    assert compare(canon(d("2025-03-12"), n), canon(d("2025-03"), n), None) == "true"
    assert compare(canon(d("2025-03"), n), canon(d("2025-03-12"), n), None) == "unknown"
    assert compare(canon(d("2026-01-05"), n), canon(d("2025"), n), "gt") == "true"
    t = lambda v, u: {"kind": "duration", "value": v, "unit": u}
    assert compare(canon(t(2, "week"), n), canon(t(14, "days"), n), None) == "true"
    assert compare(canon(t(1, "year"), n), canon(t(12, "months"), n), None) == "true"
    assert compare(canon(t(1, "month"), n), canon(t(30, "days"), n), None) == "false"
    v = lambda s, op=None: {"kind": "version", "value": s, **({"op": op} if op else {})}
    assert compare(canon(v("2.3"), n), canon(v("2.3.0"), n), None) == "true"
    assert compare(canon(v("0.12.3"), n), canon(v("0.11.6"), n), "ge") == "true"
    assert compare(canon(v("8.10.0"), n), canon(v("8.6.4"), n), "gt") == "true"
    m = lambda x, per=None: {"kind": "money", "value": x, "currency": "EUR", **({"per": per} if per else {})}
    assert compare(canon(m(49, "month"), n), canon(m(49), n), None) == "false"
    assert compare(canon(m(49.99, "month"), n), canon(m("49.99", "monthly"), n), None) == "true"
    assert compare(canon({"kind": "percent", "value": 0.1 + 0.2}, n),
                   canon({"kind": "percent", "value": 0.30000000000000004}, n), None) == "true"
    print("selfcheck ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--world", choices=sorted(suite.WORLDS))
    ap.add_argument("--forms")
    ap.add_argument("--out")
    ap.add_argument("--engine", choices=("interval", "point", "point-jitter"), default="interval")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return _selfcheck()
    if not (a.world and a.forms and a.out):
        ap.error("--world, --forms and --out are required")
    write_preds(predict(a.world, a.forms, a.engine), a.out)


if __name__ == "__main__":
    main()
