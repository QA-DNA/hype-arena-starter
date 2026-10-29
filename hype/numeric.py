"""Numeric facts (quantity, money, duration, percent, version): assign each extracted number to (subject, attribute).

    model = numeric.train(rows_with_gold_facts, lexicon)
    out = numeric.apply(model, test_rows, lexicon, facts_by_id, hyps_by_id, all_rows)   # {id: facts}

One candidate = (number, subject, attribute). A gradient-boosting ranker scores it from: the text-only attribute posterior
(LR on the number's context, out-of-fold at train time), subject evidence (mention in the sentence, carry-over from earlier
rows of the same date, chained subjects), the value timeline (how close the number is to values this (subject, attribute)
takes on other dates in the training rows) and unit priors. Each number takes its best option if P >= THETA.
"""
import math
import re
from collections import Counter, defaultdict

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import CountVectorizer, TfidfTransformer
from sklearn.linear_model import LogisticRegression

from . import parse as P
from . import values

KINDS = {"quantity", "money", "duration", "percent", "version"}
THETA = 0.2
CTXN = 10


def _sig(v):
    k = v["kind"]
    if k == "quantity" or k == "duration":
        return (k, v["unit"])
    if k == "money":
        return (k, v["currency"], v.get("per"))
    return (k,)


def _mag(v):
    x = v["value"]
    if v["kind"] == "version":
        p = [int(t) if t.isdigit() else 0 for t in str(x).split(".")]
        return sum(t / 100.0 ** i for i, t in enumerate(p))
    return float(x)


def _dist(a, b):
    return abs(math.log((abs(a) + 1e-3) / (abs(b) + 1e-3)))


def _ck(v):
    return P._canon(v)


class Model:
    pass


def _cands(text, lex, units):
    ments = lex.mentions(text)
    cs = values.extract(text, masks=[(a, b) for a, b, _ in ments], known_units=units)
    return ments, [c for c in cs if c["v"]["kind"] in KINDS]


def _build_timeline(rows):
    tl = defaultdict(list)       # (s,a) -> [(date, sig, mag)]
    ta = defaultdict(list)       # a -> [(date, sig, mag, s)]
    for r in rows:
        for f in r["facts"]:
            v = f["value"]
            if v["kind"] in KINDS:
                tl[(f["subject"], f["attribute"])].append((r["date"], _sig(v), _mag(v), v.get("op")))
                ta[f["attribute"]].append((r["date"], _sig(v), _mag(v), f["subject"]))
    return tl, ta


def _tl_feats(m, s, a, v, date):
    sg, mg = _sig(v), _mag(v)
    L = [x for x in m.tl.get((s, a), ()) if x[0] != date]
    same = [x for x in L if x[1] == sg]
    ds = [_dist(mg, x[2]) for x in same]
    f = [len(L), len(same), min(ds) if ds else 9.0, float(bool(ds) and min(ds) < 1e-6)]
    if same:
        # closest date value (string dates compare lexicographically; distance in days approximated by ordinal of ISO date)
        o = _ord(date)
        j = min(range(len(same)), key=lambda i: abs(_ord(same[i][0]) - o))
        f += [ds[j], abs(_ord(same[j][0]) - o), float(mg > same[j][2])]
    else:
        f += [9.0, 9999, 0.0]
    A = [x for x in m.ta.get(a, ()) if x[0] != date and x[1] == sg]
    da = [_dist(mg, x[2]) for x in A]
    f += [len(A), min(da) if da else 9.0, float(bool(da) and min(da) < 1e-6)]
    # value equals a value of the same attribute but of ANOTHER subject, and not of this one
    f += [float(bool(da) and min(da) < 1e-6 and (not ds or min(ds) > 1e-6))]
    return f


_ORD = {}


def _ord(d):
    o = _ORD.get(d)
    if o is None:
        try:
            y, mo, dd = (int(t) for t in d.split("-")[:3])
            o = y * 372 + mo * 31 + dd
        except Exception:
            o = 0
        _ORD[d] = o
    return o


def _group(rows):
    """row index lists per date, in idx order."""
    g = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["idx"]):
        g[r["date"]].append(r)
    return g


def _ctx_for(i, grp, rowsubs, mentsof):
    """context per subject for row i of a same-date group: (rank by recency, rows back, count prev, chained flag)."""
    ctx = {}
    rank = 0
    for k in range(1, CTXN + 1):
        if i - k < 0:
            break
        pr = grp[i - k]
        subs = list(rowsubs.get(pr["id"], []))
        for s in subs:
            if s not in ctx:
                ctx[s] = [rank, k, 0, 1.0 if k == 1 else 0.0]
                rank += 1
        for _, _, s in mentsof(pr):
            if s not in ctx:
                ctx[s] = [rank, k, 0, 0.0]
                rank += 1
            ctx[s][2] += 1
    return ctx


def _option_feats(m, lex, r, c, ments, ctx, grp_counts, pa_row, nb_counts):
    """yield (subject, attribute, features) for one candidate."""
    v = c["v"]
    k = v["kind"]
    sg = _sig(v)
    prev = None
    for a, b, s in ments:
        if b <= c["s"]:
            prev = s
    nxt = None
    for a, b, s in ments:
        if a >= c["e"]:
            nxt = s
            break
    subs = {}
    for a, b, s in ments:
        d = c["s"] - b if b <= c["s"] else a - c["e"]
        subs[s] = min(subs.get(s, 9999), d)
    cand_subs = set(subs) | set(ctx) | set(grp_counts)
    if len(cand_subs) < 12:  # also the owners of the three likeliest attributes
        for i in np.argsort(-pa_row)[:3]:
            cn = m.inv_classes[i]
            if cn != "NONE":
                cand_subs |= m.owners.get(cn, set())
    pn = pa_row[m.classes["NONE"]] if "NONE" in m.classes else 0.0
    top = np.sort(pa_row)[::-1]
    out = []
    for s in cand_subs:
        attrs = [a for a in lex.attrs.get(s, ()) if k in m.attr_kinds.get(a, ())]
        if not attrs:
            continue
        pas = [pa_row[m.classes[a]] if a in m.classes else 0.0 for a in attrs]
        tot = sum(pas) + 1e-9
        order = sorted(range(len(attrs)), key=lambda i: -pas[i])
        rk = {attrs[i]: j for j, i in enumerate(order)}
        cx = ctx.get(s, [99, 99, 0, 0.0])
        sf = [int(s in subs), subs.get(s, 9999), int(s == prev), int(s == nxt), len(ments), len(subs), cx[0], cx[1], cx[2], cx[3],
              grp_counts.get(s, 0), nb_counts.get(s, 0), int(prev is None and len(ments) == 0)]
        for a, pa in zip(attrs, pas):
            au = m.attr_units.get(a)
            uf = (au.get(v.get("unit"), 0) / sum(au.values())) if au and k in ("quantity", "duration") else -1.0
            f = [pa, pa / tot, rk[a], pn, top[0], pa - top[0], uf, math.log1p(m.sa_count.get((s, a), 0)),
                 math.log1p(m.a_count.get(a, 0)), len(attrs)]
            f += _tl_feats(m, s, a, v, r["date"]) + sf
            f += [int(k == kk) for kk in sorted(KINDS)] + [_mag(v) if k != "version" else 0.0, int(bool(v.get("op")))]
            out.append((s, a, f))
    return out


def _featurize(m, lex, rows_ctx, probs_of):
    pass


def _lr_fit(X, y):
    cv = CountVectorizer(analyzer=str.split, binary=True)
    tf = TfidfTransformer(sublinear_tf=True)
    Z = tf.fit_transform(cv.fit_transform(X))
    clf = LogisticRegression(C=30, max_iter=300)
    clf.fit(Z, y)
    return cv, tf, clf


def _lr_proba(cv, tf, clf, X, classes):
    p = clf.predict_proba(tf.transform(cv.transform(X)))
    out = np.zeros((len(X), len(classes)))
    for j, c in enumerate(clf.classes_):
        if c in classes:
            out[:, classes[c]] = p[:, j]
    return out


def _attr_data(rows, lex, units):
    """per row: (ments, cands, feat strings, labels)."""
    out = []
    for r in rows:
        ments, cs = _cands(r["text"], lex, units)
        gold = defaultdict(list)
        for f in r["facts"]:
            gold[_ck(f["value"])].append((f["subject"], f["attribute"]))
        out.append((ments, cs, [P.feat_string(r["text"], c, ments) for c in cs],
                    [(gold.get(_ck(c["v"])) or [(None, "NONE")]) for c in cs]))
    return out


def train(rows, lexicon, inner=4):
    lex = P.Lex(lexicon)
    m = Model()
    m.lex = lex
    m.units = {f["value"]["unit"] for r in rows for f in r["facts"] if f["value"]["kind"] == "quantity"}
    m.attr_kinds = defaultdict(set)
    m.attr_units = defaultdict(Counter)
    m.sa_count, m.a_count = Counter(), Counter()
    for r in rows:
        for f in r["facts"]:
            v = f["value"]
            if v["kind"] in KINDS:
                m.attr_kinds[f["attribute"]].add(v["kind"])
                if "unit" in v:
                    m.attr_units[f["attribute"]][v["unit"]] += 1
                m.sa_count[(f["subject"], f["attribute"])] += 1
                m.a_count[f["attribute"]] += 1
    m.tl, m.ta = _build_timeline(rows)
    data = _attr_data(rows, lex, m.units)
    classes = sorted({a for d in data for lab in d[3] for _, a in lab if a != "NONE"} | {"NONE"})
    m.classes = {c: i for i, c in enumerate(classes)}
    m.inv_classes = classes
    m.owners = defaultdict(set)
    for sname, ats in lex.attrs.items():
        for a in ats:
            m.owners[a].add(sname)

    def flat(idxs):
        X, y = [], []
        for i in idxs:
            for fs, lab in zip(data[i][2], data[i][3]):
                X.append(fs); y.append(lab[0][1])
        return X, y

    # out-of-fold attribute posteriors for the ranker's training rows
    dates = sorted({r["date"] for r in rows})
    fold = {d: i % inner for i, d in enumerate(dates)}
    oof = {}
    for k in range(inner):
        tr = [i for i, r in enumerate(rows) if fold[r["date"]] != k]
        te = [i for i, r in enumerate(rows) if fold[r["date"]] == k]
        X, y = flat(tr)
        mdl = _lr_fit(X, y)
        Xt = [fs for i in te for fs in data[i][2]]
        if Xt:
            pr = _lr_proba(*mdl, Xt, m.classes)
            j = 0
            for i in te:
                oof[i] = pr[j:j + len(data[i][2])]; j += len(data[i][2])
    X, y = flat(range(len(rows)))
    m.lr = _lr_fit(X, y)
    # ranker rows
    grps = _group(rows)
    pos = {}
    for d, g in grps.items():
        for j, r in enumerate(g):
            pos[r["id"]] = (g, j)
    idx_of = {r["id"]: i for i, r in enumerate(rows)}
    rowsubs = {r["id"]: list(dict.fromkeys(f["subject"] for f in r["facts"])) for r in rows}   # teacher forcing: gold subjects
    mentsof = lambda r: data[idx_of[r["id"]]][0]
    FX, FY = [], []
    for i, r in enumerate(rows):
        ments, cs, _, labs = data[i]
        if not cs:
            continue
        g, j = pos[r["id"]]
        ctx = _ctx_for(j, g, rowsubs, mentsof)
        gc, nb = _date_counts(g, j, mentsof)
        for ci, c in enumerate(cs):
            gold = set(labs[ci])
            for s, a, f in _option_feats(m, lex, r, c, ments, ctx, gc, oof[i][ci], nb):
                FX.append(f); FY.append(int((s, a) in gold))
    m.gbm = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.06, max_iter=250, min_samples_leaf=20, l2_regularization=1.0, random_state=0)
    m.gbm.fit(np.array(FX, dtype=float), np.array(FY))
    return m


def _date_counts(g, j, mentsof):
    gc, nb = Counter(), Counter()
    for k, r in enumerate(g):
        if k == j:
            continue
        for _, _, s in mentsof(r):
            gc[s] += 1
            if abs(k - j) <= 3:
                nb[s] += 1
    return gc, nb


def apply(m, test_rows, lexicon, facts_by_id, hyps_by_id, all_rows, theta=None):
    theta = THETA if theta is None else theta
    lex = m.lex
    mc = {}
    def mentsof(r):
        x = mc.get(r["id"])
        if x is None:
            x = mc[r["id"]] = lex.mentions(r["text"])
        return x
    grps = _group(all_rows)
    pos = {}
    for d, g in grps.items():
        for j, r in enumerate(g):
            pos[r["id"]] = (g, j)
    tests = sorted(test_rows, key=lambda r: r["idx"])
    cand = {r["id"]: _cands(r["text"], lex, m.units) for r in tests}
    X = [P.feat_string(r["text"], c, cand[r["id"]][0]) for r in tests for c in cand[r["id"]][1]]
    probs = _lr_proba(*m.lr, X, m.classes) if X else np.zeros((0, len(m.classes)))
    rowsubs = {rid: list(dict.fromkeys(f["subject"] for f in fs if f["value"]["kind"] not in KINDS)) for rid, fs in facts_by_id.items()}
    out, o = {}, 0
    for r in tests:
        ments, cs = cand[r["id"]]
        base = [f for f in facts_by_id.get(r["id"], []) if f["value"]["kind"] not in KINDS]
        new = {}
        if cs:
            g, j = pos[r["id"]]
            ctx = _ctx_for(j, g, rowsubs, mentsof)
            gc, nb = _date_counts(g, j, mentsof)
            for ci, c in enumerate(cs):
                opts = _option_feats(m, lex, r, c, ments, ctx, gc, probs[o + ci], nb)
                if not opts:
                    continue
                p = m.gbm.predict_proba(np.array([f for _, _, f in opts], dtype=float))[:, 1]
                b = int(np.argmax(p))
                if p[b] >= theta:
                    key = (opts[b][0], opts[b][1])
                    if key not in new or new[key][0] < p[b]:
                        new[key] = (p[b], {"subject": key[0], "attribute": key[1], "value": c["v"], "_p": float(p[b])})
            o += len(cs)
        fs = base + [f for _, f in new.values()]
        out[r["id"]] = fs
        rowsubs[r["id"]] = list(dict.fromkeys(f["subject"] for f in fs))
    return out
