"""F2 standalone labellers. Spec: F2/f2var.py:<Class>. Each computes a per-fact score that excludes the fact's
own page, maps it to P(fact true) with a monotone map fitted on labelled facts, multiplies over the row's facts,
calibrates on labelled rows and picks (threshold, unsure band) by arena points on labelled rows.
fit(train) learns hazard, maps and threshold; predict(world) applies them (transfer); run(world) = both."""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import f2core as K  # noqa: E402
from api import Prediction  # noqa: E402

F2_VERSION = 5  # bumped when f2core / f2feat behaviour changes (src_hash covers this file only)
CHAIN_DEF = dict(eps_a=0.01, eps_f=0.2, vote_lr=4.0, pi_o=0.5, mono=1.0, wm=0.0,
                 H=50.0, w_v=1.0, C=2.0, C_o=1.0, mono_pen=0.0, c=1.0)


class Std:
    fmap_how = "iso"
    rcal_how = "iso"

    def __init__(self, fmap="iso", rcal="iso", agg="prod", rule="arena"):
        self.fmap_how, self.rcal_how, self.agg, self.rule = fmap, rcal, agg, rule
        self.chosen = []

    def prep(self, world):  # learn label-derived parameters (hazard) on the training world
        pass

    def scores(self, world):
        raise NotImplementedError

    def train_scores(self, world):
        return self.scores(world)

    def fit(self, world):
        if not K.two_class(world):  # one-class public labels: fall back to the transfer fit on practice
            from world import practice_full
            self.chosen.append(("fallback", "practice"))
            world = practice_full()[0]
        self.prep(world)
        s = self.train_scores(world)
        y = K.fact_targets(world)
        self.fm = K.FactMap(self.fmap_how).fit(s, y)
        prow = K.row_prob(world, self.fm(s), self.agg)
        self.rc = K.RowCal(self.rcal_how, self.rule).fit(prow, world)
        self.chosen.append((self.rc.t, self.rc.band))
        return self

    def predict(self, world):
        s = self.scores(world)
        pf = self.fm(s)
        prow = K.row_prob(world, pf, self.agg)
        out, conf = self.rc.predict(prow, world)
        return Prediction(out, conf, pf)

    def run(self, world):
        self.fit(world)
        return self.predict(world)


# ---------------------------------------------------------------- 1. point resolvers and kernels
class Point(Std):
    """mode kernel|latest|nearest|bracket; kernel exp|tri|box, tau days, beta (weight of later evidence),
    wa anchor weight, wu vote weight, wf false-anchor weight. Score = (sp - sm) / (sp + sm), NaN if none."""

    def __init__(self, mode="kernel", kernel="exp", tau=30.0, beta=1.0, wa=1.0, wu=0.3, wf=0.0, **kw):
        super().__init__(**kw)
        self.p = dict(mode=mode, kernel=kernel, tau=float(tau), beta=beta, wa=wa, wu=wu, wf=wf)

    def scores(self, world):
        sp, sm = K.point_scores(world, self.p)
        tot = sp + sm
        return np.where(tot > 0, (sp - sm) / np.where(tot > 0, tot, 1), np.nan)


# ---------------------------------------------------------------- 2. bracket lookup tables
class Bracket(Std):
    """P(true | before/same/after cell) from labelled facts, Beta-smoothed toward the coarser cell (anchor
    symbols only) and the global rate; training scores are inner-fold (by page) out-of-fold."""

    def __init__(self, vote_fallback=True, gapb=0, alpha=4.0, inner=5, **kw):
        super().__init__(**kw)
        self.vf, self.gapb, self.alpha, self.inner = vote_fallback, gapb, alpha, inner

    def coarse(self, c):
        return "".join(ch for ch in c if ch in "YN-yn")

    def _cells(self, world):
        c = world.__dict__.setdefault("_f2_cells", {})
        k = (self.vf, self.gapb)
        if k not in c:
            c[k] = K.bracket_cells(world, self.vf, self.gapb or None)
        return c[k]

    def _table(self, cells, y, m):
        g = float(np.mean(y[m])) if m.any() else 0.85
        cnt1, cnt0 = {}, {}
        for lvl in (0, 1):
            for c, t in zip(cells[m] if lvl == 0 else [self.coarse(x) for x in cells[m]], y[m]):
                key = (lvl, c)
                cnt1[key] = cnt1.get(key, 0) + t
                cnt0[key] = cnt0.get(key, 0) + 1
        return g, cnt1, cnt0

    def _apply(self, tab, cells):
        g, c1, c0 = tab
        a = self.alpha
        out = np.empty(len(cells))
        for i, c in enumerate(cells):
            cc = self.coarse(c)
            pc = (c1.get((1, cc), 0) + a * g) / (c0.get((1, cc), 0) + a)
            out[i] = (c1.get((0, c), 0) + a * pc) / (c0.get((0, c), 0) + a)
        return out

    def train_scores(self, world):
        cells = np.array(self._cells(world), dtype=object)
        y = K.fact_targets(world)
        m = y >= 0
        out = self._apply(self._table(cells, y, m), cells)
        fpage = world.page[world.frow]
        lp = np.unique(fpage[m])
        if len(lp) >= self.inner:
            rng = np.random.RandomState(0)
            fold = dict(zip(lp, rng.permutation(len(lp)) % self.inner))
            fo = np.array([fold.get(p, -1) for p in fpage])
            for f in range(self.inner):
                te = fo == f
                out[te] = self._apply(self._table(cells, y, m & ~te), cells[te])
        self.tab = self._table(cells, y, m)
        return out

    def scores(self, world):
        cells = np.array(self._cells(world), dtype=object)
        return self._apply(self.tab, cells)


# ---------------------------------------------------------------- 3-5. chain engines
class Chain(Std):
    """engine hmm (sum-product posterior that the fact holds at its date) | viterbi (max-marginal margin) |
    tecore (max-weight consistent timeline, anchors hard, false anchors forbidden; margin) | seg (penalised
    segmentation, BIC-like penalty c * log n; sweep = list of c -> share of the sweep where the fact agrees).
    lam: 'fit' (hazard MLE on labelled anchors, by lam_by) or days**-1; lam_scale multiplies it."""

    def __init__(self, engine="hmm", lam="fit", lam_by="kind", lam_scale=1.0, sweep=None, mono_a=10.0, d0=0.1,
                 **kw):
        cal = {k: kw.pop(k) for k in ("fmap", "rcal", "agg", "rule") if k in kw}
        super().__init__(**cal)
        self.engine, self.lam_cfg, self.lam_by, self.lam_scale = engine, lam, lam_by, lam_scale
        self.sweep = sweep
        self.p = dict(CHAIN_DEF, **kw)
        self.hz = None
        self.mono_a, self.d0 = mono_a, d0

    def prep(self, world):
        if self.lam_cfg == "fit":
            self.hz = K.Hazard(self.lam_by, mono_a=self.mono_a, d0=self.d0).fit(world)
            self.chosen.append(("lam_glob", round(self.hz.glob, 6)))

    def lam(self, key):
        base = self.hz.lam(key) if self.hz is not None else float(self.lam_cfg)
        return base * self.lam_scale

    def kp(self, k):
        """Per-key params: mono='fit' takes the learned downward-switch weight of the key's kind (all ordered
        kinds), else the fixed mono."""
        if self.p.get("mono") == "fit":
            d = self.hz.down.get(k.kind, 1.0) if self.hz is not None else 1.0
            return dict(self.p, mono=d, mono_all=True)
        return self.p

    def scores(self, world):
        out = np.full(world.n_facts, np.nan)
        for k in K.keys_of(world):
            if len(np.unique(k.page)) < 2:
                continue  # no other-page evidence for any fact of this key: NaN
            lam = self.lam(k)
            P = self.kp(k)
            if self.engine == "hmm":
                post = K.hmm_post(k, P, lam)
                for b in range(k.n):
                    out[k.g[b]] = float(post[int(k.page[b]), int(k.tix[b])] @ k.Ag[:, b])
            elif self.engine == "seg" and self.sweep:
                acc = np.zeros(k.n); cnt = 0
                for c in self.sweep:
                    mm = K.max_marginals(k, dict(P, c=c), lam, "seg")
                    for b in range(k.n):
                        v, _ = mm[int(k.page[b]), int(k.tix[b])]
                        acc[b] += float(k.Ag[int(v.argmax()), b] > 0.5)
                    cnt += 1
                out[k.g] = acc / cnt
            else:
                mm = K.max_marginals(k, P, lam, self.engine)
                for b in range(k.n):
                    v, _ = mm[int(k.page[b]), int(k.tix[b])]
                    ag = k.Ag[:, b]
                    a = v[ag > 0.5].max() if (ag > 0.5).any() else -1e9
                    d = v[ag < 0.5].max() if (ag < 0.5).any() else -1e9
                    out[k.g[b]] = float(np.clip(a - d, -60, 60))
        return out


# ---------------------------------------------------------------- 7. combinations inside the family
class Combo(Std):
    """Logistic regression over F2 plugin columns (f2feat.ALL by default) and optional bracket one-hots,
    fitted on labelled facts with inner page-grouped OOF for the training scores. Score = LR P(fact true)."""

    def __init__(self, blocks=("hmm", "viterbi", "stale", "bracket"), C=0.3, inner=4, **kw):
        super().__init__(**kw)
        self.blocks, self.Cr, self.inner = list(blocks), C, inner

    def X(self, world):
        import f2feat
        return np.c_[tuple(f2feat.BLOCKS[b](world) for b in self.blocks)]

    def _lr(self):
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        return make_pipeline(StandardScaler(), LogisticRegression(C=self.Cr, max_iter=3000))

    def train_scores(self, world):
        from sklearn.model_selection import GroupKFold
        X = self.X(world)
        y = K.fact_targets(world)
        m = y >= 0
        self.lr = self._lr().fit(X[m], y[m])
        out = self.lr.predict_proba(X)[:, 1]
        idx = np.flatnonzero(m)
        g = world.page[world.frow][idx]
        k = min(self.inner, len(set(g)))
        if k >= 2:
            for a, b in GroupKFold(k).split(idx, groups=g):
                if len(set(y[idx[a]])) == 2:
                    out[idx[b]] = self._lr().fit(X[idx[a]], y[idx[a]]).predict_proba(X[idx[b]])[:, 1]
        return out

    def scores(self, world):
        return self.lr.predict_proba(self.X(world))[:, 1]


class BracketHMM(Bracket):
    """2-D lookup: bracket cell x HMM-posterior bin (nb equal-width bins of f2feat.hmm post), Beta-smoothed
    toward the HMM bin alone (backoff='hmm') or toward the bracket cell alone (backoff='cell')."""

    def __init__(self, nb=10, backoff="hmm", **kw):
        super().__init__(**kw)
        self.nb, self.backoff = nb, backoff

    def coarse(self, c):
        return c.split("|")[1] if self.backoff == "hmm" else Bracket.coarse(self, c.split("|")[0])

    def _cells(self, world):
        import f2feat
        base = super()._cells(world)
        h = f2feat.hmm(world)
        b = np.minimum((h[:, 0] * self.nb).astype(int), self.nb - 1)
        return [c + "|" + ("x" if h[n, 2] else str(b[n])) for n, c in enumerate(base)]
