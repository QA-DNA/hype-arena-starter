"""Boolean facts from the attribute side: score every boolean (subject, attribute) in scope against the sentence.

    model = booleans.train(rows_with_gold_facts, lexicon)
    new = booleans.apply(model, test_rows, lexicon, facts_by_id, hyps_by_id, all_rows)   # {id: facts}
"""
import re
from collections import Counter, defaultdict

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict

from . import parse, values

THETA = 0.4
BOOL_KINDS = {"boolean"}
W = re.compile(r"[a-z0-9]+")


def _stem(w):
    return w[:5]


def _toks(s):
    return [_stem(w) for w in W.findall(s.lower().replace("_", " "))]


def _scope(rows, lex):
    """{row id: [(subject, weight, explicit)]} from the row's mentions and the same-date neighbours (text only)."""
    out = {}
    for i, r in enumerate(rows):
        ctx = dict(parse._context(rows[max(0, i - parse.CTX_ROWS):i], rows[i + 1:i + 4], lex, r["date"]))
        d = {s: (w, 0) for s, w in ctx.items()}
        for _, _, s in lex.mentions(r["text"]):
            d[s] = (1.0, 1)
        out[r["id"]] = d
    return out


def _pair_feats(text, ttoks, subj, w, expl, attr, prior, lrs, nfacts, nment):
    at = [t for t in _toks(attr) if t not in {"is", "of", "the", "by", "in"}]
    hit = [t for t in at if t in ttoks]
    return [len(hit) / max(1, len(at)), len(hit), len(at), len(hit) == len(at), w, expl, prior, lrs, nfacts, nment, len(text),
            sum(len(t) for t in hit)]


class Model:
    pass


def _cands(lex, battrs, scope):
    for s, (w, expl) in scope.items():
        for a in lex.attrs.get(s, ()):
            if (s, a) in battrs or a in battrs_any_cache:
                yield s, a, w, expl


battrs_any_cache = set()


def _row_pairs(m, lex, r, sc, nfacts, lr_row):
    ttoks = set(_toks(r["text"]))
    nment = len(lex.mentions(r["text"]))
    out = []
    for s, (w, expl) in sc.items():
        for a in lex.attrs.get(s, ()):
            if a not in m.battr:
                continue
            out.append((s, a, _pair_feats(r["text"], ttoks, s, w, expl, a, m.prior.get((s, a), 0) + (0 if (s, a) in m.prior else 0.0) / 1,
                                          lr_row.get(a, 0.0), nfacts, nment)))
    return out


def train(rows, lexicon):
    lex = parse.Lex(lexicon)
    m = Model()
    m.lex = lex
    gold = {r["id"]: [f for f in r["facts"] if f["value"]["kind"] == "boolean"] for r in rows}
    m.prior = Counter((f["subject"], f["attribute"]) for r in rows for f in gold[r["id"]])
    m.battr = {a for _, a in m.prior}
    # text -> attribute scores (out-of-fold for the training rows)
    pos = [r for r in rows if gold[r["id"]]]
    m.tf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2)
    ya = [gold[r["id"]][0]["attribute"] for r in pos]
    allr = rows
    yall = [gold[r["id"]][0]["attribute"] if gold[r["id"]] else "NONE" for r in allr]
    Xall = m.tf.fit_transform([r["text"] for r in allr])
    m.lr = LogisticRegression(C=30, max_iter=300).fit(Xall, yall)
    oof = cross_val_predict(LogisticRegression(C=30, max_iter=300), Xall, yall, cv=4, method="predict_proba")
    classes = {c: i for i, c in enumerate(sorted(set(yall)))}
    scope = _scope(rows, lex)
    X, y = [], []
    for k, r in enumerate(rows):
        lr_row = {a: oof[k][classes[a]] for a in list(m.battr) + ['NONE'] if a in classes}
        gs = {(f["subject"], f["attribute"]) for f in gold[r["id"]]}
        nf = sum(1 for f in r["facts"] if f["value"]["kind"] != "boolean")
        # leave-one-out prior: do not count this row's own gold
        for s, a, f in _row_pairs(m, lex, r, scope[r["id"]], nf, lr_row):
            f = list(f)
            f[6] = max(0, m.prior.get((s, a), 0) - (1 if (s, a) in gs else 0))
            X.append(f); y.append((s, a) in gs)
    m.clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=10, random_state=0).fit(np.array(X), np.array(y))
    m.lr_classes = {c: i for i, c in enumerate(m.lr.classes_)}
    return m


def apply(model, test_rows, lexicon, facts_by_id, hyps_by_id, all_rows):
    lex = model.lex
    scope_all = _scope(all_rows, lex)
    P = model.lr.predict_proba(model.tf.transform([r["text"] for r in test_rows]))
    out = {}
    for k, r in enumerate(test_rows):
        old = [f for f in facts_by_id.get(r["id"], [])]
        keep = [f for f in old if f["value"]["kind"] != "boolean"]
        lr_row = {a: P[k][model.lr_classes[a]] for a in list(model.battr) + ['NONE'] if a in model.lr_classes}
        pairs = _row_pairs(model, lex, r, scope_all[r["id"]], len(keep), lr_row)
        new = []
        if pairs:
            pr = model.clf.predict_proba(np.array([f for _, _, f in pairs]))[:, 1]
            order = np.argsort(-pr)
            seen = set()
            for j in order[:2]:
                if pr[j] < THETA or pairs[j][1] in seen:
                    continue
                seen.add(pairs[j][1])
                new.append({"subject": pairs[j][0], "attribute": pairs[j][1], "value": {"kind": "boolean", "value": not values.has_negation(r["text"])},
                            "_p": float(pr[j]), "_s": float(pr[j])})
        out[r["id"]] = keep + new
    return out
