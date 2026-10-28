"""Stage 6: write exactly 1,000 new claims, every one true.

Pipeline: KB -> candidates of all five types -> render text with templates ->
validate.validate() -> rank by confidence with a mix of types -> the best 1,000.

STATUS: baseline with plain templates for all five types.
Owner: backend teammate (branch `forge`), see docs/BRIEF_backend.md. Ideas to improve:
nicer per-attribute wording (artifacts/templates.json), unit conversion in compares,
smarter ranking, reading every text back through the reader once it lands.
"""
from __future__ import annotations

import itertools
from typing import Iterator

from . import AS_OF
from .kb import KB
from .model import Claim, Step
from .render import attribute_words, render
from .validate import has_time_word, normalize_text, validate

N_CLAIMS = 1000
DURATION_SECONDS = {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "day": 86400, "week": 604800}
AMOUNT_PHRASES = {"gt": "higher than", "lt": "lower than", "eq": "the same as"}
DATE_PHRASES = {"gt": "later than", "lt": "earlier than"}


def _words_ok(attribute: str, allow_digits: bool = True) -> bool:
    w = attribute_words(attribute)
    if has_time_word(w):
        return False
    return allow_digits or not any(ch.isdigit() for ch in w)


def _step_conf(step: Step) -> float:
    """How sure we are of a stair: anchored by a labelled row, or backed by many mentions."""
    return min(0.99, max(step.confidence, 0.6 + 0.08 * step.support))


# ---- fact ------------------------------------------------------------------------------
def fact_claims(kb: KB) -> Iterator[Claim]:
    for (subj, attr) in kb.facts():
        step = kb.current(subj, attr)
        if step is None or not _words_ok(attr):
            continue
        v = step.value
        if v["kind"] == "boolean":
            words = attribute_words(attr)
            text = f"{subj} has {words}." if v["value"] else f"{subj} does not have {words}."
        else:
            r = render(v)
            if r is None:
                continue
            text = f"The {attribute_words(attr)} of {subj} is {r}."
        yield Claim("", "fact", text, {"subject": subj, "attribute": attr, "value": v},
                    _step_conf(step), [{"subject": subj, "attribute": attr}])


# ---- compare ---------------------------------------------------------------------------
def _amount(v: dict) -> tuple[tuple, float] | None:
    """(what it compares with, a comparable number), or None if it does not compare."""
    k = v["kind"]
    if k == "quantity":
        return ("quantity", v["unit"].lower()), float(v["value"])
    if k == "money":
        return ("money", v["currency"], v.get("per")), float(v["value"])
    if k == "percent":
        return ("percent",), float(v["value"])
    if k == "duration" and v["unit"] in DURATION_SECONDS:
        return ("duration",), float(v["value"]) * DURATION_SECONDS[v["unit"]]
    if k == "date" and len(v["value"]) == 10:
        return ("date",), float(v["value"].replace("-", ""))
    return None


def compare_claims(kb: KB) -> Iterator[Claim]:
    groups: dict[tuple, list] = {}
    for (subj, attr) in kb.facts():
        step = kb.current(subj, attr)
        if step is None or not _words_ok(attr, allow_digits=False):
            continue
        a = _amount(step.value)
        if a is not None:
            groups.setdefault(a[0], []).append((subj, attr, a[1], step))
    for kind, items in groups.items():
        for (ls, la, lv, lstep), (rs, ra, rv, rstep) in itertools.permutations(items, 2):
            if (ls, la) == (rs, ra):
                continue
            op = "gt" if lv > rv else "lt" if lv < rv else "eq"
            phrases = DATE_PHRASES if kind == ("date",) else AMOUNT_PHRASES
            if op not in phrases:
                continue
            text = (f"The {attribute_words(la)} of {ls} is {phrases[op]} "
                    f"the {attribute_words(ra)} of {rs}.")
            form = {"left": {"subject": ls, "attribute": la}, "right": {"subject": rs, "attribute": ra}, "op": op}
            conf = min(_step_conf(lstep), _step_conf(rstep)) * 0.95
            yield Claim("", "compare", text, form, conf,
                        [{"subject": ls, "attribute": la}, {"subject": rs, "attribute": ra}])


# ---- change ----------------------------------------------------------------------------
def change_claims(kb: KB) -> Iterator[Claim]:
    for (subj, attr) in kb.facts():
        steps = kb.timeline(subj, attr)
        if not _words_ok(attr):
            continue
        for a, b in zip(steps, steps[1:]):
            if a.value["kind"] == "boolean":
                continue
            ra, rb = render(a.value), render(b.value)
            if ra is None or rb is None:
                continue
            text = f"The {attribute_words(attr)} of {subj} went from {ra} to {rb}."
            form = {"subject": subj, "attribute": attr, "from": a.value, "to": b.value}
            yield Claim("", "change", text, form, min(_step_conf(a), _step_conf(b)) * 0.95,
                        [{"subject": subj, "attribute": attr}])


# ---- at_event --------------------------------------------------------------------------
def at_event_claims(kb: KB) -> Iterator[Claim]:
    events = {e: d for e, d in kb.events.items() if len(d) == 10}
    for (subj, attr) in kb.facts():
        if not _words_ok(attr) or kb.lexicon.is_event(subj):
            continue
        for event, day in events.items():
            step = kb.value_on(subj, attr, day)
            if step is None or step.value["kind"] == "boolean":
                continue
            r = render(step.value)
            if r is None:
                continue
            text = f"The {attribute_words(attr)} of {subj} was {r} at {event}."
            form = {"subject": subj, "attribute": attr, "event": event, "value": step.value}
            yield Claim("", "at_event", text, form, _step_conf(step) * 0.9,
                        [{"subject": subj, "attribute": attr}, {"subject": event, "attribute": "date"}])


# ---- relation --------------------------------------------------------------------------
def relation_claims(kb: KB) -> Iterator[Claim]:
    for (subj, link), lsteps in kb.links().items():
        if not _words_ok(link):
            continue
        for ls in lsteps:
            target = kb.lexicon.canonical(ls.value["value"])
            for attr in kb.lexicon.attributes(target):
                if not _words_ok(attr):
                    continue
                for ts in kb.timeline(target, attr):
                    overlaps = ts.start < (ls.end or "9999") and ls.start < (ts.end or "9999")
                    if not overlaps or ts.value["kind"] == "boolean":
                        continue
                    r = render(ts.value)
                    if r is None:
                        continue
                    text = f"The {attribute_words(attr)} of the {attribute_words(link)} of {subj} is {r}."
                    form = {"subject": subj, "link": link, "target": target, "attribute": attr, "value": ts.value}
                    yield Claim("", "relation", text, form, min(_step_conf(ls), _step_conf(ts)) * 0.9,
                                [{"subject": subj, "attribute": link}, {"subject": target, "attribute": attr}])


GENERATORS = {"fact": fact_claims, "compare": compare_claims, "change": change_claims,
              "at_event": at_event_claims, "relation": relation_claims}
# how many of the 1,000 each type may take at most, before topping up with the rest
QUOTA = {"fact": 350, "relation": 150, "at_event": 150, "change": 150, "compare": 400}


def generate(kb: KB, input_texts: set[str], n: int = N_CLAIMS) -> list[Claim]:
    seen_text: set[str] = set()
    pools: dict[str, list[Claim]] = {}
    for t, gen in GENERATORS.items():
        pool = []
        for c in gen(kb):
            c.id = "candidate"
            key = normalize_text(c.text)
            if key in seen_text or validate(c, kb.lexicon, input_texts):
                continue
            seen_text.add(key)
            pool.append(c)
        pool.sort(key=lambda c: -c.confidence)
        pools[t] = pool
    chosen = []
    for t, pool in pools.items():
        chosen += pool[:QUOTA[t]]
    rest = sorted((c for t, p in pools.items() for c in p[QUOTA[t]:]), key=lambda c: -c.confidence)
    chosen += rest[: max(0, n - len(chosen))]
    chosen.sort(key=lambda c: -c.confidence)
    chosen = chosen[:n]
    for i, c in enumerate(chosen, 1):
        c.id = f"c{i:04d}-{c.type}"
    return chosen
