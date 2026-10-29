"""F5 fingerprints on top of F2's best standalone labeller (F2/f2var.py:Chain, viterbi engine; F2's code is
imported read-only). Spec: F5/onf2.py:OnChain.

Chain gives a per-fact score (own page excluded) -> isotonic P(fact true) -> row product -> RowCal (arena rule).
Two optional F5 layers, both trained on the world's labelled rows only, out of fold by page for the training side:
  fact / plugins  fact-level LR on [logit(Chain pf), no-evidence flag, F5 columns ('plugin.col') or whole F5
                  plugin blocks]; fC its C. Targets = v9 fact targets.
  stack           row-level LR on [logit(row prob), row max of F5 columns ('plugin.col')]; sC its C.
  flr / slr       True: run the fact / row layer with no F5 column (control: the cost of the layer itself).
Chain params default to F2's best (BEST); any Chain / Std param can be overridden.
Known optimism (selection side only): Chain's isotonic fact map is fitted in sample on the labelled facts before the
out-of-fold F5 layer, so the OOF inputs of the RowCal fit are slightly optimistic. Unlabelled test rows never enter.
"""
import os
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(os.path.dirname(HERE), "F2")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import fp  # noqa: E402
import f2core as K  # noqa: E402
import f2var  # noqa: E402
from api import Prediction  # noqa: E402

BEST = dict(engine="viterbi", eps_a=0.0005, lam_scale=0.7, mono=0.1, pi_o=1, vote_lr=48)


def _lr(C):
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=C))


def _logit(p):
    q = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(q / (1 - q))


def _oof(X, y, idx, g, k, C):
    """-> (out-of-fold P(y=1) on idx (NaN elsewhere / when a fold is one-class), model fitted on all of idx)."""
    oof = np.full(len(X), np.nan)
    for a, b in GroupKFold(k).split(idx, y[idx], g):
        if len(set(y[idx[a]].tolist())) == 2:
            oof[idx[b]] = _lr(C).fit(X[idx[a]], y[idx[a]]).predict_proba(X[idx[b]])[:, 1]
    return oof, _lr(C).fit(X[idx], y[idx])


def _col(world, spec):
    p, c = spec.split(".", 1)
    return getattr(fp, p)(world)[:, fp.COLS[p].index(c)]


class OnChain(f2var.Chain):
    def __init__(self, fact=(), plugins=(), fC=0.1, stack=(), sC=1.0, flr=False, slr=False, **kw):
        super().__init__(**dict(BEST, **kw))
        self.fact, self.plugins, self.fC, self.stack, self.sC = list(fact), list(plugins), fC, list(stack), sC
        self.flr, self.slr = flr, slr  # True: run the layer even with no F5 column (control for the layer itself)
        self.fmod = self.smod = None

    def _fx(self, world, pf, s):
        cols = [_col(world, c) for c in self.fact] + [getattr(fp, p)(world) for p in self.plugins]
        return np.c_[(_logit(pf), np.isnan(s).astype(float), *cols)]

    def _z(self, world, prow):
        cols = []
        for spec in self.stack:
            r = np.full(world.n, -np.inf)
            np.maximum.at(r, world.frow, _col(world, spec))
            r[~np.isfinite(r)] = 0.0
            cols.append(r)
        return np.c_[(_logit(prow), *cols)]

    def fit(self, world):
        if not K.two_class(world):  # one-class public labels: transfer fit on practice (as F2's Std does)
            from world import practice_full
            self.chosen.append(("fallback", "practice"))
            world = practice_full()[0]
        self.prep(world)
        s = self.scores(world)
        y = K.fact_targets(world)
        self.fm = K.FactMap(self.fmap_how).fit(s, y)
        pf = self.fm(s)
        self.fmod = self.smod = None
        if self.fact or self.plugins or self.flr:
            X = self._fx(world, pf, s)
            idx = np.flatnonzero(y >= 0)
            g = world.page[world.frow][idx]
            if len(set(y[idx].tolist())) == 2 and len(set(g.tolist())) >= 4:
                oof, self.fmod = _oof(X, y, idx, g, min(4, len(set(g.tolist()))), self.fC)
                pf = np.where(np.isnan(oof), self.fmod.predict_proba(X)[:, 1], oof)
        prow = K.row_prob(world, pf, self.agg)
        if self.stack or self.slr:
            Y = world.label
            m = world.labelled & np.isin(Y, ["true", "false"])
            yr = (Y == "true").astype(int)
            idx = np.flatnonzero(m)
            g = world.page[idx]
            if len(set(yr[idx].tolist())) == 2 and len(set(g.tolist())) >= 5:
                Z = self._z(world, prow)
                oof, self.smod = _oof(Z, yr, idx, g, 5, self.sC)
                prow = np.where(np.isnan(oof), self.smod.predict_proba(Z)[:, 1], oof)
        self.rc = K.RowCal(self.rcal_how, self.rule).fit(prow, world)
        self.chosen.append((self.rc.t, self.rc.band, self.fmod is not None, self.smod is not None))
        return self

    def predict(self, world):
        s = self.scores(world)
        pf = self.fm(s)
        if self.fmod is not None:
            pf = self.fmod.predict_proba(self._fx(world, pf, s))[:, 1]
        prow = K.row_prob(world, pf, self.agg)
        if self.smod is not None:
            prow = self.smod.predict_proba(self._z(world, prow))[:, 1]
        out, conf = self.rc.predict(prow, world)
        return Prediction(out, conf, pf)
