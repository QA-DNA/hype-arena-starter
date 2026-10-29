#!/usr/bin/env python3
"""
Hooly new-claims generator (standalone port of the app's src/lib/claims.ts + tree.ts).

Builds exactly N (default 1,000) TRUE and NEW claims from the practice data,
following the starter contracts (claim-forms.md, value-forms.md, entry.schema.json).

Usage:
    python generate_claims.py --practice practice.json --lexicon lexicon.json \
        --out claims.csv [--rejected rejected.csv] [--target 1000]

Pipeline:
    1. Build the fact tree: subject -> attribute -> value segments (periods where one
       true value holds), each with its supporting observations (rows).
    2. Split each attribute into "slots" (e.g. monthly EUR price vs yearly price),
       flag unstable slots (value comes back, or two values start the same day).
    3. Build candidates for five claim types: fact, compare, change, at_event, relation.
    4. Score confidence from evidence; validate each text with referee-style rules;
       drop copies of practice rows and duplicates.
    5. Round-robin across types (best confidence first) until the target is reached.

Only the standard library is used.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import OrderedDict
from datetime import date as _date

AS_OF = "2026-10-29"
TYPES = ["fact", "compare", "change", "at_event", "relation"]
MIN_CONF = 0.7


# ---------------------------------------------------------------- helpers
def js_str(x) -> str:
    """String() as JavaScript would render it (true, 59, 1.5)."""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def format_value(v: dict) -> str:
    rest = [f"{k}={js_str(x)}" for k, x in v.items() if k not in ("kind", "value", "unit")]
    parts = [js_str(v.get("value")), v.get("unit") or "", f"({', '.join(rest)})" if rest else ""]
    return " ".join(p for p in parts if p)


def exact(v: dict) -> dict:
    return {k: x for k, x in v.items() if k != "op"}


def vkey(v: dict) -> str:
    return format_value(exact(v))


# ---------------------------------------------------------------- lexicon
class Lexicon:
    def __init__(self, raw: dict):
        self.subjects = raw["subjects"]
        self.events = raw["events"]
        self.alias = {}
        for s in self.subjects:
            self.alias[s["name"].lower()] = s["name"]
            for a in s["aliases"]:
                self.alias[a.lower()] = s["name"]
        self.names = {s["name"] for s in self.subjects}

    def resolve(self, name) -> str | None:
        return self.alias.get(str(name).strip().lower())


# ---------------------------------------------------------------- tree
DIM = {"b": "data", "kb": "data", "mb": "data", "gb": "data", "tb": "data", "mm": "len", "cm": "len", "m": "len",
       "km": "len", "in": "len", "g": "mass", "kg": "mass", "hz": "freq", "khz": "freq", "mhz": "freq", "ghz": "freq",
       "mw": "pow", "w": "pow", "kw": "pow"}


def slot_of(v: dict) -> str:
    k = v["kind"]
    if k == "money":
        per = v.get("per")
        return f"money:{js_str(v.get('currency'))}:{js_str(per) if per else 'once'}"
    if k == "quantity":
        u = str(v.get("unit") or "").lower()
        return f"q:{DIM.get(u, re.sub(r's$', '', u))}"
    if k == "duration":
        return f"d:{v.get('unit') if v.get('unit') in ('month', 'year') else 'time'}"
    return k


def same_value(a: dict, b: dict, lex: Lexicon) -> bool:
    if a["kind"] == "date" or b["kind"] == "date":
        x, y = js_str(a["value"]), js_str(b["value"])
        return x.startswith(y) or y.startswith(x)
    if a["kind"] == "name" and b["kind"] == "name":
        x, y = js_str(a["value"]), js_str(b["value"])
        rx, ry = lex.resolve(x) or x.lower(), lex.resolve(y) or y.lower()
        return rx == ry or x.lower().startswith(y.lower()) or y.lower().startswith(x.lower())
    return vkey(a) == vkey(b)


def build_tree(rows: list, lex: Lexicon) -> "OrderedDict[str, OrderedDict[str, dict]]":
    """subject -> attribute -> node {attribute, segments, falseValues, unsure, all}."""
    tree: OrderedDict = OrderedDict()
    for r in rows:
        for f in r["form"]:
            s = lex.resolve(f["subject"]) or f["subject"]
            attrs = tree.setdefault(s, OrderedDict())
            node = attrs.setdefault(f["attribute"], {"attribute": f["attribute"], "segments": [], "falseValues": [], "unsure": [], "all": []})
            node["all"].append({"rowId": r["id"], "date": r["date"], "label": r["label"], "value": vkey(f["value"]), "raw": f["value"], "text": r["text"]})
    for attrs in tree.values():
        for n in attrs.values():
            n["all"].sort(key=lambda o: o["date"])
            for o in n["all"]:
                if o["label"] == "false":
                    n["falseValues"].append(o)
                elif o["label"] == "unsure":
                    n["unsure"].append(o)
                elif not o["raw"].get("op"):
                    slot = slot_of(o["raw"])
                    same_slot = [x for x in n["segments"] if x["slot"] == slot]
                    last = same_slot[-1] if same_slot else None
                    if last and same_value(last["raw"], o["raw"], lex):
                        last["obs"].append(o)
                        if o["raw"]["kind"] == "date" and len(js_str(o["raw"]["value"])) > len(js_str(last["raw"]["value"])):
                            last["raw"], last["value"] = o["raw"], o["value"]
                    else:
                        if last:
                            last["to"] = o["date"]
                        n["segments"].append({"value": o["value"], "raw": o["raw"], "slot": slot, "from": o["date"], "to": None, "obs": [o]})
    return tree


# ---------------------------------------------------------------- value-forms.md writers
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£"}
UNIT_SYMBOLS = {"B", "KB", "MB", "GB", "TB", "mm", "cm", "m", "km", "in", "g", "kg", "mAh", "Hz", "kHz", "MHz", "GHz", "mW", "W", "kW"}
DUR = {"ms": ("ms", "ms"), "s": ("second", "seconds"), "min": ("minute", "minutes"), "h": ("hour", "hours"), "day": ("day", "days"),
       "week": ("week", "weeks"), "month": ("month", "months"), "year": ("year", "years")}


def num(n) -> str | None:
    if not isinstance(n, (int, float)) or isinstance(n, bool):
        return None
    s = f"{n:,.6f}".rstrip("0").rstrip(".")
    return None if re.search(r"\.\d{3}$", s) else s  # "1.500" is ambiguous to the referee


def plural(noun: str, n) -> str:
    if n == 1:
        return noun
    if noun == "person":
        return "people"
    if re.search(r"[^aeiou]y$", noun):
        return noun[:-1] + "ies"
    if re.search(r"(s|x|ch|sh)$", noun):
        return noun + "es"
    return noun + "s"


def write_value(v: dict) -> str | None:
    k, n = v["kind"], v.get("value")
    if k == "money":
        a = num(n)
        if a is None or n < 0:
            return None
        c = js_str(v.get("currency"))
        price = f"{SYMBOL[c]}{a}" if c in SYMBOL else f"{c} {a}"
        return f"{price} per {v['per']}" if v.get("per") else price
    if k == "quantity":
        a = num(n)
        if a is None or not v.get("unit"):
            return None
        return f"{a} {v['unit']}" if v["unit"] in UNIT_SYMBOLS else f"{a} {plural(v['unit'], n)}"
    if k == "duration":
        a, u = num(n), DUR.get(v.get("unit") or "")
        if a is None or not u:
            return None
        return f"{a} {u[0] if n == 1 else u[1]}"
    if k == "percent":
        a = num(n)
        return None if a is None else f"{a}%"
    if k == "version":
        return f"version {n}" if re.fullmatch(r"\d+(\.\d+)*", js_str(n)) else None
    if k == "date":
        m = re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", js_str(n))
        if not m:
            return None
        if m.group(3):
            return f"{int(m.group(3))} {MONTHS[int(m.group(2)) - 1]} {m.group(1)}"
        if m.group(2):
            return f"{MONTHS[int(m.group(2)) - 1]} {m.group(1)}"
        return m.group(1)
    if k == "name":
        return js_str(n).strip() or None
    return None


ACRONYM = {"ceo", "cto", "cfo", "coo", "soc2", "soc", "api", "ai", "gdpr", "nps"}


def attr_words(a: str) -> str:
    return " ".join(w.upper() if w in ACRONYM else w for w in a.split("_"))


# ---------------------------------------------------------------- referee-style validator
REFUSED = MONTHS + ["spring", "summer", "autumn", "winter", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "ago", "yesterday", "tomorrow", "once", "formerly", "previously", "originally", "initially", "recently", "lately", "soon", "eventually",
    "then", "before", "after", "since", "until", "till", "earlier", "later", "used to", "last week", "last month", "last quarter", "last year",
    "next week", "next month", "next quarter", "next year", "in the past", "in the future", "at the time", "at that time", "today", "now",
    "currently", "still"]
REFUSED_RE = [(w, re.compile(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])", re.I)) for w in REFUSED]
NEGATION = re.compile(r"\b(not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|n't\b", re.I)
NUMBER_WORDS = re.compile(r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
                          r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|dozen|single|double|half)\b", re.I)
APPROX = re.compile(r"\b(about|around|approximately|approx|roughly|nearly|almost|circa|some|over|under|at least|at most|up to|more than|less than)\b|~|≈|±", re.I)


class Validator:
    def __init__(self, lex: Lexicon, rows: list):
        self.lex = lex
        names = sorted({n for s in lex.subjects for n in [s["name"], *s["aliases"]]}, key=len, reverse=True)
        self.name_re = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(n) for n in names) + r")(?![A-Za-z0-9])", re.I)
        self.practice = {norm(r["text"]) for r in rows}

    def names_in(self, text: str) -> list:
        return [self.lex.resolve(m.group(1)) or m.group(1) for m in self.name_re.finditer(text)]

    def is_new(self, text: str) -> bool:
        return norm(text) not in self.practice

    def check(self, text: str, c: dict) -> str | None:
        if len(text) > 300:
            return "longer than 300 characters"
        if re.search(r"[.!?]\s", text.strip()[:-1]):
            return "more than one sentence"
        found = self.names_in(text)
        for r in c["required"]:
            if r not in found:
                return f"does not name {r}"
        extra = [f for f in found if f not in c["required"]]
        if extra:
            return f"names another entity: {extra[0]}"
        rest = text
        for v in c["values"]:
            if v not in rest:
                return f"value “{v}” not written"
            rest = rest.replace(v, " ", 1)
        if c.get("eventPhrase"):
            if c["eventPhrase"] not in rest:
                return "no event phrase"
            rest = rest.replace(c["eventPhrase"], " ", 1)
        rest = self.name_re.sub(" ", rest)
        if c.get("opPhrase"):
            rest = rest.replace(c["opPhrase"], " ", 1)
        if re.search(r"\d", rest):
            return "holds another number or date"
        if NUMBER_WORDS.search(rest):
            return "holds a number word"
        if APPROX.search(rest):
            return "holds a comparison or approximation word"
        for w, rx in REFUSED_RE:
            if rx.search(rest):
                return f"holds the date/time word “{w}”"
        if NEGATION.search(rest) and not (c.get("allowNo") and text.endswith(": no.")):
            return "holds a negation"
        return None


def norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


# ---------------------------------------------------------------- generator
class Generator:
    def __init__(self, rows: list, lex_raw: dict):
        self.lex = Lexicon(lex_raw)
        self.rows = rows
        self.tree = build_tree(rows, self.lex)
        self.val = Validator(self.lex, rows)
        self.slots = [sl for subj, attrs in self.tree.items() if subj in self.lex.names
                      for node in attrs.values() for sl in self._slots_of(subj, node)]

    def _slots_of(self, subject: str, node: dict) -> list:
        by: OrderedDict = OrderedDict()
        for s in node["segments"]:
            by.setdefault(s["slot"], []).append(s)
        out = []
        for slot, segs in by.items():
            seen, stable = set(), True
            for i, s in enumerate(segs):  # unstable: value comes back, or two values start on one day
                if s["value"] in seen:
                    stable = False
                seen.add(s["value"])
                if i and segs[i - 1]["from"] == s["from"]:
                    stable = False
            unsure = sum(1 for o in node["unsure"] if slot_of(o["raw"]) == slot)
            hype = sum(1 for o in node["falseValues"] if slot_of(o["raw"]) == slot)
            out.append({"subject": subject, "attribute": node["attribute"], "slot": slot, "segs": segs, "node": node, "unsure": unsure, "hype": hype, "stable": stable})
        return out

    @staticmethod
    def conf(seg: dict, slot: dict) -> float:
        c = 0.62 + 0.08 * min(len(seg["obs"]), 4)
        if slot["unsure"]:
            c -= 0.08
        if slot["hype"]:
            c -= 0.03
        if not slot["stable"]:
            c -= 0.2
        return max(0.5, min(0.97, round(c, 2)))

    def event_dates(self) -> "OrderedDict[str, str]":
        """Event date = its own `date` fact, by a clear majority (>=2 rows, >=75%) of true full-day values."""
        out: OrderedDict = OrderedDict()
        for e in self.lex.events:
            n = self.tree.get(e, {}).get("date")
            if not n:
                continue
            counts: OrderedDict = OrderedDict()
            for o in n["all"]:
                v = js_str(o["raw"]["value"])
                if o["label"] == "true" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                    counts[v] = counts.get(v, 0) + 1
            best = sorted(counts.items(), key=lambda kv: -kv[1])
            total = sum(c for _, c in best)
            if best and best[0][1] >= 2 and best[0][1] / total >= 0.75:
                out[e] = best[0][0]
        return out

    # --- fact: value held on AS_OF (latest period)
    def fact_cands(self):
        out = []
        for s in self.slots:
            if not s["stable"]:
                continue
            seg = s["segs"][-1]
            v, a = exact(seg["raw"]), attr_words(s["attribute"])
            form = {"subject": s["subject"], "attribute": s["attribute"], "value": v}
            if v["kind"] == "boolean":
                text = f"For {s['subject']}, {a}: {'yes' if v['value'] else 'no'}."
                out.append(dict(type="fact", text=text, form=form, confidence=self.conf(seg, s), check={"required": [s["subject"]], "values": [a], "allowNo": not v["value"]}))
                continue
            w = write_value(v)
            if not w:
                continue
            req = [s["subject"]]
            if v["kind"] == "name" and self.lex.resolve(w):
                req.append(self.lex.resolve(w))
            out.append(dict(type="fact", text=f"For {s['subject']}, the {a} is {w}.", form=form, confidence=self.conf(seg, s), check={"required": list(dict.fromkeys(req)), "values": [w]}))
        return out

    # --- compare: two different subjects, same comparable slot
    @staticmethod
    def magnitude(v: dict):
        k, x = v["kind"], v.get("value")
        if k == "version":
            p = [int(t) for t in js_str(x).split(".")]
            return p[0] * 1e6 + (p[1] if len(p) > 1 else 0) * 1e3 + (p[2] if len(p) > 2 else 0)
        if k == "duration" and v.get("unit") not in ("month", "year"):
            f = {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "day": 86400, "week": 604800}.get(v.get("unit") or "")
            return None if f is None else x * f
        if k == "date":
            return _date.fromisoformat(js_str(x)).toordinal() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", js_str(x)) else None
        return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None

    def compare_cands(self):
        groups: OrderedDict = OrderedDict()
        for s in self.slots:
            if not s["stable"]:
                continue
            seg = s["segs"][-1]
            v = exact(seg["raw"])
            if v["kind"] not in ("money", "quantity", "percent", "duration", "version", "date"):
                continue
            m = self.magnitude(v)
            if m is None:
                continue
            k = f"{s['slot']}:{v.get('unit')}" if v["kind"] == "quantity" else "version" if v["kind"] == "version" else s["slot"]
            groups.setdefault(k, []).append((s, seg, m))
        out = []
        for k, g in groups.items():
            is_date = k == "date"
            for L in g:
                for R in g:
                    if L is R or L[0]["subject"] == R[0]["subject"]:
                        continue
                    op = "gt" if L[2] > R[2] else "lt" if L[2] < R[2] else "eq"
                    if op == "lt" and not is_date:
                        continue  # one direction per pair for amounts
                    phrase = ({"gt": "is later than", "lt": "is earlier than", "eq": "is on the same day as"} if is_date
                              else {"gt": "is higher than", "lt": "is lower than", "eq": "is the same as"})[op]
                    ls, rs = L[0], R[0]
                    text = f"The {attr_words(ls['attribute'])} of {ls['subject']} {phrase} the {attr_words(rs['attribute'])} of {rs['subject']}."
                    c = min(self.conf(L[1], ls), self.conf(R[1], rs)) - (0.05 if op == "eq" else 0)
                    out.append(dict(type="compare", text=text, confidence=round(c, 2),
                                    form={"left": {"subject": ls["subject"], "attribute": ls["attribute"]}, "right": {"subject": rs["subject"], "attribute": rs["attribute"]}, "op": op},
                                    check={"required": [ls["subject"], rs["subject"]], "values": [], "opPhrase": phrase}))
        return out

    # --- change: two consecutive true periods
    def change_cands(self):
        out = []
        for s in self.slots:
            if not s["stable"] or len(s["segs"]) < 2:
                continue
            for i in range(1, len(s["segs"])):
                A, B = s["segs"][i - 1], s["segs"][i]
                fr, to = exact(A["raw"]), exact(B["raw"])
                if fr["kind"] == "boolean":
                    continue
                wa, wb = write_value(fr), write_value(to)
                if not wa or not wb or wa == wb:
                    continue
                text = f"For {s['subject']}, the {attr_words(s['attribute'])} went from {wa} to {wb}."
                req = [s["subject"]] + ([x for x in (self.lex.resolve(wa), self.lex.resolve(wb)) if x] if fr["kind"] == "name" else [])
                out.append(dict(type="change", text=text, confidence=min(self.conf(A, s), self.conf(B, s)),
                                form={"subject": s["subject"], "attribute": s["attribute"], "from": fr, "to": to},
                                check={"required": list(dict.fromkeys(req)), "values": [f"from {wa}", f"to {wb}"]}))
        return out

    # --- at_event: value valid on the event day, observed on both sides of it
    def at_event_cands(self):
        out = []
        for event, d in self.event_dates().items():
            for s in self.slots:
                if not s["stable"] or (s["subject"] == event and s["attribute"] == "date"):
                    continue
                seg = next((g for g in s["segs"] if g["from"] <= d and (g["to"] is None or g["to"] > d)
                            and any(o["date"] <= d for o in g["obs"]) and any(o["date"] >= d for o in g["obs"])), None)
                if not seg:
                    continue
                v = exact(seg["raw"])
                if v["kind"] == "boolean":
                    continue
                w = write_value(v)
                if not w:
                    continue
                req = [s["subject"], event] + ([self.lex.resolve(w)] if v["kind"] == "name" and self.lex.resolve(w) else [])
                out.append(dict(type="at_event", text=f"For {s['subject']}, the {attr_words(s['attribute'])} was {w} at {event}.",
                                confidence=round(self.conf(seg, s) - 0.02, 2),
                                form={"subject": s["subject"], "attribute": s["attribute"], "event": event, "value": v},
                                check={"required": list(dict.fromkeys(req)), "values": [w], "eventPhrase": f"at {event}"}))
        return out

    # --- relation: follow a name-valued link to a target whose attribute never changed
    def relation_cands(self):
        out = []
        for link in self.slots:
            if link["slot"] != "name" or not link["stable"]:
                continue
            for ls in link["segs"]:
                target = self.lex.resolve(js_str(ls["raw"]["value"]))
                if not target or target == link["subject"]:
                    continue
                for t in [x for x in self.slots if x["subject"] == target and x["stable"] and len(x["segs"]) == 1]:
                    seg = t["segs"][0]
                    v = exact(seg["raw"])
                    if v["kind"] in ("boolean", "name"):
                        continue
                    w = write_value(v)
                    if not w:
                        continue
                    lw = attr_words(link["attribute"])
                    out.append(dict(type="relation", text=f"For the {lw} of {link['subject']}, the {attr_words(t['attribute'])} is {w}.",
                                    confidence=min(self.conf(ls, link), self.conf(seg, t)),
                                    form={"subject": link["subject"], "link": link["attribute"], "target": target, "attribute": t["attribute"], "value": v},
                                    check={"required": [link["subject"]], "values": [w, lw]}))
        return out

    def generate(self, target: int = 1000):
        rejected, pools, seen = [], {t: [] for t in TYPES}, set()
        cands = self.fact_cands() + self.change_cands() + self.at_event_cands() + self.relation_cands() + self.compare_cands()
        produced = {t: 0 for t in TYPES}
        for c in cands:
            produced[c["type"]] += 1
            if c["confidence"] < MIN_CONF:
                reason = f"confidence {c['confidence']} below {MIN_CONF}"
            elif not self.val.is_new(c["text"]):
                reason = "copies a practice row"
            elif norm(c["text"]) in seen:
                reason = "duplicate"
            else:
                reason = self.val.check(c["text"], c["check"])
            if reason:
                rejected.append({"type": c["type"], "text": c["text"], "reason": reason})
                continue
            seen.add(norm(c["text"]))
            pools[c["type"]].append(c)
        for p in pools.values():
            p.sort(key=lambda c: -c["confidence"])
        picked, idx = [], {t: 0 for t in TYPES}
        while len(picked) < target:  # round-robin, best first, so every type is represented
            added = False
            for t in TYPES:
                if idx[t] < len(pools[t]) and len(picked) < target:
                    picked.append(pools[t][idx[t]]); idx[t] += 1; added = True
            if not added:
                break
        claims = [{"id": f"claim-{i + 1:04d}", "type": c["type"], "text": c["text"], "form": c["form"], "label": "true", "confidence": c["confidence"]}
                  for i, c in enumerate(picked)]
        valid = {t: len(pools[t]) for t in TYPES}
        return {"claims": claims, "rejected": rejected, "produced": produced, "valid": valid, "shortfall": max(0, target - len(claims))}


def js_num(x) -> str:
    return js_str(float(x)) if isinstance(x, float) else str(x)


def to_csv(claims: list) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "type", "text", "form", "label", "confidence"])
    for c in claims:
        w.writerow([c["id"], c["type"], c["text"], json.dumps(c["form"], ensure_ascii=False, separators=(",", ":")), c["label"], js_num(c["confidence"])])
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--practice", default="practice.json", help="practice rows as JSON list of {id,text,date,label,form}")
    ap.add_argument("--lexicon", default="lexicon.json")
    ap.add_argument("--out", default="claims.csv")
    ap.add_argument("--rejected", default=None, help="optional CSV of rejected candidates with reasons")
    ap.add_argument("--target", type=int, default=1000)
    a = ap.parse_args()

    with open(a.practice, encoding="utf-8") as f:
        rows = json.load(f)
    for r in rows:  # accept the raw CSV-style form column (JSON string) too
        if isinstance(r.get("form"), str):
            r["form"] = json.loads(r["form"])
    with open(a.lexicon, encoding="utf-8") as f:
        lex = json.load(f)

    res = Generator(rows, lex).generate(a.target)
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write(to_csv(res["claims"]))
    if a.rejected:
        with open(a.rejected, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["type", "text", "reason"], lineterminator="\n")
            w.writeheader(); w.writerows(res["rejected"])
    print(f"wrote {len(res['claims'])} claims to {a.out} (shortfall {res['shortfall']})")
    print("produced:", res["produced"])
    print("valid:   ", res["valid"])
    print("rejected:", len(res["rejected"]))


if __name__ == "__main__":
    main()
