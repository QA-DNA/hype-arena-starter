"""F4 knowledge graph over one World: facts linked by same-claim (consistent value, same observation key,
other page) and contradicts (inconsistent value) edges with time-aware weights, plus same-page and same-row
membership. Built from the world's stated facts only (label-free); labels enter only as anchors.

Labellers (Variant classes): Prop (label propagation / label spreading / personalized PageRank, optional
page latent-lie EM prior).
Feature plugins (n_facts x k, leave-fold-out for anchor facts so train and test features match):
  prop_feats  : spread score, hard-clamp propagation score, PPR log-ratio, PPR log-mass, log support degree,
                log contradiction degree, propagated P(fact true)
  page_lie    : page latent-lie posterior from the OTHER rows of the page, expected page false rate, lift
  blame_feats : P(fact false), blame share within the row, noisy-OR P(fact false | row false), max P(false)
                of the other facts of the row
"""
import math
import os
import sys

import numpy as np
import scipy.sparse as sp
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(os.path.dirname(HERE), "harness"))
from api import Prediction  # noqa: E402
from variants.v5 import groups  # noqa: E402

_EDGES = {}
K_FOLDS = 5


# ------------------------------------------------------------------ graph
def edges(world, tau=30.0, beta=0.5, wmin=0.01):
    """-> (Wp, Wm) csr (target fact x source fact): kernel weight of same-key other-page observations that
    are consistent (Wp) / inconsistent (Wm). Kernel exp(-|dt|/tau), times beta for sources dated after the
    target (before/after asymmetry on a key)."""
    ck = (world.static_key, world.n_facts, tau, beta, wmin)
    if ck in _EDGES:
        return _EDGES[ck]
    pg = world.page[world.frow]
    d = world.date[world.frow].astype(float)
    R, C, V, S = [], [], [], []
    for g, cons, _ in groups(world).values():
        if len(g) < 2:
            continue
        dtd = d[g][:, None] - d[g][None, :]  # target date - source date
        K = np.exp(-np.abs(dtd) / tau) if tau != float("inf") else np.ones_like(dtd)
        K = np.where(dtd >= 0, K, beta * K) * (pg[g][:, None] != pg[g][None, :])
        a, b = np.nonzero(K > wmin)
        R.append(g[a]); C.append(g[b]); V.append(K[a, b]); S.append(cons[a, b])
    m = world.n_facts
    if R:
        R, C, V, S = map(np.concatenate, (R, C, V, S))
    else:
        R = C = np.zeros(0, int); V = np.zeros(0); S = np.zeros(0, bool)
    Wp = sp.csr_matrix((V * S, (R, C)), shape=(m, m))
    Wm = sp.csr_matrix((V * ~S, (R, C)), shape=(m, m))
    Wp.eliminate_zeros(); Wm.eliminate_zeros()
    _EDGES[ck] = (Wp, Wm)
    return Wp, Wm


def anchors(world, role=None, mfneg="uniform", blame=None, wu=0.0):
    """Per fact anchor value Y in [-1, 1] and anchor mask. true row -> +1 for every fact; single-fact false
    row -> -1; multi-fact false row -> -1/k ('uniform'), -blame ('blame', blame array given), unused (None);
    unsure / no role -> not an anchor, value wu (vote prior: an unlabelled statement leans true)."""
    r = np.array([lab if lab is not None else "" for lab in world.label], dtype=object)
    if role is not None:
        r = np.where(world.labelled, r, np.asarray(role, dtype=object))
    nf = np.array([len(fs) for fs in world.facts])
    rf = r[world.frow]
    k = nf[world.frow]
    Y = np.full(world.n_facts, float(wu))
    A = np.zeros(world.n_facts, bool)
    t = rf == "true"
    Y[t], A[t] = 1.0, True
    f1 = (rf == "false") & (k == 1)
    Y[f1], A[f1] = -1.0, True
    fm = (rf == "false") & (k > 1)
    if mfneg == "uniform":
        Y[fm], A[fm] = -1.0 / k[fm], True
    elif mfneg == "blame" and blame is not None:
        Y[fm], A[fm] = -blame[fm], True
    return Y, A


def fact_folds(world, A, k=K_FOLDS, seed=0):
    """Fold id per fact for anchor pages (-1 elsewhere), by page, fixed seed."""
    pages = np.unique(world.page[world.frow[A]])
    rng = np.random.RandomState(seed)
    fold_of = dict(zip(rng.permutation(pages).tolist(), np.arange(len(pages)) % k))
    fp = world.page[world.frow]
    return np.array([fold_of.get(int(p), -1) if a else -1 for p, a in zip(fp, A)])


def _page_term(world, F):
    """Mean of min(F, 0) over the facts of the other rows of the same page."""
    fp, fr = world.page[world.frow], world.frow
    neg = np.minimum(F, 0)
    ps = np.bincount(fp, neg, world.n_pages); pc = np.bincount(fp, None, world.n_pages)
    rs = np.bincount(fr, neg, world.n); rc = np.bincount(fr, None, world.n)
    cnt = pc[fp] - rc[fr]
    return np.divide(ps[fp] - rs[fr], cnt, out=np.zeros_like(F), where=cnt > 0)


def spread(world, Y, A, Wp, Wm, alpha=0.8, mu=0.5, gamma=0.2, iters=30, clamp=False, page_w=0.0):
    """Signed propagation. Message to a fact: support from consistent observations (their score), contradiction
    from inconsistent TRUE-leaning observations (minus their positive part), weak support from contradicting
    false-leaning ones (gamma). clamp=True: label propagation (anchors fixed); False: label spreading
    (F = alpha * message + (1 - alpha) * Y)."""
    deg = np.asarray(Wp.sum(1)).ravel() + np.asarray(Wm.sum(1)).ravel()
    F = Y.copy()
    for _ in range(iters):
        msg = Wp @ F - Wm @ np.maximum(F, 0) + gamma * (Wm @ np.maximum(-F, 0))
        if page_w:
            msg = msg + page_w * _page_term(world, F) * (deg + mu)
        Fn = alpha * msg / (deg + mu) + (1 - alpha) * Y
        if clamp:
            Fn = np.where(A, Y, msg / (deg + mu))
        F = np.clip(Fn, -1, 1)
    return F


def ppr(world, Y, A, Wp, Wm, alpha=0.85, gamma=0.2, iters=40):
    """Personalized PageRank on the doubled graph (fact,+)/(fact,-). (b,+) -> (a,+) on consistent, (a,-) on
    inconsistent edges; (b,-) -> (a,-) on consistent, (a,+) with gamma on inconsistent. Restarts: true anchors
    (+ nodes) and false anchors (- nodes), each class normalised to mass 1. -> (log ratio, log mass)."""
    outp = np.asarray(Wp.sum(0)).ravel() + np.asarray(Wm.sum(0)).ravel()
    outm = np.asarray(Wp.sum(0)).ravel() + gamma * np.asarray(Wm.sum(0)).ravel()
    ip = np.divide(1.0, outp, out=np.zeros_like(outp), where=outp > 0)
    im = np.divide(1.0, outm, out=np.zeros_like(outm), where=outm > 0)
    rp = np.where(A & (Y > 0), Y, 0.0); rm = np.where(A & (Y < 0), -Y, 0.0)
    rp = rp / rp.sum() if rp.sum() else rp
    rm = rm / rm.sum() if rm.sum() else rm
    pp, pm = rp.copy(), rm.copy()
    for _ in range(iters):
        a, b = pp * ip, pm * im
        pp, pm = (1 - alpha) * rp + alpha * (Wp @ a + gamma * (Wm @ b)), (1 - alpha) * rm + alpha * (Wm @ a + Wp @ b)
    eps = 1e-6 / max(1, world.n_facts)
    return np.log((pp + eps) / (pm + eps)), np.log(pp + pm + eps)


def _oof(world, Y, A, fn, folds, wu=0.0):
    """fn(Y, A) -> array(s) per fact. Anchor facts get the value from the run with their fold unanchored;
    every other fact from the run with all anchors."""
    full = fn(Y, A)
    tup = isinstance(full, tuple)
    out = [x.copy() for x in full] if tup else [full.copy()]
    for k in range(K_FOLDS):
        m = folds == k
        if not m.any():
            continue
        r = fn(np.where(m, wu, Y), A & ~m)
        for o, x in zip(out, r if tup else (r,)):
            o[m] = x[m]
    return tuple(out) if tup else out[0]


def fact_targets(world, A, Y):
    """Training targets for a 1-D map: anchors with Y=+1 -> 1, Y=-1 -> 0 (single-fact false)."""
    m = A & (np.abs(Y) == 1)
    return m, (Y[m] > 0).astype(float)


def to_prob(score, m, y, default=0.85):
    """Monotone 1-D logistic map score -> P(fact true), fitted on anchor facts' out-of-fold scores."""
    if m.sum() < 5 or len(set(y.tolist())) < 2:
        return np.full(len(score), default)
    lr = LogisticRegression(C=10.0).fit(score[m][:, None], y)
    return lr.predict_proba(score[:, None])[:, 1]


DEF = dict(tau=30.0, beta=0.5, alpha=0.8, mu=0.5, gamma=0.2, page_w=0.0, mfneg="uniform", em=0, wu=0.0)


def propagate(world, role=None, mode="spread", **kw):
    """-> (score per fact, OOF), P(fact true) per fact. mode: spread | prop | ppr. em>0: noisy-OR blame rounds for
    multi-fact false anchors (blame from the previous round's P(false))."""
    p = dict(DEF, **kw)
    Wp, Wm = edges(world, p["tau"], p["beta"])
    Y, A = anchors(world, role, p["mfneg"], wu=p["wu"])
    folds = fact_folds(world, A)
    m, y = fact_targets(world, A, Y)

    def run(Y_, A_):
        if mode == "ppr":
            return ppr(world, Y_, A_, Wp, Wm, gamma=p["gamma"])[0]
        return spread(world, Y_, A_, Wp, Wm, p["alpha"], p["mu"], p["gamma"], clamp=mode == "prop",
                      page_w=p["page_w"])
    s = _oof(world, Y, A, run, folds, p["wu"])
    pt = to_prob(s, m, y)
    for _ in range(p["em"]):
        Y, A = anchors(world, role, "blame", blame=row_blame(world, 1 - pt)[1], wu=p["wu"])
        s = _oof(world, Y, A, run, folds, p["wu"])
        pt = to_prob(s, m, y)
    return s, pt


# ------------------------------------------------------------------ blame (MIL / noisy-OR)
def row_blame(world, q):
    """q = P(fact false). -> (P(row false) = 1 - prod(1 - q), blame share q / sum q, noisy-OR posterior
    P(fact false | row false) = q / P(row false), max q of the OTHER facts of the row)."""
    fr = world.frow
    lq = np.log(np.clip(1 - q, 1e-9, 1))
    prf = 1 - np.exp(np.bincount(fr, lq, world.n))
    qs = np.bincount(fr, q, world.n)
    share = np.divide(q, qs[fr], out=np.ones_like(q), where=qs[fr] > 0)
    post = np.clip(np.divide(q, prf[fr], out=np.ones_like(q), where=prf[fr] > 0), 0, 1)
    other = np.zeros_like(q)
    for i in np.where(np.bincount(fr, None, world.n) > 1)[0]:
        s = slice(world.fstart[i], world.fstart[i] + len(world.facts[i]))
        v = q[s]
        for j in range(len(v)):
            other[s.start + j] = np.max(np.delete(v, j))
    return prf, share, post, other


# ------------------------------------------------------------------ page latent-lie EM
def page_em(world, q_fact, iters=40, labels=True):
    """Latent page state z (lying / honest), row false ~ Bern(rho_z). Labelled rows: observed label; other rows:
    soft evidence from their facts (row P(false) = 1 - prod(1 - q), turned into a likelihood ratio against the
    base rate). -> per row: leave-row-out posterior P(z=1 | other rows of the page), expected false rate, params."""
    fr = world.frow
    prf = 1 - np.exp(np.bincount(fr, np.log(np.clip(1 - q_fact, 1e-9, 1)), world.n))
    has = np.bincount(fr, None, world.n) > 0
    lab0 = world.labelled & np.isin(world.label, ["true", "false"])
    lab = lab0 if labels else np.zeros(world.n, bool)
    base = float(np.clip(np.mean(world.label[lab0] == "false") if lab0.any() else 0.15, 0.02, 0.5))
    e = np.clip(prf, 1e-4, 1 - 1e-4)
    Lf = np.where(lab, (world.label == "false").astype(float), e / base)
    Lt = np.where(lab, (world.label == "true").astype(float), (1 - e) / (1 - base))
    use = (lab | (~lab & has)).astype(float)
    pi, r0, r1 = 0.3, max(0.01, base * 0.5), min(0.9, base * 2.5)
    pg = world.page
    for _ in range(iters):
        l1 = np.log(np.clip(r1 * Lf + (1 - r1) * Lt, 1e-12, None)) * use
        l0 = np.log(np.clip(r0 * Lf + (1 - r0) * Lt, 1e-12, None)) * use
        s1 = np.bincount(pg, l1, world.n_pages); s0 = np.bincount(pg, l0, world.n_pages)
        lo = np.log(pi / (1 - pi)) + s1 - s0
        post = 1 / (1 + np.exp(-np.clip(lo, -50, 50)))
        pz = post[pg]
        f1 = r1 * Lf / np.clip(r1 * Lf + (1 - r1) * Lt, 1e-12, None)
        f0 = r0 * Lf / np.clip(r0 * Lf + (1 - r0) * Lt, 1e-12, None)
        pi = float(np.clip(post.mean(), 0.01, 0.99))
        r1 = float(np.clip((pz * f1 * use).sum() / max(1e-9, (pz * use).sum()), 1e-3, 0.999))
        r0 = float(np.clip(((1 - pz) * f0 * use).sum() / max(1e-9, ((1 - pz) * use).sum()), 1e-3, 0.999))
        if r0 > r1:
            r0, r1 = r1, r0
    l1 = np.log(np.clip(r1 * Lf + (1 - r1) * Lt, 1e-12, None)) * use
    l0 = np.log(np.clip(r0 * Lf + (1 - r0) * Lt, 1e-12, None)) * use
    s1 = np.bincount(pg, l1, world.n_pages); s0 = np.bincount(pg, l0, world.n_pages)
    lo_row = np.log(pi / (1 - pi)) + (s1[pg] - l1) - (s0[pg] - l0)  # leave this row out
    post_row = 1 / (1 + np.exp(-np.clip(lo_row, -50, 50)))
    rate = post_row * r1 + (1 - post_row) * r0
    return post_row, rate, dict(pi=pi, rho0=r0, rho1=r1, base=base)


# ------------------------------------------------------------------ plugins
_PCACHE = {}


def _key(world, role, tag):
    lk = hash((world.labelled.tobytes(), tuple(world.label[world.labelled]),
               None if role is None else tuple(np.asarray(role, dtype=object).tolist())))
    return (world.static_key, world.n, tag, lk)


def _base(world, role=None, tau=30.0):
    k = _key(world, role, ("base", tau))
    if k not in _PCACHE:
        s_sp, pt = propagate(world, role, "spread", tau=tau)
        s_pr, _ = propagate(world, role, "prop", tau=tau)
        Wp, Wm = edges(world, tau)
        Y, A = anchors(world, role, "uniform")
        folds = fact_folds(world, A)
        lr, lm = _oof(world, Y, A, lambda Y_, A_: ppr(world, Y_, A_, Wp, Wm), folds)
        dp = np.log1p(np.asarray(Wp.sum(1)).ravel()); dm = np.log1p(np.asarray(Wm.sum(1)).ravel())
        _PCACHE[k] = np.c_[s_sp, s_pr, lr, lm, dp, dm, pt]
        if len(_PCACHE) > 64:
            _PCACHE.pop(next(iter(_PCACHE)))
    return _PCACHE[k]


def prop_feats(world, role=None):
    """7 columns: spread score, propagation score, PPR log-ratio, PPR log-mass, log support degree, log
    contradiction degree, propagated P(fact true) (spread score mapped by a 1-D logistic fit on anchors)."""
    return _base(world, role)


def prop_feats_t10(world, role=None):
    """prop_feats with a 10-day time kernel (tau 10, the best standalone Prop labeller kernel)."""
    return _base(world, role, 10.0)


def prop_p(world, role=None):
    """1 column: propagated P(fact true)."""
    return _base(world, role)[:, 6]


def page_lie(world, role=None, labels=False):
    """3 columns per fact: P(page lies | other rows of the page), expected page false rate, log lift over base.
    Soft evidence only (labels=False): every row speaks through its propagated (out-of-fold) fact scores, as on a
    test page, which is never labelled."""
    q = 1 - _base(world, role)[:, 6]
    post, rate, prm = page_em(world, q, labels=labels)
    fr = world.frow
    return np.c_[post[fr], rate[fr], np.log(rate[fr] / prm["base"])]


def page_lie_lab(world, role=None):
    """page_lie with the labelled rows of the page observed (train/test mismatch: kept for the comparison)."""
    return page_lie(world, role, labels=True)


def blame_feats(world, role=None):
    """4 columns per fact: P(fact false) (propagated), blame share in the row, noisy-OR P(fact false | row false),
    max P(false) of the other facts of the row."""
    q = 1 - _base(world, role)[:, 6]
    prf, share, post, other = row_blame(world, q)
    return np.c_[q, share, post, other]


def all_feats(world, role=None):
    """prop_feats + page_lie + blame_feats (14 columns)."""
    return np.c_[prop_feats(world, role), page_lie(world, role), blame_feats(world, role)]


# ------------------------------------------------------------------ labeller
def select_rows(world, prow_tr, prow, calib=True):
    """v9-style: isotonic on labelled rows (out-of-fold P(true)), threshold and unsure band chosen for arena points
    exactly as A/score.py: +1 correct (a correct unsure included), -1 wrong true/false, 0 wrong unsure."""
    tr = world.labelled
    Y = world.label
    iso = None
    if calib:
        m = tr & np.isin(Y, ["true", "false"])
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(prow_tr[m], (Y[m] == "true").astype(float))
        prow_tr, prow = iso.predict(prow_tr), iso.predict(prow)
    ytr = Y[tr].astype(str)
    best = None
    for t in (0.3, 0.4, 0.5, 0.6, 0.7):
        for band in (0.0, 0.05, 0.1, 0.15):
            o = decide(prow_tr[tr], t, band)
            sc = float(np.mean(np.where(o == ytr, 1, np.where(o == "unsure", 0, -1))))
            if best is None or sc > best[0]:
                best = (sc, t, band)
    return iso, best[1], best[2], prow


def conf_of(out, p):
    """Confidence of the returned label, floored at 0.5 (contract: decided rows carry 0.5..1)."""
    return np.maximum(np.where(out == "true", p, 1 - p), 0.5)


def two_classes(world):
    """True when the world's labelled rows hold both true and false (refit possible)."""
    lab = world.label[world.labelled]
    return bool((lab == "true").any() and (lab == "false").any())


def practice_world():
    """Fallback training world for one-class refit worlds: practice, every row labelled (public data)."""
    from world import practice_full
    return practice_full()[0]


def decide(pt, t, band):
    out = np.where(pt >= t, "true", "false").astype(object)
    out[np.abs(pt - t) < band] = "unsure"
    return out


class Prop:
    """Graph labeller. mode spread | prop | ppr; pagelie: multiply row odds by the page-EM lift; em: blame rounds.
    Row P(true) = product of propagated fact P(true); isotonic + points-optimal threshold on labelled rows.
    Rows without facts: the labelled true rate decides. Transfer: fit() keeps the 1-D maps; predict() reruns
    propagation on the target world with its own anchors (graph methods are transductive)."""

    def __init__(self, mode="spread", pagelie=False, **kw):
        self.mode, self.pagelie, self.kw = mode, pagelie, kw
        self.chosen = []
        self.state = None

    def _prow(self, world):
        s, pt = propagate(world, None, self.mode, **self.kw)
        prow = np.exp(np.bincount(world.frow, np.log(np.clip(pt, 1e-9, 1)), world.n))
        if self.pagelie:
            post, rate, prm = page_em(world, 1 - pt, labels=False)
            lift = rate / prm["base"]
            odds = prow / np.clip(1 - prow, 1e-9, None) / lift
            prow = odds / (1 + odds)
        nofact = np.bincount(world.frow, None, world.n) == 0
        return np.where(nofact, np.nan, prow)

    def run(self, world):
        if not two_classes(world):  # one-class public labels: fit on practice, apply here
            return self.fit(practice_world()).predict(world)
        prow = self._prow(world)
        fill = float(np.nanmean(prow)) if np.isfinite(prow).any() else 0.85
        prow = np.where(np.isnan(prow), fill, prow)
        iso, t, band, pc = select_rows(world, prow, prow)
        self.chosen.append((t, band))
        self.state = (iso, t, band)
        out = decide(pc, t, band)
        return Prediction(out, conf_of(out, pc))

    def fit(self, train_world):
        self.run(train_world)
        return self

    def predict(self, world):
        iso, t, band = self.state
        prow = self._prow(world)
        prow = np.where(np.isnan(prow), float(np.nanmean(prow)) if np.isfinite(prow).any() else 0.85, prow)
        pc = iso.predict(prow) if iso is not None else prow
        out = decide(pc, t, band)
        return Prediction(out, conf_of(out, pc))


if __name__ == "__main__":
    import time
    from world import load_track
    tr = load_track("P80")
    w, gold, sc = tr.folds[0]
    t0 = time.time()
    X = all_feats(w)
    print("all_feats", X.shape, round(time.time() - t0, 2), "s", np.isfinite(X).all())
    g = np.array([None] * w.n, dtype=object); g[sc] = gold
    gf = g[w.frow]
    m = np.isin(gf, ["true", "false"])
    from sklearn.metrics import roc_auc_score
    names = ["spread", "prop", "ppr_lr", "ppr_lm", "dsup", "dcon", "p_true", "page_post", "page_rate", "page_lift",
             "q", "share", "nor_post", "q_other"]
    for c, nm in enumerate(names):
        print(nm, "AUC(true) on scored facts", round(roc_auc_score(gf[m] == "true", X[m, c]), 3))
    q = np.array([0.1, 0.5, 0.2])

    class _W:  # tiny check of row_blame
        n, frow, fstart, facts = 1, np.array([0, 0, 0]), np.array([0]), [[0, 0, 0]]
    prf, share, post, other = row_blame(_W, q)
    assert abs(prf[0] - (1 - 0.9 * 0.5 * 0.8)) < 1e-9 and abs(share.sum() - 1) < 1e-9
    assert np.allclose(other, [0.5, 0.2, 0.5])
    print("graph selfcheck ok")
