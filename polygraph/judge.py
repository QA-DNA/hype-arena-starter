"""Stage 5: label each unlabelled row true / false / unsure, with a confidence.

This is the second model we TRAIN on the labels. Every row gets features from the truth
engine and from its own words:

  timeline   does each fact agree with its staircase on the row's date? if not, is the value
             stale (true before), premature (true later) or invented (never true)?
  support    how many other mentions share the row's value, near its date and anywhere;
             whether a labelled row already confirmed or refuted the same value
  page       the trust of the row's page (the other rows on it), labelled lies on the page
  words      speaker ("Gavin:"), hedges ("I have been told"), hype words, first person
  extraction how sure the attributor was, how many facts were found

A gradient-boosted classifier learns true / false / unsure from the labelled rows. Their
features are computed OUT OF FOLD (the truth engine refit without their own labels), so
the model trains on exactly what it will see for an unlabelled row. Its probability for
the chosen label is the confidence.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import replace

import numpy as np

from . import truth as truth_mod
from .lexicon import Lexicon
from .model import Fact, Row, Verdict, value_key

FOLDS = 5
CLASSES = ["true", "false", "unsure"]
PRIOR_TRUE = 0.83
FALSE_CUTOFF = 0.6  # call a row false only when P(false | true or false) is above this (5-fold CV)
STATUS = ["agrees", "stale", "premature", "invented", "unknown"]

HEDGE_RE = re.compile(r"\b(?:i have been told|i've been told|i hear|i heard|reportedly|rumou?r|apparently|word is|"
                      r"allegedly|supposedly|it seems|maybe|might|could|perhaps|unconfirmed|we think|i think|"
                      r"sources say|people say|they say|according to)\b", re.I)
HYPE_RE = re.compile(r"\b(?:best|fastest|biggest|largest|flawless|perfect|revolutionary|incredible|amazing|"
                     r"unmatched|record|world-class|never|always|every|all|only|more than any|first)\b", re.I)
SPEAKER_RE = re.compile(r"^\s*([A-Z][A-Za-z]+)(?:\s[A-Z][A-Za-z]+)?:")
FIRST_PERSON_RE = re.compile(r"\b(?:I|I'm|I've|we|we're|our|us|my)\b")
FUTURE_RE = re.compile(r"\b(?:will|soon|next|plan|plans|planned|aim|aims|target|expect|expects|expected|coming|upcoming)\b", re.I)
NOW_RE = re.compile(r"\b(?:now|today|currently|already|still|this week|this month)\b", re.I)


def _num(v: dict):
    try:
        k = value_key(v)
        import json
        return json.loads(k).get("value")
    except Exception:
        return None


def fact_status(t: truth_mod.Truth, f: Fact, row: Row) -> tuple[str, dict]:
    """How a row's fact stands against its timeline, and numbers about it."""
    key = (f.subject, f.attribute)
    ms = t.mentions.get(key, [])
    others = [m for m in ms if m.row != row.id]
    info = {"n_other": len(others), "same_any": 0, "same_near": 0, "diff_near": 0,
            "anchor_true_same": 0, "anchor_false_same": 0, "anchor_true_near_same": 0, "gap_days": 999,
            "prev_same": -1, "next_same": -1, "top_value": 0, "n_values": 0, "w_same_near": 0.0, "w_diff_near": 0.0,
            "anchor_false_near_diff": 0}
    if not others:
        return "unknown", info
    k = value_key({kk: vv for kk, vv in f.value.items() if kk != "op"})
    d = row.date
    dd = _days(d)
    before = [m for m in others if m.date < d]
    after = [m for m in others if m.date > d]
    if before:
        info["prev_same"] = float(max(before, key=lambda m: m.date).key == k)
    if after:
        info["next_same"] = float(min(after, key=lambda m: m.date).key == k)
    counts = defaultdict(float)
    for m in others:
        counts[m.key] += 1
    info["n_values"] = len(counts)
    info["top_value"] = float(max(counts, key=counts.get) == k)
    for m in others:
        if abs(_days(m.date) - dd) <= 60:
            w = m.weight if m.anchor == 0 else 3.0
            if m.key == k:
                info["w_same_near"] += w if m.anchor >= 0 else -3.0
            else:
                info["w_diff_near"] += w if m.anchor >= 0 else 0.0
                info["anchor_false_near_diff"] += m.anchor < 0
    for m in others:
        same = m.key == k
        near = abs(_days(m.date) - _days(d)) <= 30
        info["same_any"] += same
        info["same_near"] += same and near
        info["diff_near"] += (not same) and near
        info["anchor_true_same"] += same and m.anchor > 0
        info["anchor_false_same"] += same and m.anchor < 0
        info["anchor_true_near_same"] += same and near and m.anchor > 0
        info["gap_days"] = min(info["gap_days"], abs(_days(m.date) - _days(d)))
    od = t.on_date.get(key, {})
    held = od.get(d)
    op = f.value.get("op", "eq")
    if op != "eq":
        # "over 100 customers": true when the value held on the date satisfies it
        if held is None:
            near_dates = sorted(od, key=lambda x: abs(_days(x) - _days(d)))
            held = od[near_dates[0]] if near_dates else None
        if held is None:
            return "unknown", info
        import json
        hv, fv = json.loads(held).get("value"), _num(f.value)
        if not isinstance(hv, (int, float)) or not isinstance(fv, (int, float)):
            return "unknown", info
        ok = {"gt": hv > fv, "lt": hv < fv, "ge": hv >= fv, "le": hv <= fv}.get(op, False)
        return ("agrees" if ok else "invented"), info
    if held is None:
        return "unknown", info
    if held == k:
        return "agrees", info
    # a wrong value or a wrong extraction? a lie keeps the fact's unit and lands near its
    # value; a value given to the wrong attribute usually doesn't
    import json
    hv, rv = json.loads(held), json.loads(k)
    info["unit_match"] = float(hv.get("kind") == rv.get("kind") and hv.get("unit") == rv.get("unit")
                               and hv.get("currency") == rv.get("currency") and hv.get("per") == rv.get("per"))
    a, b = hv.get("value"), rv.get("value")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        info["rel_diff"] = abs(a - b) / max(abs(a), abs(b), 1e-9)
    info["elsewhere"] = float(any(m2.key == k for (s2, a2), ms2 in t.mentions.items()
                                  if s2 == f.subject and a2 != f.attribute for m2 in ms2))
    info["score"] = f.score
    dates_with = [x for x, v in od.items() if v == k]
    if not dates_with:
        return "invented", info
    if max(dates_with) < d:
        return "stale", info
    if min(dates_with) > d:
        return "premature", info
    return "invented", info


_DAY_CACHE: dict[str, int] = {}


def _days(d: str) -> int:
    if d not in _DAY_CACHE:
        import datetime as dt
        parts = (d + "-01-01")[:10].split("-")
        _DAY_CACHE[d] = dt.date(int(parts[0]), int(parts[1] or 1), int(parts[2] or 1)).toordinal()
    return _DAY_CACHE[d]


def row_features(r: Row, fs: list[Fact], t: truth_mod.Truth, page_info: dict) -> tuple[list[float], list[dict], str]:
    details, worst, worst_info = [], "none", None
    rank = {"none": 0, "agrees": 1, "unknown": 2, "premature": 3, "stale": 4, "invented": 5}
    agg = defaultdict(float)
    for f in fs:
        st, info = fact_status(t, f, r)
        details.append({"subject": f.subject, "attribute": f.attribute, "value": f.value, "status": st,
                        "score": round(f.score, 3)})
        agg[st] += 1
        if rank[st] > rank[worst]:
            worst, worst_info = st, info
        for k, v in info.items():
            agg["sum_" + k] += v
    wi = worst_info or {"n_other": 0, "same_any": 0, "same_near": 0, "diff_near": 0, "anchor_true_same": 0,
                        "anchor_false_same": 0, "anchor_true_near_same": 0, "gap_days": 999, "prev_same": -1,
                        "next_same": -1, "top_value": 0, "n_values": 0, "w_same_near": 0.0, "w_diff_near": 0.0,
                        "anchor_false_near_diff": 0}
    n = len(fs)
    text = r.text
    sp = SPEAKER_RE.match(text)
    trust_loo = page_info["trust_loo"]
    x = [
        n, agg["agrees"], agg["stale"], agg["premature"], agg["invented"], agg["unknown"],
        agg["agrees"] / n if n else -1,
        rank[worst],
        math.log1p(wi["n_other"]), math.log1p(wi["same_any"]), math.log1p(wi["same_near"]),
        math.log1p(wi["diff_near"]), wi["anchor_true_same"], wi["anchor_false_same"], wi["anchor_true_near_same"],
        min(wi["gap_days"], 400),
        min((f.score for f in fs), default=0), sum(f.score for f in fs) / n if n else 0,
        trust_loo, page_info["size"], page_info["false_labels"], page_info["true_labels"], page_info["unsure_labels"],
        float(bool(sp)), float(bool(sp) and sp.group(1) == "Gavin"),
        float(bool(HEDGE_RE.search(text))), len(HYPE_RE.findall(text)), float(bool(FIRST_PERSON_RE.search(text))),
        float(bool(FUTURE_RE.search(text))), float(bool(NOW_RE.search(text))),
        float("?" in text), float("!" in text), len(text), _days(r.date) - _days("2025-10-01"),
        sum(any(f.value.get("kind") == k for f in fs) for k in ("boolean",)),
        float(any("op" in f.value and f.value["op"] != "eq" for f in fs)),
        wi["prev_same"], wi["next_same"], wi["top_value"], wi["n_values"], wi["w_same_near"], wi["w_diff_near"],
        wi["anchor_false_near_diff"], agg["sum_same_any"] / n if n else 0, agg["sum_diff_near"] / n if n else 0,
        page_info.get("twin", -1),
        wi.get("unit_match", -1), wi.get("rel_diff", -1), wi.get("elsewhere", -1), wi.get("score", -1),
    ]
    return x, details, worst


def _page_info(rows: list[Row], t: truth_mod.Truth, facts: dict[str, list[Fact]], hide: set[str]) -> dict[str, dict]:
    """Per row: its page's trust without the row itself, and the page's labels."""
    by_page = defaultdict(list)
    twins = defaultdict(list)  # the same sentence elsewhere, already labelled
    for r in rows:
        by_page[r.page].append(r)
        if r.label:
            twins[_norm(r.text)].append((r.id, r.label))
    out = {}
    for p, rs in by_page.items():
        agree_n = []
        for r in rs:
            fs = facts.get(r.id, [])
            ok = [fact_status(t, f, r)[0] == "agrees" for f in fs]
            agree_n.append((sum(ok), len(ok)))
        labels = [r.label if r.id not in hide else "" for r in rs]
        tot_a = sum(a for a, _ in agree_n)
        tot_n = sum(n for _, n in agree_n)
        for i, r in enumerate(rs):
            a, n = agree_n[i]
            lab = [l for j, l in enumerate(labels) if j != i]
            out[r.id] = {
                "trust_loo": (tot_a - a + 3 * PRIOR_TRUE) / (tot_n - n + 3),
                "size": len(rs),
                "false_labels": lab.count("false"), "true_labels": lab.count("true"), "unsure_labels": lab.count("unsure"),
            }
            tw = [l for rid, l in twins.get(_norm(r.text), []) if rid != r.id]
            if tw:
                out[r.id]["twin"] = {"true": 1.0, "false": 0.0, "unsure": 0.5}[tw[0]]
    return out


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w%€$£.]+", " ", text.lower()).split()).rstrip(". ")


def featurize(rows: list[Row], facts: dict[str, list[Fact]], lexicon: Lexicon, targets: set[str]):
    t = truth_mod.build(lexicon, rows, facts)
    pinfo = _page_info(rows, t, facts, set())
    out = {}
    for r in rows:
        if r.id in targets:
            out[r.id] = row_features(r, facts.get(r.id, []), t, pinfo[r.id])
    return out, t


def label(rows: list[Row], facts: dict[str, list[Fact]], lexicon: Lexicon,
          extracted: dict[str, list[Fact]] | None = None) -> tuple[list[Verdict], truth_mod.Truth]:
    """facts: every row's facts (gold for labelled practice rows). extracted: what the
    attributor makes of the labelled rows without having seen them; a labelled row being
    hidden for training uses these, exactly like an unlabelled row."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    labelled = [r for r in rows if r.label in CLASSES]
    unlabelled = [r for r in rows if not r.label]
    extracted = extracted or {}

    # out-of-fold features for the labelled rows: refit the truth without their own labels
    lab = {r.id: r.label for r in labelled}
    X, y = [], []
    for k in range(FOLDS):
        fold = {r.id for r in labelled if r.page % FOLDS == k}
        if not fold:
            continue
        rows_k = [replace(r, label="") if r.id in fold else r for r in rows]
        facts_k = {**facts, **{rid: extracted[rid] for rid in fold if rid in extracted}}
        feats, _ = featurize(rows_k, facts_k, lexicon, fold)
        for rid, (x, _, _) in feats.items():
            X.append(x)
            y.append(lab[rid])

    feats, t = featurize(rows, facts, lexicon, {r.id for r in unlabelled})
    if not unlabelled:
        return [], t
    Xu = np.asarray([feats[r.id][0] for r in unlabelled], dtype=float)
    if len(set(y)) >= 2:
        model = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=15,
                                               l2_regularization=1.0, min_samples_leaf=10, random_state=0)
        model.fit(np.asarray(X, dtype=float), np.asarray(y))
        proba = model.predict_proba(Xu)
        classes = list(model.classes_)
    else:
        proba = np.tile([PRIOR_TRUE, 1 - PRIOR_TRUE], (len(unlabelled), 1))
        classes = ["true", "false"]

    out = []
    for r, p in zip(unlabelled, proba):
        x, details, worst = feats[r.id]
        i = int(np.argmax(p))
        lab = classes[i]
        if lab != "unsure" and "false" in classes and "true" in classes:
            pt, pf = p[classes.index("true")], p[classes.index("false")]
            lab = "false" if pf / max(1e-9, pt + pf) > FALSE_CUTOFF else "true"
        why = _why(lab, worst, details)
        if lab == "unsure":
            out.append(Verdict(r.id, "unsure", None, why, details))
        else:
            # confidence: the probability the call is right, among true/false
            pt = p[classes.index("true")] if "true" in classes else 0
            pf = p[classes.index("false")] if "false" in classes else 0
            conf = max(pt, pf) / max(1e-9, pt + pf)
            out.append(Verdict(r.id, lab, float(min(1.0, max(0.5, conf))), why, details))
    return out, t


def _why(label: str, worst: str, details: list[dict]) -> str:
    bad = next((d for d in details if d["status"] == worst), None)
    if label == "false" and bad and worst in ("stale", "premature", "invented"):
        what = {"stale": "was true before this date, not on it", "premature": "only becomes true later",
                "invented": "is never true in the timeline"}[worst]
        return f"{bad['subject']} {bad['attribute'].replace('_', ' ')}: this value {what}"
    if label == "true" and details and all(d["status"] == "agrees" for d in details):
        return "every fact agrees with its timeline"
    if label == "unsure":
        return "the evidence does not settle it"
    if not details:
        return "no fact found: judged from the page and the wording"
    return f"judged from {len(details)} fact(s), the page's trust and the wording"


def status(kb, fact: Fact, day: str) -> str:
    """Kept for the trace: a fact's status against a KB's steps."""
    from .model import same_value
    steps = kb.timeline(fact.subject, fact.attribute)
    if not steps:
        return "unknown"
    idx = [i for i, s in enumerate(steps) if same_value(s.value, fact.value)]
    if not idx:
        return "invented"
    for i in idx:
        s = steps[i]
        if s.start <= day and (s.end is None or day < s.end):
            return "agrees"
    return "premature" if all(steps[i].start > day for i in idx) else "stale"
