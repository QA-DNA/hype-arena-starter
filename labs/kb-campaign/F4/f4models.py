"""F4 learned models on top of V9 (variants/v9.py) and the F4 graph.

G9 (V9 subclass, select='points' by default):
  mil      : EM rounds of MIL / noisy-OR blame. Facts of labelled multi-fact false rows enter training twice,
             as false with weight blame and as true with weight 1 - blame, blame = noisy-OR P(fact false | row
             false) from the previous round's out-of-fold fact P(true) (mil_kind "post"; "share" = q / sum q).
             V9 drops these 75 practice rows.
  pseudo   : self-training rounds that ADD confident unlabelled facts to the training set (weight pw, fact
             thresholds phi / plo); V9's own selftrain only re-derives role features.
  lap      : graph-regularised logistic regression: Laplacian penalty lap * n * mean over edges of
             (logit_i - logit_j)^2 over same-claim support edges (time kernel, other page) and same-page edges
             (weight lap_page), on all facts of the world (labelled and unlabelled); lap_tau = edge time kernel.
  select   : 'points' = arena points of A/score.py (correct unsure +1, wrong unsure 0) for threshold and band.
CoTrain: co-training of a temporal view (V9 timeline features) and a source/page view (page latent-lie, page
  position and size, row size, lexicon features); each round each view hands its most confident unlabelled facts
  to the shared training set; final fact logit = sum of the view logits minus the prior logit.
"""
import os
import sys

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(os.path.dirname(HERE), "harness"))
from api import Base, Prediction  # noqa: E402
from variants import v9  # noqa: E402
import f4graph as G  # noqa: E402
from f4graph import conf_of  # noqa: E402
import f4lex as LX  # noqa: E402


# ------------------------------------------------------------------ graph-regularised LR
def laplacian(world, page_w=1.0, tau=30.0):
    Wp, _ = G.edges(world, tau)
    W = (Wp + Wp.T) * 0.5
    if page_w:
        R, C = [], []
        for idx in v9.page_members(world).values():
            rows = world.frow[idx]
            a, b = np.meshgrid(idx, idx, indexing="ij")
            m = rows[:, None] != rows[None, :]
            R.append(a[m]); C.append(b[m])
        if R:
            R, C = np.concatenate(R), np.concatenate(C)
            W = W + sp.csr_matrix((np.full(len(R), page_w), (R, C)), shape=W.shape)
    d = np.asarray(W.sum(1)).ravel()
    return (sp.diags(d) - W).tocsr(), float(W.sum())


class LapLR:
    """Logistic regression with an L2 penalty plus lap * n_train * beta' (X' L X / sum W) beta over the world's
    graph. Xall: features of every fact of the world (unscaled)."""

    def __init__(self, Xall, L, wsum, lap=1.0, C=0.5):
        self.Xall, self.L, self.wsum, self.lap, self.C = Xall, L, wsum, lap, C

    def fit(self, X, y, sample_weight=None):
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, float)
        self.sc = StandardScaler().fit(X)
        Xs = self.sc.transform(X)
        Xa = self.sc.transform(self.Xall)
        M = Xa.T @ (self.L @ Xa) / max(self.wsum, 1e-9)
        M = 0.5 * (M + M.T)
        n, k = Xs.shape
        lam = self.lap * w.sum()

        def f(theta):
            b, beta = theta[0], theta[1:]
            z = Xs @ beta + b
            lz = np.logaddexp(0, z)
            loss = np.sum(w * (lz - y * z))
            pen = 0.5 * beta @ beta / self.C + lam * beta @ M @ beta
            r = w * (1 / (1 + np.exp(-z)) - y)
            g = np.r_[r.sum(), Xs.T @ r + beta / self.C + 2 * lam * M @ beta]
            return loss + pen, g
        res = minimize(f, np.zeros(k + 1), jac=True, method="L-BFGS-B", options=dict(maxiter=500))
        self.b, self.beta = res.x[0], res.x[1:]
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X):
        z = self.sc.transform(X) @ self.beta + self.b
        p = 1 / (1 + np.exp(-z))
        return np.c_[1 - p, p]


def make_w(model, Xall=None, L=None, wsum=None, lap=0.0):
    if lap and Xall is not None:
        C = float(model[3:]) if model.startswith("lrC") else 0.5
        return LapLR(Xall, L, wsum, lap, C)
    return v9.make(model)


def fit_w(est, X, y, w):
    if isinstance(est, (LapLR, HistGradientBoostingClassifier)):
        return est.fit(X, y, sample_weight=w)
    return est.fit(X, y, logisticregression__sample_weight=w)


# ------------------------------------------------------------------ G9
class Variant(v9.Variant):
    def __init__(self, mil=0, mil_kind="post", pseudo=0, pw=0.5, phi=0.97, plo=0.1, lap=0.0, lap_page=1.0, lap_tau=30.0, select="points",
                 transfer="plain", match_seeds=1, **kw):
        super().__init__(select=select, **kw)
        self.mil, self.mil_kind, self.pseudo, self.pw, self.phi, self.plo = mil, mil_kind, pseudo, pw, phi, plo
        self.lap, self.lap_page, self.lap_tau = lap, lap_page, lap_tau
        self.transfer, self.match_seeds = transfer, match_seeds

    def _train(self, world, trf, yf, pf_prev, pseudo_on):
        idx = np.where(trf)[0]
        y = yf[idx].astype(float)
        w = np.ones(len(idx))
        self._nbase = len(idx)
        if self.mil and pf_prev is not None:
            nf = np.array([len(fs) for fs in world.facts])
            fm = np.where(world.labelled[world.frow] & (world.label[world.frow] == "false") & (nf[world.frow] > 1))[0]
            if len(fm):
                b = G.row_blame(world, 1 - pf_prev)[2 if self.mil_kind == "post" else 1][fm]
                idx = np.r_[idx, fm, fm]; y = np.r_[y, np.zeros(len(fm)), np.ones(len(fm))]
                w = np.r_[w, b, 1 - b]
        if pseudo_on and pf_prev is not None:
            un = ~world.labelled[world.frow]
            hi = np.where(un & (pf_prev >= self.phi))[0]; lo = np.where(un & (pf_prev <= self.plo))[0]
            idx = np.r_[idx, hi, lo]; y = np.r_[y, np.ones(len(hi)), np.zeros(len(lo))]
            w = np.r_[w, np.full(len(hi) + len(lo), self.pw)]
        return idx, y, w

    def _fit_oof_w(self, world, X, idx, y, w):
        g = world.page[world.frow[idx]]
        k = min(4, len(set(g)))
        lapargs = {}
        if self.lap:
            L, ws = laplacian(world, self.lap_page, self.lap_tau)
            lapargs = dict(Xall=X, L=L, wsum=ws, lap=self.lap)
        oof = np.full(world.n_facts, np.nan)
        lab = np.arange(len(idx)) < self._nbase  # only the base labelled targets get OOF values
        for a, b in GroupKFold(k).split(X[idx], y, g):
            if len(set(y[a])) < 2:
                continue
            est = fit_w(make_w(self.model, **lapargs), X[idx[a]], y[a], w[a])
            bb = b[lab[b]]
            oof[idx[bb]] = est.predict_proba(X[idx[bb]])[:, 1]
        full = fit_w(make_w(self.model, **lapargs), X[idx], y, w)
        return oof, full.predict_proba(X)[:, 1], full

    def _rest_w(self, world, X, trf, yf, pf_prev, pseudo_on):
        idx, y, w = self._train(world, trf, yf, pf_prev, pseudo_on)
        oof, pf, m1 = self._fit_oof_w(world, X, idx, y, w)
        m2 = iso = None
        if self.stage2:
            p1 = np.where(np.isnan(oof), pf, oof)
            X2 = np.c_[X, v9.page_susp(world, p1)]
            oof, pf, m2 = self._fit_oof_w(world, X2, idx, y, w)
        pf_tr = np.where(np.isnan(oof), pf, oof)
        prow_tr = np.ones(world.n); np.multiply.at(prow_tr, world.frow, pf_tr)
        prow = np.ones(world.n); np.multiply.at(prow, world.frow, pf)
        iso, t, band, pc = G.select_rows(world, prow_tr, prow, self.calib) if self.select == "points" else \
            (None, None, None, None)
        if self.select != "points":
            raise ValueError("G9 supports select='points' only")
        self.chosen.append((t, band))
        self.state = (m1, m2, iso, t, band)
        out = G.decide(pc, t, band)
        return out, conf_of(out, pc), pc, pf_tr

    def run(self, world):
        trf, yf = self.targets(world)
        if len(set(yf[trf].tolist())) < 2 or not G.two_classes(world):  # one-class refit world: transfer
            return self.fit(G.practice_world()).predict(world)
        X = self.features(world)
        rounds = max(self.mil, self.pseudo, self.selftrain)
        pf_prev = None
        for r in range(rounds + 1):
            if r and r <= self.selftrain:
                role = np.full(world.n, "", dtype=object)
                role[prow >= self.hi] = "true"; role[prow <= self.lo] = "false"
                X = self.features(world, role)
            out, conf, prow, pf_prev = self._rest_w(world, X, trf, yf, pf_prev, 0 < r <= self.pseudo)
        return Prediction(out, conf, pf_prev)

    def fit(self, train_world):
        """transfer 'plain': V9 fit (run on the training world, every row an anchor). 'match': keep the training
        world and fit at predict time under the target's anchor density (see _fit_matched)."""
        if self.transfer == "match":
            self._train_world = train_world
            return self
        return super().fit(train_world)

    def _fit_matched(self, tw0, d, seed=0):
        """Density-matched transfer fit. A random share d of the training world's pages (d = the target world's
        labelled row share, public) act as anchors; features of every fact come from those anchors only; the
        training targets are the OTHER rows with their known labels, i.e. exactly the target's test condition
        (unlabelled rows seen through sparse anchors). Parameter-free; mil rounds apply, pseudo/selftrain do not."""
        rng = np.random.RandomState(seed)
        lab_pages = rng.rand(tw0.n_pages) < d
        if not lab_pages.any():
            lab_pages[rng.randint(tw0.n_pages)] = True
        sub = lab_pages[tw0.page]
        full = np.array([x if x is not None else "unsure" for x in tw0.label], dtype=object)
        X = self.features(tw0.with_labels(sub, full))
        tw = tw0.with_labels(~sub, full)
        trf, yf = self.targets(tw)
        pf_prev = None
        for r in range(self.mil + 1):
            out, conf, prow, pf_prev = self._rest_w(tw, X, trf, yf, pf_prev, False)

    def predict(self, world):
        if self.transfer == "match" and getattr(self, "_train_world", None) is not None:
            d = float(np.mean(world.labelled))
            ps, ts, bs = [], [], []
            for seed in range(self.match_seeds):  # bagging over anchor subsamples: mean calibrated P(true)
                self._fit_matched(self._train_world, d, seed)
                p = self._predict_state(world)
                ps.append(p[0]); ts.append(self.state[3]); bs.append(self.state[4])
            prow, pf = np.mean(ps, 0), p[1]
            out = G.decide(prow, float(np.mean(ts)), float(np.mean(bs)))
            return Prediction(out, conf_of(out, prow), pf)
        prow, pf = self._predict_state(world)
        out = G.decide(prow, self.state[3], self.state[4])
        return Prediction(out, conf_of(out, prow), pf)

    def _predict_state(self, world):
        m1, m2, iso, t, band = self.state
        X = self.features(world)
        for r in range(self.selftrain + 1):
            if r:
                role = np.full(world.n, "", dtype=object)
                role[prow >= self.hi] = "true"; role[prow <= self.lo] = "false"
                X = self.features(world, role)
            pf = m1.predict_proba(X)[:, 1]
            if m2 is not None:
                pf = m2.predict_proba(np.c_[X, v9.page_susp(world, pf)])[:, 1]
            prow = np.ones(world.n); np.multiply.at(prow, world.frow, pf)
            if iso is not None:
                prow = iso.predict(prow)
        return prow, pf


# ------------------------------------------------------------------ co-training
TIME_DROP = [16, 17, 18]  # page and row-size columns of the V9 base block go to the source view


def source_view(world, role=None):
    pl = G.page_lie(world, role)
    pm = v9.page_members(world)
    size = np.zeros(world.n_facts); pos = np.zeros(world.n_facts)
    for idx in pm.values():
        rows = world.frow[idx]
        ur = np.unique(rows)
        size[idx] = np.log1p(len(ur))
        rank = {r: k / max(1, len(ur) - 1) for k, r in enumerate(ur)}
        pos[idx] = [rank[r] for r in rows]
    nf = np.array([len(fs) for fs in world.facts])[world.frow]
    return np.c_[pl, size, pos, np.log(nf), LX.lex_small(world)]


class CoTrain(Base):
    def __init__(self, rounds=3, per_round=0.02, C=0.5, calib=True):
        self.rounds, self.per_round, self.C, self.calib = rounds, per_round, C, calib
        self.chosen = []

    def _views(self, world):
        XT = np.delete(v9.fact_feats(world), TIME_DROP, axis=1)
        XS = source_view(world)
        return XT, XS

    def _lr(self):
        return v9.make(f"lrC{self.C}")

    def _fit(self, X, idx, y, w):
        return fit_w(self._lr(), X[idx], y, w)

    def run(self, world):
        if not G.two_classes(world):  # one-class refit world: transfer from practice
            return self.fit(G.practice_world()).predict(world)
        XT, XS = self._views(world)
        trf, yf = v9.Variant.targets(world)
        base_idx = np.where(trf)[0]
        base_y = yf[base_idx].astype(float)
        un = np.where(~world.labelled[world.frow])[0]
        pseudo = {}
        prior = np.clip(base_y.mean(), 0.05, 0.95)
        lp = np.log(prior / (1 - prior))
        for r in range(self.rounds + 1):
            idx = np.r_[base_idx, np.array(list(pseudo), int)]
            y = np.r_[base_y, np.array(list(pseudo.values()), float)]
            w = np.ones(len(idx))
            mT, mS = self._fit(XT, idx, y, w), self._fit(XS, idx, y, w)
            if r == self.rounds:
                break
            k = max(1, int(self.per_round * len(un)))
            for m, X in ((mT, XT), (mS, XS)):
                cand = np.array([u for u in un if u not in pseudo], int)
                if not len(cand):
                    break
                p = m.predict_proba(X[cand])[:, 1]
                kt = max(1, int(round(k * prior))); kf = max(1, k - kt)
                for u in cand[np.argsort(-p)[:kt]]:
                    pseudo[int(u)] = 1.0
                for u in cand[np.argsort(p)[:kf]]:
                    pseudo[int(u)] = 0.0
        self.models = (mT, mS, lp)
        # out-of-fold fact scores for the labelled rows (row calibration and threshold)
        g = world.page[world.frow[base_idx]]
        oofT = np.full(world.n_facts, np.nan); oofS = np.full(world.n_facts, np.nan)
        for a, b in GroupKFold(min(4, len(set(g)))).split(base_idx, base_y, g):
            ia = np.r_[base_idx[a], np.array(list(pseudo), int)]
            ya = np.r_[base_y[a], np.array(list(pseudo.values()), float)]
            if len(set(ya)) < 2:
                continue
            oofT[base_idx[b]] = self._fit(XT, ia, ya, None).predict_proba(XT[base_idx[b]])[:, 1]
            oofS[base_idx[b]] = self._fit(XS, ia, ya, None).predict_proba(XS[base_idx[b]])[:, 1]
        pf = self._combine(mT.predict_proba(XT)[:, 1], mS.predict_proba(XS)[:, 1], lp)
        pf_oof = self._combine(oofT, oofS, lp)
        pf_tr = np.where(np.isnan(pf_oof), pf, pf_oof)
        prow_tr = np.ones(world.n); np.multiply.at(prow_tr, world.frow, pf_tr)
        prow = np.ones(world.n); np.multiply.at(prow, world.frow, pf)
        iso, t, band, pc = G.select_rows(world, prow_tr, prow, self.calib)
        self.chosen.append((t, band))
        self.state = (iso, t, band)
        out = G.decide(pc, t, band)
        return Prediction(out, conf_of(out, pc), pf)

    @staticmethod
    def _combine(pT, pS, lp):
        lg = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))  # noqa: E731
        z = lg(pT) + lg(pS) - lp
        return 1 / (1 + np.exp(-z))

    def fit(self, train_world):
        self.run(train_world)
        return self

    def predict(self, world):
        mT, mS, lp = self.models
        iso, t, band = self.state
        XT, XS = self._views(world)
        pf = self._combine(mT.predict_proba(XT)[:, 1], mS.predict_proba(XS)[:, 1], lp)
        prow = np.ones(world.n); np.multiply.at(prow, world.frow, pf)
        pc = iso.predict(prow) if iso is not None else prow
        out = G.decide(pc, t, band)
        return Prediction(out, conf_of(out, pc), pf)


if __name__ == "__main__":
    rng = np.random.RandomState(0)
    X = rng.randn(200, 3); y = (X[:, 0] + 0.3 * rng.randn(200) > 0).astype(float)
    L = sp.csr_matrix((200, 200))
    m = LapLR(X, L, 1.0, lap=0.0, C=1.0).fit(X, y)
    ref = LogisticRegression(C=1.0).fit(StandardScaler().fit_transform(X), y)
    assert np.allclose(m.beta, ref.coef_[0], atol=1e-3), (m.beta, ref.coef_)
    print("LapLR with lap=0 matches sklearn LR; selfcheck ok")
