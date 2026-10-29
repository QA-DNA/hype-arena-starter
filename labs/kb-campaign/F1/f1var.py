"""F1 standalone labellers: a truth-discovery method gives P(fact true on its date); row = product over its
facts; calibration (isotonic by default) and the (threshold, unsure band) are fitted on out-of-fold row scores
of the labelled rows (inner GroupKFold by page: the labels of the scored fold's pages are hidden from the
method, so no row ever sees its own label). fit(train) + predict(world) for transfer tracks; run(world) refits.

Params: method (td.METHODS key), calib 'iso' | 'platt' | 'none', inner (folds, default 5), select 'arena' (exact
scorer points on the OOF rows), 'bayes' (t 0.5, band u/(1-u)), 'points' (stage 1: unsure scored 0), 'mf1', row 'prod' | 'min', everything else goes to the method.
"""
import os
import sys

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import GroupKFold

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import td  # noqa: E402
from api import Prediction  # noqa: E402

TS = (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7)
BANDS = (0.0, 0.05, 0.1, 0.15)


def decide(pt, t, band):
    out = np.where(pt >= t, "true", "false").astype(object)
    out[np.abs(pt - t) < band] = "unsure"
    return out


def rowscore(world, pf, how="prod"):
    if how == "min":
        r = np.ones(world.n)
        np.minimum.at(r, world.frow, pf)
        return r
    return td.row_prod(world, pf)


def oof_rows(world, fn, inner=5, how="prod"):
    """Row scores for the labelled rows, each computed with its page fold's labels hidden; also returns the
    per-fact scores of those folds (labelled facts only, NaN elsewhere)."""
    td.graph(world)  # label-free cache shared by every with_labels copy
    lab = world.labelled
    pages = np.unique(world.page[lab])
    prow = np.full(world.n, np.nan)
    pfo = np.full(world.n_facts, np.nan)
    k = min(inner, len(pages))
    if k < 2:
        return prow, pfo
    for _, te in GroupKFold(k).split(pages, groups=pages):
        hide = np.isin(world.page, pages[te]) & lab
        w2 = world.with_labels(lab & ~hide, world.label)
        pf = fn(w2)
        pr = rowscore(world, pf, how)
        prow[hide] = pr[hide]
        fh = hide[world.frow]
        pfo[fh] = pf[fh]
    return prow, pfo


class Variant:
    def __init__(self, method="accu", calib="iso", inner=5, select="points", row="prod", **params):
        self.method, self.calib, self.inner, self.select, self.row = method, calib, inner, select, row
        self.p = params
        self.chosen = []
        self.state = None

    def scores(self, world):
        pf, _, _ = td.run_method(world, self.method, **self.p)
        return np.clip(np.nan_to_num(pf, nan=0.5), 0.0, 1.0)

    def _cal(self, x):
        kind, m = self.cal_model
        if kind == "iso":
            return m.predict(x)
        if kind == "platt":
            return m.predict_proba(td.logit(x)[:, None])[:, 1]
        return x

    def fit(self, train):
        prow, _ = oof_rows(train, self.scores, self.inner, self.row)
        Y = train.label
        m = train.labelled & np.isin(Y, ["true", "false"]) & np.isfinite(prow)
        y = (Y[m] == "true").astype(float)
        if m.sum() < 10 or len(set(y.tolist())) < 2:  # one-class or tiny training labels: raw posterior, t=0.5
            self.cal_model = ("none", None)
            self.state = (0.5, 0.0)
            self.chosen.append(("fallback", 0.5, 0.0))
            return self
        if self.calib == "iso":
            self.cal_model = ("iso", IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(prow[m], y))
        elif self.calib == "platt":
            self.cal_model = ("platt", LogisticRegression(C=100.0).fit(td.logit(prow[m])[:, None], y))
        else:
            self.cal_model = ("none", None)
        tr = train.labelled & np.isfinite(prow)
        pt = self._cal(np.where(tr, prow, 0.5))
        ytr = Y[tr].astype(str)
        best = None
        if self.select == "bayes":  # argmax{2P(T)-1, 2P(F)-1, P(U)} with P(U) = training unsure rate u
            u = float(np.mean(ytr == "unsure"))
            self.state = (0.5, u / (1 - u))
            self.chosen.append(self.state)
            return self
        for t in TS:
            for b in (BANDS + (0.02,) if self.select == "arena" else BANDS):
                o = decide(pt[tr], t, b).astype(str)
                if self.select == "arena":  # exact A/score.py points: correct unsure +1, wrong unsure 0
                    sc = float(np.mean(np.where(o == ytr, 1, np.where(o == "unsure", 0, -1))))
                elif self.select == "points":  # stage-1 rule (unsure always 0)
                    sc = float(np.mean(np.where(o == "unsure", 0, np.where(o == ytr, 1, -1))))
                else:
                    sc = f1_score(ytr, o, labels=["true", "false", "unsure"], average="macro", zero_division=0)
                if best is None or sc > best[0] + 1e-12:
                    best = (sc, t, b)
        self.state = best[1:]
        self.chosen.append(best[1:])
        return self

    def predict(self, world):
        pf = self.scores(world)
        prow = rowscore(world, pf, self.row)
        pt = self._cal(prow)
        t, b = self.state
        out = decide(pt, t, b)
        nofacts = np.array([len(fs) == 0 for fs in world.facts])
        out[nofacts] = "unsure"
        # confidence of the returned label, floored at 0.5 (contract: decided rows carry 0.5..1)
        conf = np.where(out == "true", np.maximum(pt, 0.5), np.where(out == "false", np.maximum(1 - pt, 0.5), np.nan))
        return Prediction(out, conf, pf)

    def run(self, world):
        self.fit(world)
        return self.predict(world)
