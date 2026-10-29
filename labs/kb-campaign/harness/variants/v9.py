"""V9 / V11 port of labs/kb-experiments/v9.py on the harness World.

Fact-level bracket features -> classifier P(fact true) trained on labelled facts (true rows; single-fact false
rows), inner GroupKFold OOF by page, stage 2 page suspicion, row P(true) = product over facts, isotonic,
(threshold, unsure band) chosen on the labelled rows. Fixed: decide() writes into an object array, so 'unsure'
is no longer truncated to 'unsur' (legacy_unsur=True restores the published behaviour, then maps 'unsur' back to
'unsure' in the output like A/v9/run_v9.py did).

Params: model 'lr' | 'hgb' | 'lrC<float>'; stage2; calib; legacy_unsur; select 'mf1' (published) | 'points' (legacy, correct unsure = 0) | 'arena' (A/score.py exactly)
(worker D's SELPTS); selftrain rounds (V11, hi/lo pseudo thresholds); extra_features ['module:func', ...]
(plugin columns appended to the 45 base columns); drop_features [column indices of the base block].
"""
import math

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from api import Prediction, feature_block
from variants.v5 import BASE, fact_scores, groups
from world import KINDS, LABELS

L1 = lambda x: math.log1p(abs(x))  # noqa: E731
N_BASE = 45


def bracket(obs):
    prev = [a for a in obs if a[0] < 0]; same = [a for a in obs if a[0] == 0]; nxt = [a for a in obs if a[0] > 0]

    def grp(g, pick):
        if not g:
            return -1, 9.0
        d0 = pick(a[0] for a in g); m = [a[1] for a in g if a[0] == d0]
        return sum(m) / len(m), L1(d0)
    pm, pg = grp(prev, max); nm, ng = grp(nxt, min)
    sm = float(np.mean([a[1] for a in same])) if same else -1
    eb = float(any(a[1] for a in prev)); ea = float(any(a[1] for a in nxt))
    return [pm, pg, nm, ng, sm, eb, ea, float(pm == 0 and eb), float(nm == 0 and ea),
            float(np.mean([a[1] for a in obs])) if obs else -1, len(obs)]


def numeric(f, obs):
    if not isinstance(f.canon, float) or f.op != "eq":
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    v = f.canon

    def near(g, pick):
        if not g:
            return None
        d0 = pick(a[0] for a in g); vals = [a[2] for a in g if a[0] == d0 and isinstance(a[2], float)]
        return vals[0] if vals else None
    pv = near([a for a in obs if a[0] < 0], max); nv = near([a for a in obs if a[0] > 0], min)
    lr = lambda a: max(-10.0, min(10.0, math.log10((abs(v) + 1e-9) / (abs(a) + 1e-9)))) if a is not None else 0.0  # noqa
    rp, rn = lr(pv), lr(nv)
    p10 = float(any(a is not None and a != v and abs(abs(x) - round(abs(x))) < 0.01 and round(abs(x)) >= 1
                    for a, x in ((pv, rp), (nv, rn))))
    btw = float(pv is not None and nv is not None and pv != nv and min(pv, nv) <= v <= max(pv, nv))
    return [rp, rn, abs(rp) + abs(rn), p10, btw, float(v == 0.0)]


def page_members(world):
    c = world.__dict__.setdefault("_v9_pages", {})
    if not c:
        fpage = world.page[world.frow]
        order = np.argsort(fpage, kind="stable")
        bounds = np.r_[0, np.flatnonzero(np.diff(fpage[order])) + 1, len(order)]
        for a, b in zip(bounds[:-1], bounds[1:]):
            c[int(fpage[order[a]])] = order[a:b]
    return c


def evidence_role(world, role=None):
    """Per row: labelled rows -> their label, others -> role ('' = no role)."""
    r = np.array([lab if lab is not None else "" for lab in world.label], dtype=object)
    if role is not None:
        r = np.where(world.labelled, r, np.asarray(role, dtype=object))
    return r


def fact_feats(world, role=None):
    """v9.fact_feats(lab, interval=True, role) -> (n_facts x 45)."""
    p = dict(BASE, interval=True)
    sp, sm = fact_scores(world, p)
    tot = sp + sm
    marg = np.divide(sp - sm, tot, out=np.zeros_like(tot), where=tot > 0)
    role = evidence_role(world, role)
    nf = np.array([len(fs) for fs in world.facts])
    # pg_other: share of negative margins over the facts of the OTHER rows of the same page
    fpage = world.page[world.frow]
    neg = (marg < 0).astype(float)
    pneg = np.bincount(fpage, neg, world.n_pages); pcnt = np.bincount(fpage, None, world.n_pages)
    rneg = np.bincount(world.frow, neg, world.n); rcnt = np.bincount(world.frow, None, world.n)
    X = np.zeros((world.n_facts, N_BASE))
    for g, cons, _ in groups(world).values():
        rows = world.frow[g]; pages = world.page[rows]; dates = world.date[rows]
        for a, n in enumerate(g):
            i = rows[a]; f = world.flat[n]; D = dates[a]
            an, ng, vo = [], [], []
            for b in np.flatnonzero(pages != pages[a]):
                k = rows[b]; c = bool(cons[a, b]); d = int(dates[b] - D); rk = role[k]
                if rk == "true":
                    an.append((d, c, world.flat[g[b]].canon))
                elif rk == "false":
                    ng.append((d, c, nf[k]))
                else:
                    vo.append((d, c, world.flat[g[b]].canon))
            prev = [x for x in an if x[0] < 0]; same = [x for x in an if x[0] == 0]; nxt = [x for x in an if x[0] > 0]

            def grp(gg, pick):
                if not gg:
                    return -1, 0.0
                d0 = pick(x[0] for x in gg); m = [x[1] for x in gg if x[0] == d0]
                return float(sum(m) * 2 > len(m)), L1(d0)
            pm, pg = grp(prev, max); nm, ngap = grp(nxt, min)
            sm_ = float(any(x[1] for x in same)) if same else -1
            match = [abs(x[0]) for x in an if x[1]]; miss = [abs(x[0]) for x in an if not x[1]]
            negm = [abs(x[0]) for x in ng if x[1] and x[2] == 1]
            vs = [math.exp(-abs(x[0]) / 30) for x in vo if x[1]]; vd = [math.exp(-abs(x[0]) / 30) for x in vo if not x[1]]
            po = pcnt[fpage[n]] - rcnt[i]
            X[n] = ([pm, pg, nm, ngap, sm_, float(bool(match)), L1(min(match)) if match else 9,
                     L1(min(miss)) if miss else 9, len(an), float(len(negm)), L1(min(negm)) if negm else 9,
                     sum(vs), sum(vd), len(vs), len(vd), marg[n],
                     (pneg[fpage[n]] - rneg[i]) / po if po else 0.0, po,
                     nf[i], float(f.op != "eq"), float(f.kind == "date" and len(f.raw["value"]) < 10),
                     KINDS.index(f.kind),
                     float(any(x[1] for x in prev)), float(any(x[1] for x in nxt)),
                     float(pm == 0 and any(x[1] for x in prev)), float(nm == 0 and any(x[1] for x in nxt)),
                     len(an), float(len(set((x[0] > 0, x[1]) for x in an)))] + bracket(an + vo)
                    + numeric(f, an if an else vo))
    return X


def make(model):
    if model.startswith("lrC"):
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=float(model[3:])))
    if model == "hgb":
        return HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05, min_samples_leaf=8,
                                              categorical_features=[21])
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.5))


def page_susp(world, p1):
    """Leave-row-out mean/max of stage-1 P(false) over the other facts of the same page."""
    out = np.full((world.n_facts, 2), 0.15)
    q = 1 - p1
    for idx in page_members(world).values():
        rows = world.frow[idx]
        for i in np.unique(rows):
            o = idx[rows != i]
            if len(o):
                out[idx[rows == i]] = (float(np.mean(q[o])), float(np.max(q[o])))
    return out


def decide(pt, t, band, legacy=False):
    out = np.where(pt >= t, "true", "false").astype("<U5" if legacy else object)
    out[np.abs(pt - t) < band] = "unsure"
    return out


class Variant:  # run() = the published V9 path; fit()/predict() for transfer tracks
    def __init__(self, model="lr", stage2=True, calib=True, legacy_unsur=False, select="mf1", selftrain=0,
                 hi=0.95, lo=0.2, extra_features=(), drop_features=()):
        self.model, self.stage2, self.calib, self.legacy = model, stage2, calib, legacy_unsur
        self.select, self.selftrain, self.hi, self.lo = select, selftrain, hi, lo
        self.extra, self.drop = list(extra_features), list(drop_features)
        self.chosen = []

    def features(self, world, role=None):
        X = fact_feats(world, role)
        if self.drop:
            X = np.delete(X, self.drop, axis=1)
        blocks = [feature_block(world, s, role) for s in self.extra]
        return np.c_[(X, *blocks)] if blocks else X

    @staticmethod
    def targets(world):
        """Fact training targets: 1 = fact of a labelled true row, 0 = the fact of a labelled single-fact false row."""
        nf = np.array([len(fs) for fs in world.facts])
        lab_f = world.label[world.frow]
        yf = np.where(lab_f == "true", 1, np.where((lab_f == "false") & (nf[world.frow] == 1), 0, -1))
        return world.labelled[world.frow] & (yf >= 0), yf

    def fit(self, train_world):
        """Transfer: train on train_world (selftrain rounds refit there too), keep models, isotonic, threshold."""
        self.run(train_world)
        return self

    def predict(self, world):
        """Apply the fitted models to another world; its labelled rows act as evidence only (no refit).
        selftrain rounds recompute pseudo-role features with the same models."""
        m1, m2, iso, t, band = self.state
        X = self.features(world)
        for r in range(self.selftrain + 1):
            if r:
                role = np.full(world.n, "", dtype=object)
                role[prow >= self.hi] = "true"; role[prow <= self.lo] = "false"
                X = self.features(world, role)
            pf = m1.predict_proba(X)[:, 1]
            if m2 is not None:
                pf = m2.predict_proba(np.c_[X, page_susp(world, pf)])[:, 1]
            prow = np.ones(world.n); np.multiply.at(prow, world.frow, pf)
            if iso is not None:
                prow = iso.predict(prow)
        out = decide(prow, t, band, self.legacy).astype(object)
        out[out == "unsur"] = "unsure"
        return Prediction(out, np.where(out == "true", prow, 1 - prow), pf)

    def run(self, world):
        trf, yf = self.targets(world)
        X = self.features(world)
        out, conf, prow, pf = self._rest(world, X, trf, yf)
        for _ in range(self.selftrain):  # V11: confident hidden rows become pseudo anchors / negatives
            role = np.full(world.n, "", dtype=object)
            role[prow >= self.hi] = "true"; role[prow <= self.lo] = "false"
            X = self.features(world, role)
            out, conf, prow, pf = self._rest(world, X, trf, yf)
        return Prediction(out, conf, pf)

    def _fit_oof(self, X, trf, yf, g, k, model):
        oof = np.full(len(yf), np.nan)
        idx = np.where(trf)[0]
        for a, b in GroupKFold(k).split(X[trf], yf[trf], g):
            if len(set(yf[idx[a]])) < 2:
                continue
            oof[idx[b]] = make(model).fit(X[idx[a]], yf[idx[a]]).predict_proba(X[idx[b]])[:, 1]
        full = make(model).fit(X[trf], yf[trf])
        return oof, full.predict_proba(X)[:, 1], full

    def _rest(self, world, X, trf, yf):
        fpage = world.page[world.frow]
        g = fpage[trf]
        k = min(4, len(set(g)))
        oof, pf, m1 = self._fit_oof(X, trf, yf, g, k, self.model)
        m2 = iso = None
        if self.stage2:
            p1 = np.where(np.isnan(oof), pf, oof)
            X = np.c_[X, page_susp(world, p1)]
            oof, pf, m2 = self._fit_oof(X, trf, yf, g, k, self.model)
        pf_tr = np.where(np.isnan(oof), pf, oof)
        prow_tr = np.ones(world.n); np.multiply.at(prow_tr, world.frow, pf_tr)
        prow = np.ones(world.n); np.multiply.at(prow, world.frow, pf)
        tr = world.labelled
        Y = world.label
        if self.calib:
            m = tr & np.isin(Y, ["true", "false"])
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(prow_tr[m], (Y[m] == "true").astype(float))
            prow_tr = iso.predict(prow_tr); prow = iso.predict(prow)
        best = None
        ytr = Y[tr].astype(str)
        for t in (0.3, 0.4, 0.5, 0.6, 0.7):
            for band in (0.0, 0.05, 0.1):
                o = decide(prow_tr, t, band, self.legacy)[tr].astype(str)
                if self.select == "points":  # legacy: scores a correct unsure as 0, kept for reproduction
                    sc = float(np.mean(np.where(o == "unsure", 0, np.where(o == ytr, 1, -1))))
                elif self.select == "arena":  # exactly A/score.py: correct unsure +1, wrong unsure 0
                    sc = float(np.mean(np.where(o == ytr, 1, np.where(o == "unsure", 0, -1))))
                else:
                    sc = f1_score(ytr, o, labels=list(LABELS), average="macro", zero_division=0)
                if best is None or sc > best[0]:
                    best = (sc, t, band)
        self.chosen.append(best[1:])
        self.state = (m1, m2, iso, best[1], best[2])
        out = decide(prow, best[1], best[2], self.legacy).astype(object)
        out[out == "unsur"] = "unsure"
        conf = np.where(out == "true", prow, 1 - prow)
        return out, conf, prow, pf
