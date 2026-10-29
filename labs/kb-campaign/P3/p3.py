"""P3 combination variants on top of F2's best chain (F2/f2var.py:Chain, imported read-only).

Spec P3/p3.py:Stack. Pipeline (everything learned on the track's labelled rows only):
  1. chain score per fact (own page excluded) -> monotone isotonic FactMap -> pf.
     oofmap=True: labelled facts get pf from FactMaps fitted without their page fold (honest stacker inputs).
  2. optional vote modulation (chain emissions): vw=[plugin specs] -> fact-level LR P(fact true | features),
     OOF by page on labelled facts; every vote's (unlabelled / unsure row) log emission is scaled by q**vg.
     The chain is then rerun with the scaled votes.
  3. optional fact decider: feats=[plugin specs] -> LR (C) or HGB on [logit pf, no-evidence flag, features],
     page-grouped OOF on labelled facts; offset=True keeps logit pf as a fixed offset (LR learns corrections only).
  4. row prob = product of fact probs (agg) -> decision:
     dec=None: F2 RowCal (rcal iso/platt, rule arena = argmax expected points, conf (1-u)pc >= 0.5 by construction)
     dec='<calib>:<policy>': F3 calib.Decider (calibrator + abstention policy) on the OOF row probs.
Plugin spec: 'path/file.py:func' (whole block) or 'path/file.py:func#0,2' (columns). Refs resolve from the run.py
cwd ($KBC), as the harness does. Single-class labelled worlds (Spilot-r, Sprac-r): fit falls back to fully labelled
practice (the transfer fit), recorded in chosen.
"""
import os
import sys
import timeit  # noqa: F401  stdlib first: F1/plugins.py puts F1/ (which has a timeit.py) on sys.path[0]

import numpy as np
import sklearn.ensemble  # noqa: F401
import sklearn.linear_model  # noqa: F401
import sklearn.pipeline  # noqa: F401
import sklearn.preprocessing  # noqa: F401
from sklearn.model_selection import GroupKFold

HERE = os.path.dirname(os.path.abspath(__file__))
KBC = os.path.dirname(HERE)
for _p in (os.path.join(KBC, "F2"), os.path.join(KBC, "F3")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import f2core as K  # noqa: E402
import f2var  # noqa: E402
from api import Prediction, feature_block  # noqa: E402

F2BEST = dict(engine="viterbi", d0=0.03, eps_a=0.0005, mono="fit", mono_a=10, pi_o=1, vote_lr=48)

_orig_ll = K.Key.loglik


def _ll(self, p):  # vote modulation hook; identical to F2 when p has no '_vw'
    out = _orig_ll(self, p)
    vw = p.get("_vw")
    if vw is not None:
        m = self.role == "V"
        out[:, m] = out[:, m] * vw[self.g[m]][None, :]
    return out


K.Key.loglik = _ll


def _logit(p):
    q = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(q / (1 - q))


def block(world, spec):
    c = world.__dict__.setdefault("_p3_blk", {})
    key = (spec, np.packbits(world.labelled).tobytes())
    if key not in c:
        ref, _, cols = spec.partition("#")
        X = feature_block(world, ref)
        if cols:
            X = X[:, [int(i) for i in cols.split(",")]]
        c[key] = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return c[key]


def dupes(world):
    """Exact-duplicate claims (same normalised row text, same fact position): every copy after the earliest
    (by date, then page) is a dupe (F1 td.graph's rule, recomputed here)."""
    tid = {}
    rcl = np.array([tid.setdefault(" ".join(t.casefold().split()), len(tid)) for t in world.text], np.int64)
    fcl = rcl[world.frow] * 64 + world.fidx[:, 1]
    order = np.lexsort((world.page[world.frow], world.date[world.frow]))
    _, first = np.unique(fcl[order], return_index=True)
    d = np.ones(world.n_facts, bool); d[order[first]] = False
    return d


def hmm2(world):
    """Plugin: logit of F2's #2 chain (HMM forward-backward engine, own page excluded) per fact; 0 where NaN."""
    c = f2var.Chain(engine="hmm", d0=0.1, eps_a=0.0001, mono="fit", mono_a=3, pi_o=1, vote_lr=48)
    c.prep(world)
    s = c.scores(world)
    return np.where(np.isnan(s), 0.0, _logit(np.nan_to_num(s, nan=0.5)))


class _Off:
    """LR with a fixed offset column (column 0 = logit pf): learns corrections only."""

    def __init__(self, C):
        self.C = C

    def fit(self, X, y):
        from scipy.optimize import minimize
        self.mu, self.sd = X[:, 1:].mean(0), X[:, 1:].std(0) + 1e-9
        Z = (X[:, 1:] - self.mu) / self.sd
        o = X[:, 0]

        def f(w):
            z = o + Z @ w[1:] + w[0]
            pz = 1 / (1 + np.exp(-z))
            ll = np.sum(np.logaddexp(0, z) - y * z) + 0.5 * np.sum(w[1:] ** 2) / self.C
            return ll, np.r_[np.sum(pz - y), Z.T @ (pz - y) + w[1:] / self.C]
        self.w = minimize(f, np.zeros(Z.shape[1] + 1), jac=True, method="L-BFGS-B").x
        return self

    def predict_proba(self, X):
        z = X[:, 0] + ((X[:, 1:] - self.mu) / self.sd) @ self.w[1:] + self.w[0]
        p = 1 / (1 + np.exp(-z))
        return np.c_[1 - p, p]


def _model(kind, C, offset):
    if offset:
        return _Off(C)
    if kind == "hgb":
        from sklearn.ensemble import HistGradientBoostingClassifier
        return HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, max_leaf_nodes=15,
                                              min_samples_leaf=20, l2_regularization=1.0, random_state=0)
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=3000))


def _folds(idx, g, k):
    k = min(k, len(set(g.tolist())))
    return list(GroupKFold(k).split(idx, groups=g)) if k >= 2 else []


class Stack(f2var.Chain):
    def __init__(self, feats=(), model="lr", C=1.0, offset=False, oofmap=True, vw=(), vg=1.0, vC=1.0,
                 dec=None, inner=4, dedup=False, **kw):
        super().__init__(**dict(F2BEST, **kw))
        self.feats, self.mkind, self.Cf, self.offset, self.oofmap = list(feats), model, C, offset, oofmap
        self.vw, self.vg, self.vC, self.dec, self.inner = list(vw), vg, vC, dec, inner
        self.dedup = dedup
        self.fmod = self.vmod = self.dmod = None

    # ---- vote modulation
    def _vX(self, world):
        return np.c_[tuple(block(world, s) for s in self.vw)]

    def _set_vw(self, world, q):
        w = np.clip(q, 1e-3, 1.0) ** self.vg if q is not None else np.ones(world.n_facts)
        if self.dedup:
            w = np.where(dupes(world), 0.0, w)  # a copy does not vote
        self.p["_vw"] = w

    def _fit_vw(self, world, y, idx, g):
        X = self._vX(world)
        q = np.full(world.n_facts, np.nan)
        for a, b in _folds(idx, g, self.inner):
            if len(set(y[idx[a]].tolist())) == 2:
                q[idx[b]] = _model("lr", self.vC, False).fit(X[idx[a]], y[idx[a]]).predict_proba(X[idx[b]])[:, 1]
        self.vmod = _model("lr", self.vC, False).fit(X[idx], y[idx])
        q = np.where(np.isnan(q), self.vmod.predict_proba(X)[:, 1], q)
        self._set_vw(world, q)

    # ---- fact decider
    def _fX(self, world, pf, s):
        return np.c_[(_logit(pf), np.isnan(s).astype(float), *(block(world, f) for f in self.feats))]

    def fit(self, world):
        self.p.pop("_vw", None)
        if not K.two_class(world):
            from world import practice_full
            self.chosen.append(("fallback", "practice"))
            world = practice_full()[0]
        self.prep(world)
        y = K.fact_targets(world)
        idx = np.flatnonzero(y >= 0)
        g = world.page[world.frow][idx]
        folds = _folds(idx, g, self.inner)
        if self.vw:
            self._fit_vw(world, y, idx, g)
        elif self.dedup:
            self._set_vw(world, None)
        s = self.scores(world)
        self.fm = K.FactMap(self.fmap_how).fit(s, y)
        pf = self.fm(s)
        if self.oofmap:
            for a, b in folds:
                yy = np.full_like(y, -1); yy[idx[a]] = y[idx[a]]
                pf[idx[b]] = K.FactMap(self.fmap_how).fit(s, yy)(s[idx[b]])
        if self.feats or self.offset:
            X = self._fX(world, pf, s)
            oof = np.full(world.n_facts, np.nan)
            for a, b in folds:
                if len(set(y[idx[a]].tolist())) == 2:
                    oof[idx[b]] = _model(self.mkind, self.Cf, self.offset).fit(X[idx[a]], y[idx[a]]).predict_proba(X[idx[b]])[:, 1]
            self.fmod = _model(self.mkind, self.Cf, self.offset).fit(X[idx], y[idx])
            pf = np.where(np.isnan(oof), self.fmod.predict_proba(X)[:, 1], oof)
        prow = K.row_prob(world, np.clip(pf, 1e-4, 1 - 1e-4), self.agg)
        if self.dec:
            import calib
            cal, pol = self.dec.split(":")
            tr = world.labelled & (np.array([len(f) for f in world.facts]) > 0)
            self.dmod = calib.Decider(cal, pol).fit(prow[tr], world.label[tr].astype(object), world.page[tr])
        else:
            self.rc = K.RowCal(self.rcal_how, self.rule).fit(prow, world)
            self.chosen.append((self.rc.t, self.rc.band))
        self.p.pop("_vw", None)
        return self

    def predict(self, world):
        if self.vw or self.dedup:
            self._set_vw(world, self.vmod.predict_proba(self._vX(world))[:, 1] if self.vw else None)
        s = self.scores(world)
        self.p.pop("_vw", None)
        pf = self.fm(s)
        if self.fmod is not None:
            pf = self.fmod.predict_proba(self._fX(world, pf, s))[:, 1]
        prow = K.row_prob(world, np.clip(pf, 1e-4, 1 - 1e-4), self.agg)
        if self.dmod is not None:
            out, conf, _ = self.dmod.decide(prow)
            out = np.asarray(out, dtype=object)
            nof = np.array([len(f) == 0 for f in world.facts])
            out[nof] = "unsure"
            conf = np.where(out == "unsure", np.nan, conf)
        else:
            out, conf = self.rc.predict(prow, world)
        return Prediction(out, conf, pf)
