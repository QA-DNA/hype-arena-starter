"""Stage 4: rebuild every fact's timeline from all rows: temporal truth discovery.

For each (subject, attribute) we fit a staircase over the dates it is mentioned, by
dynamic programming: each date takes one value; a mention that disagrees with its date's
value costs its weight; changing value between dates costs SWITCH. So a lone lie (an
invented, stale or premature value) is outvoted, while a real change, repeated by later
pages, becomes a new stair.

Weights: an unlabelled mention weighs its page's trust x its extraction score. Labelled
rows are anchors: a `true` row pins its value on its date, a `false` row forbids it.

Page trust is re-estimated from how well each page agrees with the staircases, and the
staircases are refit, a few rounds (EM-style).
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from .kb import KB
from .lexicon import Lexicon
from .model import Fact, Row, Step, same_value, value_key

import os

# tuned by scripts/eval_labels.py; POLY_* environment variables override them for experiments
SWITCH = float(os.environ.get("POLY_SWITCH", 1.6))  # cost of a change of value between two dates
ANCHOR = float(os.environ.get("POLY_ANCHOR", 6.0))  # weight of a labelled row
PRIOR_TRUST = 0.85  # share of true rows in practice
TRUST_PSEUDO = float(os.environ.get("POLY_PSEUDO", 3.0))  # pseudo-count pulling small pages to the prior
ROUNDS = int(os.environ.get("POLY_ROUNDS", 3))


@dataclass
class Mention:
    row: str
    date: str
    value: dict
    key: str
    weight: float
    anchor: int  # +1 labelled true, -1 labelled false, 0 unlabelled


@dataclass
class Truth:
    """The fitted world: timelines, page trust, and per-row agreement."""
    kb: KB
    page_trust: dict[int, float]
    # (subject, attribute) -> {date: value key the staircase holds on that date}
    on_date: dict[tuple, dict[str, str]] = field(default_factory=dict)
    mentions: dict[tuple, list[Mention]] = field(default_factory=dict)


def _fit_staircase(ms: list[Mention]) -> dict[str, str]:
    """date -> value key, minimizing disagreement cost + SWITCH per change."""
    by_date: dict[str, list[Mention]] = defaultdict(list)
    for m in ms:
        by_date[m.date].append(m)
    dates = sorted(by_date)
    values = sorted({m.key for m in ms})
    if len(values) == 1:
        return {d: values[0] for d in dates}
    INF = float("inf")
    prev = None
    back = []
    for d in dates:
        cost = {}
        for v in values:
            c = 0.0
            for m in by_date[d]:
                if m.anchor > 0:
                    c += ANCHOR * (m.key != v)
                elif m.anchor < 0:
                    c += ANCHOR * (m.key == v)
                else:
                    c += m.weight * (m.key != v)
            cost[v] = c
        if prev is None:
            cur, bk = dict(cost), {v: None for v in values}
        else:
            bu = min(values, key=lambda u: prev[u])
            cur, bk = {}, {}
            for v in values:
                stay, switch = prev[v], prev[bu] + SWITCH
                cur[v], bk[v] = (stay, v) if stay <= switch else (switch, bu)
                cur[v] += cost[v]
        back.append(bk)
        prev = cur
    v = min(values, key=lambda u: prev[u])
    out = {}
    for i in range(len(dates) - 1, -1, -1):
        out[dates[i]] = v
        v = back[i][v] if back[i][v] is not None else v
    return out


def _steps(on_date: dict[str, str], ms: list[Mention]) -> list[Step]:
    """Collapse a date -> value map into Steps, with support = agreeing mentions."""
    value_of = {m.key: m.value for m in ms}
    steps: list[Step] = []
    for d in sorted(on_date):
        k = on_date[d]
        agree = sum(1 for m in ms if m.date == d and m.key == k and m.anchor >= 0)
        anchors = sum(1 for m in ms if m.date == d and m.key == k and m.anchor > 0)
        if steps and value_key(steps[-1].value) == k:
            s = steps[-1]
            s.support += agree
            s.last_seen = d
            s.confidence = max(s.confidence, 1.0 if anchors else 0.0)
            continue
        if steps:
            steps[-1].end = d
        steps.append(Step(d, None, value_of[k], 1.0 if anchors else 0.0, agree, d))
    for s in steps:  # confidence: anchored, or by how many mentions back it
        s.confidence = 1.0 if s.confidence == 1.0 else min(0.97, 0.55 + 0.1 * s.support)
    return steps


TIMER = {"ms": 0.0}  # time spent here, for the pipeline's stage timings


def build(lexicon: Lexicon, rows: list[Row], facts: dict[str, list[Fact]]) -> Truth:
    """Fit the timelines. `facts` holds every row's facts (gold forms for practice rows the
    input labels, extracted ones for the rest)."""
    t0 = time.perf_counter()
    try:
        return _build(lexicon, rows, facts)
    finally:
        TIMER["ms"] += (time.perf_counter() - t0) * 1000


def _build(lexicon: Lexicon, rows: list[Row], facts: dict[str, list[Fact]]) -> Truth:
    page_of = {r.id: r.page for r in rows}
    label_of = {r.id: r.label for r in rows}
    trust = {r.page: PRIOR_TRUST for r in rows}
    fact_rows: dict[tuple, list[tuple[Row, Fact]]] = defaultdict(list)
    for r in rows:
        for f in facts.get(r.id, []):
            if f.value.get("op", "eq") != "eq":
                continue  # "over 100 customers" does not pin a value
            fact_rows[(f.subject, f.attribute)].append((r, f))

    on_date: dict[tuple, dict[str, str]] = {}
    mentions: dict[tuple, list[Mention]] = {}
    for _ in range(ROUNDS):
        for key, items in fact_rows.items():
            ms = []
            for r, f in items:
                anchor = 1 if r.label == "true" else -1 if r.label == "false" else 0
                ms.append(Mention(r.id, r.date, f.value, value_key(f.value),
                                  trust[r.page] * f.score, anchor))
            mentions[key] = ms
            on_date[key] = _fit_staircase(ms)
        # page trust from agreement of its unlabelled + labelled rows
        agree, n = defaultdict(float), defaultdict(float)
        for key, ms in mentions.items():
            for m in ms:
                p = page_of[m.row]
                ok = on_date[key].get(m.date) == m.key
                if label_of[m.row] in ("true", "false"):
                    ok = label_of[m.row] == "true"
                agree[p] += ok
                n[p] += 1
        for r in rows:
            if label_of[r.id] in ("true", "false") and not facts.get(r.id):
                agree[r.page] += label_of[r.id] == "true"
                n[r.page] += 1
        trust = {p: (agree[p] + TRUST_PSEUDO * PRIOR_TRUST) / (n[p] + TRUST_PSEUDO) for p in trust}

    kb = KB(lexicon)
    for key, ms in mentions.items():
        kb.timelines[key] = _steps(on_date[key], ms)
        for m in ms:
            kb.mentions[key].append({"date": m.date, "value": m.value, "row_id": m.row,
                                     "verdict": label_of[m.row] or ("agrees" if on_date[key][m.date] == m.key else "disagrees")})
    return Truth(kb, trust, on_date, mentions)


def build_kb(lexicon: Lexicon, rows: list[Row], facts: dict[str, list[Fact]], gold_forms=None) -> KB:
    return build(lexicon, rows, facts).kb
