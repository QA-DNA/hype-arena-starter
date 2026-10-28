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
import os
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
# call a row false only when P(false | true or false) is above this (5-fold CV)
FALSE_CUTOFF = float(os.environ.get("POLY_CUTOFF", 0.6))
# the judge's gradient-boosted model: trees, learning rate, leaves, min rows per leaf (5-fold CV)
_m = [float(x) for x in os.environ.get("POLY_MODEL", "120,0.06,7,20").split(",")]
MODEL = {"iter": int(_m[0]), "lr": _m[1], "leaves": int(_m[2]), "min_leaf": int(_m[3])}
STACK = os.environ.get("POLY_STACK", "1") == "1"  # the page-level second pass
BAGS = int(os.environ.get("POLY_BAGS", 1))  # models averaged over bootstrap resamples
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
            "anchor_false_near_diff": 0, "anchor_true_near_diff": 0, "days_to_true_diff": 400,
            "days_to_true_same": 400}
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
        if m.anchor > 0:  # a confirmed-true row: how close is it, and does it agree?
            gap = abs(_days(m.date) - dd)
            if m.key == k:
                info["days_to_true_same"] = min(info["days_to_true_same"], gap)
            else:
                info["days_to_true_diff"] = min(info["days_to_true_diff"], gap)
                info["anchor_true_near_diff"] += gap <= 60
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
    info["elsewhere"] = float(bool(_values_by_subject(t).get((f.subject, k), set()) - {f.attribute}))
    info["score"] = f.score
    dates_with = [x for x, v in od.items() if v == k]
    if not dates_with:
        return "invented", info
    if max(dates_with) < d:
        return "stale", info
    if min(dates_with) > d:
        return "premature", info
    return "invented", info


def _agrees(t: truth_mod.Truth, f: Fact, row: Row) -> bool:
    """The cheap part of fact_status: does the fact hold its timeline's value on the date?"""
    if f.value.get("op", "eq") != "eq":
        return fact_status(t, f, row)[0] == "agrees"
    key = (f.subject, f.attribute)
    if len(t.mentions.get(key, ())) < 2:  # only this row: "unknown", not agreement
        return False
    held = t.on_date.get(key, {}).get(row.date)
    return held is not None and held == value_key({k: v for k, v in f.value.items() if k != "op"})


def _values_by_subject(t: truth_mod.Truth) -> dict:
    """(subject, value key) -> the attributes of that subject mentioned with that value."""
    idx = getattr(t, "_vbs", None)
    if idx is None:
        idx = defaultdict(set)
        for (s, a), ms in t.mentions.items():
            for m in ms:
                idx[(s, m.key)].add(a)
        t._vbs = idx
    return idx


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
                        "anchor_false_near_diff": 0, "anchor_true_near_diff": 0, "days_to_true_diff": 400,
                        "days_to_true_same": 400}
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
        wi["anchor_true_near_diff"], wi["days_to_true_diff"], wi["days_to_true_same"],
        float(wi["days_to_true_diff"] < wi["days_to_true_same"]),
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
            ok = [_agrees(t, f, r) for f in fs]
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


def reconcile(rows: list[Row], facts: dict[str, list[Fact]], t: truth_mod.Truth, lexicon: Lexicon,
              targets: set[str], ctx: dict) -> tuple[dict[str, list[Fact]], int]:
    """Let the knowledge base fix extraction. A value read in a sentence that exactly matches
    what one (subject on the page, attribute) holds on the sentence's date is almost surely
    that fact: if the attributor gave the value to an attribute where it makes no sense, or
    dropped it, take the match. Lies never match, so this only rescues true rows from
    looking false because of an extraction slip."""
    index: dict[str, set] = defaultdict(set)
    for (s, a), steps in t.kb.timelines.items():
        for st in steps:
            index[value_key(st.value)].add((s, a))
    out, changed = dict(facts), 0
    for r in rows:
        if r.id not in targets or r.id not in ctx["readings"]:
            continue
        fs = list(facts.get(r.id, []))
        subjects = set(ctx["subjects"].get(r.id, ()))
        for v, start, end in ctx["readings"][r.id]:
            k = value_key({kk: vv for kk, vv in v.items() if kk != "op"})
            if v.get("op", "eq") != "eq":
                continue
            matches = []
            for s, a in index.get(k, ()):
                if s in subjects:
                    st = t.kb.value_on(s, a, r.date)
                    if st is not None and value_key(st.value) == k:
                        matches.append((s, a))
            if len(matches) != 1:
                continue
            s, a = matches[0]
            at_span = [i for i, f in enumerate(fs) if f.span == (start, end)]
            if any(fs[i].subject == s and fs[i].attribute == a for i in at_span):
                continue
            if any(f.subject == s and f.attribute == a for f in fs):
                continue
            new = Fact(s, a, v, (start, end), 0.5)
            if at_span:
                i = at_span[0]
                old = fs[i]
                st_old = t.kb.value_on(old.subject, old.attribute, r.date)
                if st_old is not None and value_key(st_old.value) == value_key(old.value):
                    continue  # the attributor's choice already agrees
                fs[i] = new
            else:
                fs.append(new)
            changed += 1
        out[r.id] = fs
    return out, changed


def featurize(rows: list[Row], facts: dict[str, list[Fact]], lexicon: Lexicon, targets: set[str],
              ctx: dict | None = None):
    t = truth_mod.build(lexicon, rows, facts)
    if ctx:
        facts, changed = reconcile(rows, facts, t, lexicon, targets, ctx)
        if changed:
            t = truth_mod.build(lexicon, rows, facts)
    pinfo = _page_info(rows, t, facts, set())
    out = {}
    for r in rows:
        if r.id in targets:
            out[r.id] = row_features(r, facts.get(r.id, []), t, pinfo[r.id])
    t.facts = facts
    return out, t


def label(rows: list[Row], facts: dict[str, list[Fact]], lexicon: Lexicon,
          extracted: dict[str, list[Fact]] | None = None, ctx: dict | None = None) -> tuple[list[Verdict], truth_mod.Truth]:
    """facts: every row's facts (gold for labelled practice rows). extracted: what the
    attributor makes of the labelled rows without having seen them; a labelled row being
    hidden for training uses these, exactly like an unlabelled row."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    labelled = [r for r in rows if r.label in CLASSES]
    unlabelled = [r for r in rows if not r.label]
    extracted = extracted or {}

    # out-of-fold features for the labelled rows: refit the truth without their own labels
    lab = {r.id: r.label for r in labelled}
    page_of = {r.id: r.page for r in rows}
    X, y, ids = [], [], []
    for k in range(FOLDS):
        fold = {r.id for r in labelled if r.page % FOLDS == k}
        if not fold:
            continue
        rows_k = [replace(r, label="") if r.id in fold else r for r in rows]
        facts_k = {**facts, **{rid: extracted[rid] for rid in fold if rid in extracted}}
        feats, _ = featurize(rows_k, facts_k, lexicon, fold, ctx)
        for rid, (x, _, _) in feats.items():
            X.append(x)
            y.append(lab[rid])
            ids.append(rid)

    feats, t = featurize(rows, facts, lexicon, {r.id for r in unlabelled}, ctx)
    if not unlabelled:
        return [], t
    Xu = np.asarray([feats[r.id][0] for r in unlabelled], dtype=float)
    if len(set(y)) >= 2:
        X, y = np.asarray(X, dtype=float), np.asarray(y)
        if STACK:
            # second pass: lies cluster by page, so add how suspicious the OTHER rows of the
            # row's page look to the first pass. Training rows' page-mates are in the same
            # fold (folds go by page), so their first-pass scores are out-of-fold too.
            groups = np.asarray([page_of[i] % FOLDS for i in ids])
            p1 = _oof_pfalse(X, y, groups)
            pu = _pfalse(_model().fit(X, y), Xu)
            score = {**dict(zip(ids, p1)), **{r.id: p for r, p in zip(unlabelled, pu)}}
            X = np.hstack([X, _page_scores(ids, page_of, score)])
            Xu = np.hstack([Xu, _page_scores([r.id for r in unlabelled], page_of, score)])
        model = _model().fit(X, y)
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


def _model():
    from sklearn.ensemble import HistGradientBoostingClassifier
    base = HistGradientBoostingClassifier(max_iter=MODEL["iter"], learning_rate=MODEL["lr"],
                                          max_leaf_nodes=MODEL["leaves"], l2_regularization=1.0,
                                          min_samples_leaf=MODEL["min_leaf"], random_state=0)
    return Bagged(base, BAGS) if BAGS > 1 else base


class Bagged:
    """The average of models trained on bootstrap resamples: steadier on ~1,500 rows."""

    def __init__(self, base, n):
        self.base, self.n = base, n

    def fit(self, X, y):
        from sklearn.base import clone
        rng = np.random.default_rng(0)
        self.classes_ = np.unique(y)
        self.models = []
        for _ in range(self.n):
            idx = rng.integers(0, len(y), len(y))
            if len(np.unique(y[idx])) < len(self.classes_):
                idx = np.arange(len(y))
            self.models.append(clone(self.base).fit(X[idx], y[idx]))
        return self

    def predict_proba(self, X):
        out = np.zeros((len(X), len(self.classes_)))
        for m in self.models:
            p = m.predict_proba(X)
            for j, c in enumerate(m.classes_):
                out[:, list(self.classes_).index(c)] += p[:, j]
        return out / len(self.models)


def _pfalse(model, X) -> np.ndarray:
    p = model.predict_proba(X)
    c = list(model.classes_)
    pt = p[:, c.index("true")] if "true" in c else 0
    pf = p[:, c.index("false")] if "false" in c else 0
    return pf / np.maximum(1e-9, pt + pf)


def _oof_pfalse(X, y, groups) -> np.ndarray:
    out = np.zeros(len(y))
    for g in np.unique(groups):
        tr, te = groups != g, groups == g
        if len(set(y[tr])) < 2:
            out[te] = 1 - PRIOR_TRUE
            continue
        out[te] = _pfalse(_model().fit(X[tr], y[tr]), X[te])
    return out


def _page_scores(ids, page_of, score) -> np.ndarray:
    """Mean and max first-pass P(false) of the other rows on each row's page."""
    by_page = defaultdict(list)
    for rid, s in score.items():
        by_page[page_of[rid]].append((rid, s))
    out = []
    for rid in ids:
        others = [s for r2, s in by_page[page_of[rid]] if r2 != rid]
        out.append([float(np.mean(others)) if others else -1.0, max(others) if others else -1.0,
                    float(sum(s > 0.5 for s in others))])
    return np.asarray(out)


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
