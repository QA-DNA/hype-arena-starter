"""
Layer 2 - Temporal Interval Algebra + Knowledge Base
====================================================
Every labelled row is an observation: (subject, attribute) had value v on date d
(label true) or did NOT have v on d (label false).

Model: each fact is a step function over time. Sorted true observations
d1 < d2 < ... of a (subject, attribute) build validity intervals
    I_k = [d_k, d_{k+1})        (last one open-ended: [d_n, +inf))
Allen's interval algebra (13 relations) classifies how a claim date / claim
interval relates to I_k; "state at T" = the interval with T in it (Allen: T
'during' / 'starts' I_k). Lookup is a binary search: O(log n) per query, a
sorted-array interval tree, since intervals of one fact never overlap.

Before the first observation the state is unknown (we do NOT extrapolate back),
unless the attribute is 'static' (founded, joined, date of an event ...).
"""
from __future__ import annotations

import bisect
import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

INF = date.max
NEG_INF = date.min

# Attributes whose value never changes once set: extrapolate in both directions.
STATIC_ATTRS = {"founded", "joined", "date", "city", "previous_employer", "beta_opened",
                "founders", "launched", "released", "started"}


def to_date(s) -> date:
    return s if isinstance(s, date) else date.fromisoformat(str(s)[:10])


# ---------------------------------------------------------------- Allen algebra
@dataclass(frozen=True)
class Interval:
    start: date
    end: date            # exclusive; INF = still valid

    def contains(self, t: date) -> bool:
        return self.start <= t < self.end


def allen(a: Interval, b: Interval) -> str:
    """The Allen relation of a to b (13 base relations)."""
    if a.end < b.start:   return "before"
    if a.end == b.start:  return "meets"
    if b.end < a.start:   return "after"
    if b.end == a.start:  return "met_by"
    if a.start == b.start and a.end == b.end: return "equals"
    if a.start == b.start: return "starts" if a.end < b.end else "started_by"
    if a.end == b.end:     return "finishes" if a.start > b.start else "finished_by"
    if b.start < a.start and a.end < b.end: return "during"
    if a.start < b.start and b.end < a.end: return "contains"
    return "overlaps" if a.start < b.start else "overlapped_by"


def point(t: date) -> Interval:
    return Interval(t, date.fromordinal(t.toordinal() + 1))


# ---------------------------------------------------------------- values
def value_key(v: dict) -> tuple:
    """Hashable canonical key of a claimed value (Layer 3 does unit maths)."""
    from layer3_constraint_engine import canonical  # lazy: avoid import cycle
    return canonical(v)


@dataclass
class Observation:
    day: date
    value: dict
    row_id: str
    positive: bool       # True: label true; False: label false (value was wrong)


@dataclass
class State:
    value: dict | None
    interval: Interval | None
    support: int                      # how many true rows back this value
    relation: str                     # Allen relation of the query point to the interval
    negatives: list = field(default_factory=list)   # values known false at T
    known_values: int = 0             # distinct true values ever seen for the fact


class TemporalKB:
    def __init__(self):
        self.pos: dict[tuple, list[Observation]] = defaultdict(list)
        self.neg: dict[tuple, list[Observation]] = defaultdict(list)
        self._built = False
        self.min_day, self.max_day = INF, NEG_INF

    # -- loading ---------------------------------------------------------
    def add(self, subject: str, attribute: str, value: dict, day, row_id="", positive=True):
        d = to_date(day)
        obs = Observation(d, value, row_id, positive)
        (self.pos if positive else self.neg)[(subject, attribute)].append(obs)
        self.min_day, self.max_day = min(self.min_day, d), max(self.max_day, d)
        self._built = False

    def load_rows(self, rows, resolver=None, exclude_ids: set | None = None):
        """rows: dicts with id, date, label, form (JSON list of atoms).
        A true row makes every atom positive. A false row with ONE atom makes
        that atom negative (with several atoms we don't know which one lied)."""
        for r in rows:
            if exclude_ids and r["id"] in exclude_ids:
                continue
            label = (r.get("label") or "").strip().lower()
            if label not in ("true", "false") or not r.get("form"):
                continue
            atoms = json.loads(r["form"]) if isinstance(r["form"], str) else r["form"]
            if label == "false" and len(atoms) != 1:
                continue
            for a in atoms:
                subj = a["subject"]
                if resolver:
                    res = resolver.resolve(subj, a["attribute"])
                    subj = res.canonical or subj
                if a["value"].get("op", "eq") != "eq" and label == "true":
                    continue          # "over 10,000" is not a point value
                self.add(subj, a["attribute"], a["value"], r["date"], r["id"], label == "true")

    @classmethod
    def from_csv(cls, path: str, resolver=None, exclude_ids=None) -> "TemporalKB":
        kb = cls()
        with open(path, encoding="utf-8") as f:
            kb.load_rows(csv.DictReader(f), resolver, exclude_ids)
        return kb

    # -- index -----------------------------------------------------------
    def build(self):
        """Collapse observations into non-overlapping change intervals."""
        self.timeline: dict[tuple, list[tuple[Interval, dict, int]]] = {}
        self.starts: dict[tuple, list[date]] = {}
        for key, obs in self.pos.items():
            obs.sort(key=lambda o: o.day)
            segs: list[list] = []          # [start, value, key, support]
            for o in obs:
                k = value_key(o.value)
                if segs and segs[-1][2] == k:
                    segs[-1][3] += 1
                elif segs and segs[-1][0] == o.day:
                    # two values on the same day: keep the better supported one
                    segs[-1][3] -= 1
                    if segs[-1][3] <= 0:
                        segs[-1] = [o.day, o.value, k, 1]
                else:
                    segs.append([o.day, o.value, k, 1])
            static = key[1] in STATIC_ATTRS
            line = []
            for i, (s, v, _, sup) in enumerate(segs):
                start = NEG_INF if (i == 0 and static) else s
                end = segs[i + 1][0] if i + 1 < len(segs) else INF
                line.append((Interval(start, end), v, sup))
            self.timeline[key] = line
            self.starts[key] = [iv.start for iv, _, _ in line]
        self._built = True

    # -- query -----------------------------------------------------------
    def has_fact(self, subject, attribute) -> bool:
        return (subject, attribute) in self.pos or (subject, attribute) in self.neg

    def state_at(self, subject: str, attribute: str, day) -> State:
        if not self._built:
            self.build()
        t = to_date(day)
        key = (subject, attribute)
        negs = [o.value for o in self.neg.get(key, []) if abs((o.day - t).days) <= 0]
        line = self.timeline.get(key)
        if not line:
            return State(None, None, 0, "no_data", negs, 0)
        i = bisect.bisect_right(self.starts[key], t) - 1
        if i < 0:
            return State(None, line[0][0], 0, allen(point(t), line[0][0]), negs, len(line))
        iv, v, sup = line[i]
        return State(v, iv, sup, allen(point(t), iv), negs, len(line))

    def history(self, subject, attribute):
        if not self._built:
            self.build()
        return self.timeline.get((subject, attribute), [])

    def value_at_event(self, subject, attribute, event_date) -> State:
        return self.state_at(subject, attribute, event_date)


if __name__ == "__main__":
    import sys
    from layer1_entity_resolution import EntityResolver
    lex = sys.argv[2] if len(sys.argv) > 2 else "data/lexicon.json"
    kb = TemporalKB.from_csv(sys.argv[1] if len(sys.argv) > 1 else "data/practice.csv",
                             EntityResolver.from_file(lex))
    kb.build()
    print("facts:", len(kb.timeline), "range:", kb.min_day, "->", kb.max_day)
    changing = [(k, l) for k, l in kb.timeline.items() if len(l) > 1][:5]
    for k, l in changing:
        print(k, [(str(iv.start), str(iv.end), v.get("value")) for iv, v, _ in l])
