"""Stage 5: label each unlabelled row true / false / unsure, with a confidence.

Each fact a row states gets a status against its timeline:
  agrees     the value holds on the row's date
  stale      the value held before the row's date, not on it
  premature  the value holds only after the row's date
  invented   the value never holds
  unknown    no timeline for this fact

Phase 2 (Claude): these statuses plus page trust, support, hedge words ("I have been
told"), speaker and outlier features feed a gradient-boosted model trained at runtime on
the labelled rows, whose probabilities are calibrated into confidences.

STATUS: baseline rules.
"""
from __future__ import annotations

from .kb import KB
from .model import Fact, Row, Verdict, same_value

PRIOR_TRUE = 0.83  # share of `true` among practice rows


def status(kb: KB, fact: Fact, day: str) -> str:
    steps = kb.timeline(fact.subject, fact.attribute)
    if not steps:
        return "unknown"
    idx = [i for i, s in enumerate(steps) if same_value(s.value, fact.value)]
    if not idx:
        return "invented"
    for i in idx:
        s = steps[i]
        # the value may have started any time after the previous step was last seen,
        # and may have lasted until the next step was first seen
        start = steps[i - 1].last_seen or steps[i - 1].start if i > 0 else s.start
        if (start < day or s.start <= day) and (s.end is None or day < s.end):
            return "agrees"
    if all(steps[i].start > day for i in idx):
        return "premature"
    return "stale"


def label(rows: list[Row], facts: dict[str, list[Fact]], kb: KB) -> list[Verdict]:
    out = []
    for r in rows:
        if r.label:
            continue
        fs = facts.get(r.id, [])
        st = [status(kb, f, r.date) for f in fs]
        detail = [{"subject": f.subject, "attribute": f.attribute, "value": f.value, "status": s}
                  for f, s in zip(fs, st)]
        bad = [d for d in detail if d["status"] in ("stale", "premature", "invented")]
        if bad:
            b = bad[0]
            out.append(Verdict(r.id, "false", 0.8, f"{b['status']}: {b['subject']} {b['attribute']}", detail))
        elif st and all(s == "agrees" for s in st):
            out.append(Verdict(r.id, "true", 0.9, "agrees with the timeline", detail))
        else:
            out.append(Verdict(r.id, "true", 0.6, "no evidence either way: base rate", detail))
    return out
