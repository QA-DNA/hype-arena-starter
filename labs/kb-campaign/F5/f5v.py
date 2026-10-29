"""F5 model variant: V9-LR + F5 feature plugins (fp.py) + an optional unsure layer.

Params (on top of every v9.Variant param):
  plugins     list of fp.py plugin names appended after V9's 45 base columns (before stage-2 page suspicion)
  cols        optional {plugin: [column names]} to keep only some columns of a plugin
  unsure      None | 'ev': a row-level LR P(unsure | cues) trained on the labelled rows (out-of-fold by page for
              the selection), then P(T) = (1 - pu) * prow, P(F) = (1 - pu) * (1 - prow); the label maximises the
              expected arena points (true if 2 P(T) - 1 is the best of {2P(T)-1, 2P(F)-1, 0}, etc.). The selection
              on labelled rows still picks between this rule and V9's (threshold, band) grid by points.
              'conf': same P(unsure) model, labels from V9's rule, only the confidence uses P(T) / P(F)
  ucues       fp plugins whose columns (max over the row's facts) feed the unsure layer
  conf_pu     True: confidence = P(T) or P(F) including the unsure mass (else V9's prow / 1 - prow)
  min_unsure  fewer labelled unsure rows than this -> pu = their base rate (no model)
  stack       ['plugin.col', ...]: stage-3 row LR on logit(V9 prow) + row max of these columns (fewer free
              parameters than appending them to the fact model); sC its C
  scorer_pts  True: the selection scores points exactly like A/score.py (a correct unsure is +1); False (default,
              kept for the runs made before this was found): a correct unsure counts 0, as v9 select='points'
"""
import os
import sys

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fp  # noqa: E402

from api import Prediction  # noqa: E402
from variants import v9  # noqa: E402

UCUES = ["uns_tl", "src_text", "src_page"]


def ev_decide(prow, pu, scorer=False):
    """Expected points: true 2P(T)-1, false 2P(F)-1, unsure 0 (scorer=False) or P(U) (scorer=True: A/score.py
    gives +1 when an unsure prediction meets an unsure gold row)."""
    pT, pF = (1 - pu) * prow, (1 - pu) * (1 - prow)
    out = np.where(pT >= pF, "true", "false").astype(object)
    out[np.maximum(2 * pT - 1, 2 * pF - 1) < (pu if scorer else 0.0)] = "unsure"
    return out, pT, pF


class Variant(v9.Variant):
    def __init__(self, plugins=(), cols=None, unsure=None, ucues=tuple(UCUES), conf_pu=False, min_unsure=8,
                 uC=0.1, scorer_pts=False, stack=(), sC=1.0, **kw):
        kw.setdefault("select", "points")
        super().__init__(**kw)
        self.plugins, self.cols = list(plugins), dict(cols or {})
        self.unsure, self.ucues, self.conf_pu, self.min_unsure, self.uC = unsure, list(ucues), conf_pu, min_unsure, uC
        self.scorer_pts, self.stack, self.sC = scorer_pts, list(stack), sC

    def _block(self, world, name):
        X = getattr(fp, name)(world)
        if name in self.cols:
            X = X[:, [fp.COLS[name].index(c) for c in self.cols[name]]]
        return X

    def features(self, world, role=None):
        X = super().features(world, role)
        blocks = [self._block(world, p) for p in self.plugins]
        return np.c_[(X, *blocks)] if blocks else X

    # ---------------------------------------------------------------- unsure layer
    def _urows(self, world):
        F = np.c_[tuple(getattr(fp, c)(world) for c in self.ucues)]
        R = np.full((world.n, F.shape[1]), -1e9)
        np.maximum.at(R, world.frow, F)
        R[R == -1e9] = 0.0
        return np.c_[R, [len(f) for f in world.facts]]

    def _ufit(self, world):
        """-> (pu for every row, pu out-of-fold for labelled rows, fitted model or base rate)."""
        lab = world.labelled & np.array([x is not None for x in world.label])
        y = np.array([x == "unsure" for x in world.label]) & lab
        base = y[lab].mean() if lab.any() else 0.0
        if y.sum() < self.min_unsure or len(set(world.page[lab].tolist())) < 5:
            return np.full(world.n, base), np.full(world.n, base), base
        Xr = self._urows(world)
        mk = lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=self.uC))  # noqa: E731
        idx = np.flatnonzero(lab); g = world.page[idx]
        oof = np.full(world.n, base)
        for a, b in GroupKFold(min(5, len(set(g)))).split(idx, y[idx], g):
            if y[idx[a]].sum() >= 2:
                oof[idx[b]] = mk().fit(Xr[idx[a]], y[idx[a]]).predict_proba(Xr[idx[b]])[:, 1]
        m = mk().fit(Xr[idx], y[idx])
        return m.predict_proba(Xr)[:, 1], oof, m

    def _upredict(self, world):
        m = self.ustate
        if isinstance(m, float) or np.isscalar(m):
            return np.full(world.n, float(m))
        return m.predict_proba(self._urows(world))[:, 1]

    # ---------------------------------------------------------------- stage-3 fingerprint stack
    def _zrows(self, world, prow):
        cols = []
        for spec in self.stack:
            p, c = spec.split(".", 1)
            x = getattr(fp, p)(world)[:, fp.COLS[p].index(c)]
            r = np.full(world.n, -np.inf); np.maximum.at(r, world.frow, x); r[~np.isfinite(r)] = 0.0
            cols.append(r)
        q = np.clip(prow, 1e-4, 1 - 1e-4)
        return np.c_[(np.log(q / (1 - q)), *cols)]

    def _stack_fit(self, world, prow_tr, prow):
        """Row-level LR on [logit(calibrated V9 prow), row max of fingerprint columns], trained on labelled true /
        false rows with V9's out-of-fold prow; out-of-fold by page again for the selection."""
        Y = world.label
        m = world.labelled & np.isin(Y, ["true", "false"])
        y = (Y == "true").astype(int)
        idx = np.flatnonzero(m); g = world.page[idx]
        if len(set(y[idx].tolist())) < 2 or len(set(g.tolist())) < 5:
            return prow_tr, prow
        Ztr, Z = self._zrows(world, prow_tr), self._zrows(world, prow)
        mk = lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=self.sC))  # noqa: E731
        oof = np.full(world.n, np.nan)
        for a, b in GroupKFold(5).split(idx, y[idx], g):
            if len(set(y[idx[a]].tolist())) == 2:
                oof[idx[b]] = mk().fit(Ztr[idx[a]], y[idx[a]]).predict_proba(Ztr[idx[b]])[:, 1]
        sm = mk().fit(Ztr[idx], y[idx])
        self.sstate = sm
        p_tr = sm.predict_proba(Ztr)[:, 1]
        return np.where(np.isnan(oof), p_tr, oof), sm.predict_proba(Z)[:, 1]

    # ---------------------------------------------------------------- V9 path with the unsure layer
    def _rest(self, world, X, trf, yf):
        fpage = world.page[world.frow]
        g = fpage[trf]
        k = min(4, len(set(g)))
        oof, pf, m1 = self._fit_oof(X, trf, yf, g, k, self.model)
        m2 = iso = None
        if self.stage2:
            p1 = np.where(np.isnan(oof), pf, oof)
            X = np.c_[X, v9.page_susp(world, p1)]
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
        self.sstate = None
        if self.stack:
            prow_tr, prow = self._stack_fit(world, prow_tr, prow)
        pu = pu_tr = None
        if self.unsure in ("ev", "conf"):
            pu, pu_tr, self.ustate = self._ufit(world)
        ytr = Y[tr].astype(str)
        if self.scorer_pts:
            pts = lambda o: float(np.mean(np.where(o == ytr, 1, np.where(o == "unsure", 0, -1))))  # noqa: E731
        else:
            pts = lambda o: float(np.mean(np.where(o == "unsure", 0, np.where(o == ytr, 1, -1))))  # noqa: E731
        best = None
        for t in (0.3, 0.4, 0.5, 0.6, 0.7):
            for band in (0.0, 0.05, 0.1):
                o = v9.decide(prow_tr, t, band)[tr].astype(str)
                sc = pts(o)
                if best is None or sc > best[0]:
                    best = (sc, t, band)
        rule = "v9"
        if pu is not None and self.unsure == "ev":
            sc = pts(ev_decide(prow_tr, pu_tr, self.scorer_pts)[0][tr].astype(str))
            if sc >= best[0]:
                rule = "ev"
        self.chosen.append((best[1], best[2], rule))
        self.state = (m1, m2, iso, best[1], best[2])
        self.rule = rule
        return self._out(prow, pu, best[1], best[2]) + (prow, pf)

    def _out(self, prow, pu, t, band):
        if self.rule == "ev":
            out, pT, pF = ev_decide(prow, pu, self.scorer_pts)
        else:
            out = v9.decide(prow, t, band).astype(object)
            pT, pF = prow, 1 - prow
            if pu is not None and self.conf_pu:
                pT, pF = (1 - pu) * prow, (1 - pu) * (1 - prow)
        if not self.conf_pu:
            pT, pF = prow, 1 - prow
        conf = np.clip(np.where(out == "true", pT, pF), 0.5, 1.0)  # output contract: decided rows in [0.5, 1]
        return out, conf

    def predict(self, world):
        m1, m2, iso, t, band = self.state
        X = self.features(world)
        pf = m1.predict_proba(X)[:, 1]
        if m2 is not None:
            pf = m2.predict_proba(np.c_[X, v9.page_susp(world, pf)])[:, 1]
        prow = np.ones(world.n); np.multiply.at(prow, world.frow, pf)
        if iso is not None:
            prow = iso.predict(prow)
        if getattr(self, "sstate", None) is not None:
            prow = self.sstate.predict_proba(self._zrows(world, prow))[:, 1]
        pu = self._upredict(world) if self.unsure in ("ev", "conf") else None
        out, conf = self._out(prow, pu, t, band)
        return Prediction(out, conf, pf)

    def run(self, world):
        if self.selftrain:
            raise NotImplementedError("selftrain is not supported by the F5 variant")
        trf, yf = self.targets(world)
        if len(set(yf[trf].tolist())) < 2 or len(set(world.page[world.frow][trf].tolist())) < 4:
            # one-class (or nearly empty) public labels: fit on practice (public data) and transfer
            from world import practice_full
            self.run(practice_full()[0])
            self.chosen.append(("fallback-practice",))
            return self.predict(world)
        X = self.features(world)
        out, conf, prow, pf = self._rest(world, X, trf, yf)
        return Prediction(out, conf, pf)
