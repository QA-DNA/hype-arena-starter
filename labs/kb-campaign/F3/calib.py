"""F3 calibrators and abstention policies, reusable around any row scorer.

A score s is any monotone "row is true" score (default: a probability in [0, 1]). Everything is fitted on
out-of-fold scores of labelled rows; policy parameters are chosen on CROSS-FITTED calibrated scores (the
calibrator is refitted without each page fold), so the threshold never sees an in-sample isotonic fit.

Main entry points (module:function for the combination phase):
  calib:Decider            Decider(calib, policy, **kw).fit(s, y3, groups, noev).decide(s_new, noev_new)
  calib:wrap               wrap(s_tr, y3_tr, g_tr, s_te, calib=..., policy=...) -> labels, conf, p
  calib:fit_calibrator     fit_calibrator(name, s, y01) -> f(s_new) -> (p, width)
Calibrators: none platt temp beta iso hist va (inductive Venn-Abers, hand-written).
Policies: never05 (t=0.5), never (t chosen by points), points (t and unsure band by points),
  conformal (split conformal at alpha, marginal: both labels in the set -> unsure), mondrian (per-class quantiles),
  confpts / mondpts (alpha chosen by points),
  vaw (Venn-Abers interval width above w -> unsure, w and t by points), noev (unsure where the row has no
  evidence at all, else t=0.5), noev+points.
  arena3 (no free parameter: P(unsure | s) from a coarse binned calibrator, P(false) = 1 - P(true) - P(unsure),
  label = argmax{true: 2P(true)-1, false: 2P(false)-1, unsure: P(unsure)}: the expected-points rule).
Points (A/score.py): +1 when the label equals gold (a correct unsure too), 0 for a wrong unsure, -1 for a wrong
true/false. Before 2026-10-29 ~01:55 points() gave 0 to a correct unsure (legacy objective, see the F3 report).
"""
import math

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from sklearn.isotonic import IsotonicRegression, isotonic_regression
from sklearn.model_selection import GroupKFold

EPS = 1e-6
T_GRID = np.round(np.arange(0.20, 0.801, 0.025), 3)
B_GRID = (0.0, 0.025, 0.05, 0.075, 0.1, 0.15)


def _logit(s):
    s = np.clip(np.asarray(s, float), EPS, 1 - EPS)
    return np.log(s) - np.log1p(-s)


def _sig(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))


def _nll(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return -float(np.mean(y * np.log(p) + (1 - y) * np.log1p(-p)))


# ------------------------------------------------------------------ calibrators: f(s) -> (p, width)
def _platt(s, y):
    z = _logit(s)
    npos, nneg = y.sum(), len(y) - y.sum()
    t = np.where(y > 0, (npos + 1) / (npos + 2), 1 / (nneg + 2))  # Platt's smoothed targets

    def f(ab):
        return _nll(_sig(ab[0] * z + ab[1]), t)
    ab = minimize(f, np.array([1.0, 0.0]), method="L-BFGS-B").x
    return lambda q: (_sig(ab[0] * _logit(q) + ab[1]), None)


def _temp(s, y):
    z = _logit(s)
    r = minimize_scalar(lambda lt: _nll(_sig(z / math.exp(lt)), y), bounds=(-4, 4), method="bounded")
    T = math.exp(r.x)
    return lambda q: (_sig(_logit(q) / T), None)


def _beta(s, y):
    # ponytail: unconstrained 3-parameter beta map (Kull 2017 also forces a, b >= 0); add the constraint if it
    # ever produces a non-monotone map on our scores.
    s = np.clip(s, EPS, 1 - EPS)
    F = np.c_[np.log(s), -np.log1p(-s)]
    npos, nneg = y.sum(), len(y) - y.sum()
    t = np.where(y > 0, (npos + 1) / (npos + 2), 1 / (nneg + 2))

    def f(w):
        return _nll(_sig(F @ w[:2] + w[2]), t)
    w = minimize(f, np.array([1.0, 1.0, 0.0]), method="L-BFGS-B").x

    def g(q):
        q = np.clip(np.asarray(q, float), EPS, 1 - EPS)
        return _sig(np.c_[np.log(q), -np.log1p(-q)] @ w[:2] + w[2]), None
    return g


def _iso(s, y):
    m = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(s, y)
    return lambda q: (m.predict(np.asarray(q, float)), None)


def _hist(s, y, bins=10, m=2.0):
    edges = np.unique(np.quantile(s, np.linspace(0, 1, bins + 1)[1:-1]))
    b = np.searchsorted(edges, s, side="right")
    prior = y.mean()
    val = np.array([(y[b == k].sum() + m * prior) / ((b == k).sum() + m) for k in range(len(edges) + 1)])
    val = np.maximum.accumulate(val)  # keep the map monotone
    return lambda q: (val[np.searchsorted(edges, np.asarray(q, float), side="right")], None)


def _va(s, y):
    """Inductive Venn-Abers: isotonic fitted twice per test score (label assumed 0 and 1);
    p = p1 / (1 - p0 + p1), width = p1 - p0. Test scores are grouped by insertion position."""
    us, inv = np.unique(np.asarray(s, float), return_inverse=True)
    w = np.bincount(inv).astype(float)
    ys = np.bincount(inv, y) / w

    def f(q):
        q = np.asarray(q, float)
        pos = np.searchsorted(us, q, side="left")
        hit = (pos < len(us)) & (us[np.minimum(pos, len(us) - 1)] == q)
        p0 = np.empty(len(q)); p1 = np.empty(len(q))
        for key in set(zip(pos.tolist(), hit.tolist())):
            k, h = key
            sel = (pos == k) & (hit == h)
            out = []
            for lab in (0.0, 1.0):
                if h:  # merge into the existing tied value
                    yy, ww = ys.copy(), w.copy()
                    yy[k] = (ys[k] * w[k] + lab) / (w[k] + 1); ww[k] += 1; at = k
                else:
                    yy, ww = np.insert(ys, k, lab), np.insert(w, k, 1.0); at = k
                out.append(isotonic_regression(yy, sample_weight=ww, y_min=0.0, y_max=1.0)[at])
            p0[sel], p1[sel] = out
        return p1 / (1 - p0 + p1), p1 - p0
    return f


def unsure_rate(s, yu, bins=5, m=20.0):
    """P(gold unsure | score): equal-frequency bins (not monotone), shrunk to the base rate with weight m."""
    edges = np.unique(np.quantile(s, np.linspace(0, 1, bins + 1)[1:-1])) if len(s) else np.array([])
    b = np.searchsorted(edges, s, side="right")
    prior = float(yu.mean()) if len(yu) else 0.0
    val = np.array([(yu[b == k].sum() + m * prior) / ((b == k).sum() + m) for k in range(len(edges) + 1)])
    return lambda q: val[np.searchsorted(edges, np.asarray(q, float), side="right")]


CALIBRATORS = {"none": None, "platt": _platt, "temp": _temp, "beta": _beta, "iso": _iso, "hist": _hist, "va": _va}


def fit_calibrator(name, s, y):
    s = np.asarray(s, float); y = np.asarray(y, float)
    if name == "none" or len(set(y.tolist())) < 2:
        c = float(y.mean()) if name != "none" and len(y) else None
        if c is None:
            return lambda q: (np.clip(np.asarray(q, float), 0, 1), None)
        return lambda q: (np.full(len(np.asarray(q)), c), None)
    return CALIBRATORS[name](s, y)


# ------------------------------------------------------------------ decisions
def points(y3, lab):
    """Arena points exactly as A/score.py: +1 when the label equals gold (a correct unsure included), 0 for a wrong
    unsure, -1 for a wrong true/false."""
    y3 = np.asarray(y3, dtype=object); lab = np.asarray(lab, dtype=object)
    return float(np.sum(np.where(lab == y3, 1, np.where(lab == "unsure", 0, -1))))


def threshold(p, t, band=0.0):
    out = np.where(p >= t, "true", "false").astype(object)
    out[np.abs(p - t) < band] = "unsure"
    return out


def _pick(cands, y3):
    """cands: list of (params, labels); max points, ties -> the first (grids are ordered simplest first)."""
    best = None
    for prm, lab in cands:
        sc = points(y3, lab)
        if best is None or sc > best[0] + 1e-9:
            best = (sc, prm)
    return best[1]


def _t_order():
    return sorted(T_GRID, key=lambda t: (abs(t - 0.5), t))  # ties resolve toward 0.5


def conformal_q(p, y3, alpha, mondrian=False):
    """Split-conformal quantiles, nonconformity 1-p for gold true, p for gold false (gold unsure rows dropped).
    Marginal (one quantile over both classes: a symmetric unsure band around 0.5) or Mondrian (per class)."""
    q = {}
    a_all = np.r_[1 - p[y3 == "true"], p[y3 == "false"]]
    for cls, a in (("true", 1 - p), ("false", p)):
        v = np.sort(a[y3 == cls] if mondrian else a_all)
        if not len(v):
            q[cls] = 1.0
            continue
        k = math.ceil((len(v) + 1) * (1 - alpha)) - 1
        q[cls] = 1.0 if k >= len(v) else float(v[max(k, 0)])
    return q


def conformal_labels(p, q):
    tin = (1 - p) <= q["true"]; fin = p <= q["false"]
    out = np.where(p >= 0.5, "true", "false").astype(object)
    out[tin & ~fin] = "true"; out[fin & ~tin] = "false"; out[tin & fin] = "unsure"
    return out


A_GRID = (0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3)
W_GRID = (0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.01)


def choose(policy, p, w, y3, noev, alpha=0.1):
    if policy in ("never05", "noev"):
        return {"t": 0.5, "band": 0.0}
    if policy == "never":
        return _pick([({"t": t, "band": 0.0}, threshold(p, t)) for t in _t_order()], y3)
    if policy in ("points", "noev+points"):
        c = []
        for b in B_GRID:
            for t in _t_order():
                lab = threshold(p, t, b)
                if policy == "noev+points":
                    lab[noev] = "unsure"
                c.append(({"t": t, "band": b}, lab))
        return _pick(c, y3)
    if policy in ("conformal", "mondrian"):
        return {"q": conformal_q(p, y3, alpha, policy == "mondrian")}
    if policy in ("confpts", "mondpts"):
        c = [{"q": conformal_q(p, y3, a, policy == "mondpts"), "alpha": a} for a in A_GRID]
        return _pick([(prm, conformal_labels(p, prm["q"])) for prm in c], y3)
    if policy == "vaw":
        if w is None:
            raise ValueError("vaw needs calib='va'")
        c = []
        for wt in sorted(W_GRID, reverse=True):
            for t in _t_order():
                lab = threshold(p, t); lab[w > wt] = "unsure"
                c.append(({"t": t, "band": 0.0, "w": wt}, lab))
        return _pick(c, y3)
    raise ValueError(policy)


def apply(policy, prm, p, w, noev):
    if policy in ("conformal", "mondrian", "confpts", "mondpts"):
        return conformal_labels(p, prm["q"])
    lab = threshold(p, prm["t"], prm["band"])
    if policy == "vaw":
        lab[w > prm["w"]] = "unsure"
    if policy in ("noev", "noev+points") and noev is not None:
        lab[noev] = "unsure"
    return lab


def conf_of(lab, p, mode="class"):
    """class: calibrated P(returned label), floored at 0.5 (the output contract is [0.5, 1]; a label returned
    against its own probability, possible when t != 0.5, gets 0.5). max: max(p, 1 - p)."""
    c = np.where(lab == "true", p, 1 - p) if mode == "class" else np.maximum(p, 1 - p)
    c = np.clip(c, 0.5, 1.0).astype(float)
    c[lab == "unsure"] = np.nan
    return c


class Decider:
    """calib + policy around any score. fit(s, y3, groups, noev): s = out-of-fold scores of labelled rows,
    y3 = their labels ('true'/'false'/'unsure'), groups = page ids. Binary target: true vs not-true ('tvn',
    unsure counts as not true) or true vs false ('tvf', unsure rows dropped from the calibrator fit)."""

    def __init__(self, calib="iso", policy="points", alpha=0.1, k=5, target="tvn", conf="class"):
        self.calib, self.policy, self.alpha, self.k, self.target, self.conf = calib, policy, alpha, k, target, conf

    def _y01(self, y3):
        keep = np.ones(len(y3), bool) if self.target == "tvn" else (y3 != "unsure")
        return keep, (y3 == "true").astype(float)

    def fit(self, s, y3, groups, noev=None):
        s = np.asarray(s, float); y3 = np.asarray(y3, dtype=object)
        keep, y01 = self._y01(y3)
        self.f = fit_calibrator(self.calib, s[keep], y01[keep])
        if self.policy == "arena3":
            self.fu = unsure_rate(s, (y3 == "unsure").astype(float))
            self.prm = {"rule": "argmax expected points"}
            self.p_cf = self.w_cf = None
            return self
        # cross-fitted calibrated scores for choosing the policy parameters
        pc = np.empty(len(s)); wc = np.zeros(len(s)) if self.calib == "va" else None
        k = min(self.k, len(set(groups.tolist())))
        if k >= 2:
            for a, b in GroupKFold(k).split(s, groups=groups):
                ka = a[keep[a]]
                f = fit_calibrator(self.calib, s[ka], y01[ka])
                pc[b], wb = f(s[b])
                if wc is not None:
                    wc[b] = wb
        else:
            pc[:], wb = self.f(s)
            if wc is not None:
                wc[:] = wb
        self.p_cf, self.w_cf = pc, wc
        self.prm = choose(self.policy, pc, wc, y3, None if noev is None else np.asarray(noev, bool), self.alpha)
        return self

    def decide(self, s, noev=None):
        p, w = self.f(np.asarray(s, float))
        p = np.asarray(p, float)
        if self.policy == "arena3":
            pu = self.fu(np.asarray(s, float))
            pt = p if self.target == "tvn" else p * (1 - pu)
            pf = np.clip(1 - pt - pu, 0, 1)
            sc = np.c_[2 * pt - 1, 2 * pf - 1, pu]
            lab = np.array(["true", "false", "unsure"], dtype=object)[np.argmax(sc, 1)]
            c = np.where(lab == "true", pt, pf).astype(float)
            c = np.clip(c, 0.5, 1.0); c[lab == "unsure"] = np.nan
            return lab, c, pt
        lab = apply(self.policy, self.prm, p, w, None if noev is None else np.asarray(noev, bool))
        return lab, conf_of(lab, p, self.conf), p


def wrap(s_tr, y3_tr, g_tr, s_te, calib="platt", policy="points", noev_tr=None, noev_te=None, **kw):
    d = Decider(calib, policy, **kw).fit(s_tr, y3_tr, np.asarray(g_tr), noev_tr)
    return d.decide(s_te, noev_te)


def reliability(y_correct, conf, bins=10):
    """ECE (10 equal-width bins, as A/score.py) and Brier over decided rows."""
    ok = np.asarray(y_correct, float); c = np.asarray(conf, float)
    b = np.minimum((c * bins).astype(int), bins - 1)
    ece = sum(abs(ok[b == k].sum() - c[b == k].sum()) for k in range(bins)) / len(c)
    return ece, float(np.mean((c - ok) ** 2))


def _selfcheck():
    rng = np.random.default_rng(0)
    s = rng.uniform(size=600); y = (rng.uniform(size=600) < s ** 2).astype(float)
    for name in CALIBRATORS:
        p, w = fit_calibrator(name, s, y)(s)
        assert p.shape == s.shape and np.all((p >= 0) & (p <= 1)), name
        if name not in ("none",):
            assert _nll(p, y) < _nll(s, y) + 0.02, (name, _nll(p, y), _nll(s, y))
    p, w = _va(s, y)(np.r_[s[:5], 0.5, -1, 2])
    assert np.all(w >= -1e-12) and np.all((p >= 0) & (p <= 1))
    y3 = np.where(y > 0, "true", "false").astype(object); g = np.arange(600) // 6
    for pol in ("never05", "never", "points", "conformal", "mondrian", "confpts", "mondpts", "noev", "noev+points"):
        lab, conf, p = wrap(s, y3, g, s, calib="iso", policy=pol, noev_tr=s < 0.05, noev_te=s < 0.05)
        assert set(lab.tolist()) <= {"true", "false", "unsure"} and np.isnan(conf[lab == "unsure"]).all()
        assert np.all(conf[lab != "unsure"] >= 0.5)
    lab, conf, p = wrap(s, y3, g, s, calib="va", policy="vaw")
    assert threshold(np.array([0.7, 0.3, 0.52]), 0.5, 0.05).tolist() == ["true", "false", "unsure"]
    assert points(["true", "false", "unsure"], ["true", "true", "unsure"]) == 1
    assert points(["true", "unsure"], ["unsure", "false"]) == -1
    y3u = y3.copy(); y3u[::25] = "unsure"
    lab, conf, p = wrap(s, y3u, g, s, calib="iso", policy="arena3")
    assert set(lab.tolist()) <= {"true", "false", "unsure"} and np.all(conf[lab != "unsure"] >= 0.5)
    print("calib selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
