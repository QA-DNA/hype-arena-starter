"""Stage 4: rebuild every fact's timeline from all rows.

Phase 2 (Claude): temporal truth discovery. For each (subject, attribute), fit a staircase
over all mentions with dynamic programming, weighting each mention by its page's trust;
re-estimate page trust from how well the page agrees with the staircases; repeat. Labelled
rows are anchors: a `true` row fixes its value on its date, a `false` row forbids it.

STATUS: baseline. The KB is the gold one (labelled practice rows' forms); facts the
extractor found in unlabelled rows are only recorded as mentions.
"""
from __future__ import annotations

from .kb import KB
from .lexicon import Lexicon
from .model import Fact, Row


def build_kb(lexicon: Lexicon, rows: list[Row], facts: dict[str, list[Fact]],
             gold_forms: dict[str, list[dict]]) -> KB:
    kb = KB.from_gold(lexicon, rows, gold_forms)
    for r in rows:
        if r.label:
            continue
        for f in facts.get(r.id, []):
            kb.mentions[(f.subject, f.attribute)].append(
                {"date": r.date, "value": f.value, "row_id": r.id, "verdict": ""})
    return kb
