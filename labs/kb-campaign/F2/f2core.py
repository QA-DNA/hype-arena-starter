"""F2 core: per-key temporal structures, hazard fitting, chain engines (HMM sum/max product, TeCoRe DP,
penalised segmentation), kernel point resolvers, bracket categories, and the shared calibrate-and-decide step.

Every per-fact score excludes the fact's own page (a page has one date, so the chain engines get exact
leave-own-page-out posteriors from one forward-backward pass plus a local correction at that date).
Only labelled rows' labels are read (world.label is None elsewhere)."""
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
H = os.path.join(os.path.dirname(HERE), "harness")
for p in (HERE, H):
    if p not in sys.path:
        sys.path.insert(0, p)

from variants.v5 import groups  # noqa: E402  okey -> (flat idx sorted by date, consistency, equality)

NUMK = ("quantity", "money", "duration", "percent")


# ---------------------------------------------------------------- per-key structure
class Key:
    """One observation key (exp.py okey). Arrays over its n observations (sorted by date):
    g flat idx, row, date, page, role ('A' true anchor, 'F' false single-fact, 'M' false multi-fact,
    'V' vote = unlabelled or labelled unsure), nf facts in row, eq (op == eq).
    States: distinct canon values of eq observations, plus 'other' (an unseen value) as the last state.
    Ag[s, b] in {0, .5, 1}: observation b agrees with state s (other: 0 for eq obs, .5 for range obs)."""

    def __init__(self, world, okey, g, cons, nf):
        self.okey = okey
        self.g = g
        self.row = world.frow[g]
        self.date = world.date[self.row].astype(np.int64)
        self.page = world.page[self.row]
        self.n = len(g)
        lab = world.labelled[self.row]
        L = world.label[self.row]
        self.nf = nf[self.row]
        role = np.full(self.n, "V", dtype=object)
        role[lab & (L == "true")] = "A"
        role[lab & (L == "false") & (self.nf == 1)] = "F"
        role[lab & (L == "false") & (self.nf > 1)] = "M"
        self.role = role
        facts = [world.flat[n] for n in g]
        self.kind = facts[0].kind
        self.attr = okey[1]
        self.eq = np.array([f.op == "eq" for f in facts])
        codes, rep = {}, []
        for b, f in enumerate(facts):
            if f.op == "eq" and f.canon not in codes:
                codes[f.canon] = len(rep)
                rep.append(b)
        self.S = len(rep) + 1  # + other
        self.vals = [facts[b].canon for b in rep]
        Ag = np.zeros((self.S, self.n))
        if rep:
            Ag[:-1] = cons[np.array(rep)].astype(float)
        Ag[-1] = np.where(self.eq, 0.0, 0.5)
        self.Ag = Ag
        self.times, self.tix = np.unique(self.date, return_inverse=True)
        self.T = len(self.times)
        self.cons = cons
        # numeric order of value states (for monotone transitions)
        self.num = self.kind in NUMK and all(isinstance(v, float) for v in self.vals)
        # order of value states for monotone priors beyond numbers: dates by first day, versions by numeric parts
        self.order = np.array(self.vals, float) if self.num else None
        if self.kind == "date" and rep:
            self.order = np.array([facts[b].lo for b in rep], float)
        elif self.kind == "version" and rep:
            parts = [tuple(int(x) for x in re.findall(r"\d+", str(v))[:4]) for v in self.vals]
            if all(parts):
                rank = {p: i for i, p in enumerate(sorted(set(parts)))}
                self.order = np.array([rank[p] for p in parts], float)

    def loglik(self, p):
        """(S x n) log emission of each observation under each state, by role."""
        A = self.Ag
        out = np.zeros_like(A)
        ea, ef, r, wm = p["eps_a"], p["eps_f"], p["vote_lr"], p.get("wm", 0.0)
        m = self.role == "A"
        out[:, m] = np.log(ea + (1 - ea) * A[:, m])
        m = self.role == "F"
        out[:, m] = np.log(1 - (1 - ef) * A[:, m])
        m = self.role == "M"
        if wm:
            out[:, m] = np.log(1 - wm * (1 - ef) * A[:, m] / self.nf[m])
        m = self.role == "V"
        out[:, m] = np.log(1 - (1 - 1 / r) * (1 - A[:, m]))
        return out


def keys_of(world):
    cache = world.__dict__.setdefault("_f2_keys", None)
    if cache is not None:
        return cache
    nf = np.array([len(fs) for fs in world.facts])
    out = []
    for okey, (g, cons, same) in groups(world).items():
        out.append(Key(world, okey, g, cons, nf))
    world.__dict__["_f2_keys"] = out
    return out


# ---------------------------------------------------------------- hazard (staleness)
def attr_token(attr):
    t = [x for x in str(attr).split("_") if x]
    return t[-1] if t else str(attr)


def anchor_pairs(world):
    """Consecutive labelled-true eq anchors of each key on different dates: (gap days, same value, kind, token, attr)."""
    out = []
    for k in keys_of(world):
        a = np.flatnonzero((k.role == "A") & k.eq)
        if len(a) < 2:
            continue
        # one value per date (majority by first), consecutive dates
        last = None
        for b in a:
            if last is not None and k.date[b] > k.date[last]:
                same = bool(k.cons[b, last])
                up = None
                if not same and k.order is not None:
                    sb, sl = int(k.Ag[:-1, b].argmax()), int(k.Ag[:-1, last].argmax())
                    if k.order[sb] != k.order[sl]:
                        up = bool(k.order[sb] > k.order[sl])
                out.append((float(k.date[b] - k.date[last]), same, k.kind, attr_token(k.attr), k.attr, up))
            if last is None or k.date[b] > k.date[last]:
                last = b
    return out


def mle_lambda(gaps, same, prior_lam=1 / 200.0, prior_n=2.0):
    """MLE of lambda in P(same | g) = exp(-lambda g), with prior_n pseudo pairs at the prior mean gap."""
    gaps = np.asarray(gaps, float)
    same = np.asarray(same, bool)
    best = (None, -np.inf)
    g0 = 1 / prior_lam
    for lam in np.exp(np.linspace(np.log(1e-4), np.log(0.2), 160)):
        q = np.exp(-lam * gaps)
        ll = np.sum(np.where(same, -lam * gaps, np.log(np.clip(1 - q, 1e-12, 1))))
        # prior: prior_n pseudo pairs at gap g0, half same
        q0 = math.exp(-lam * g0)
        ll += prior_n * 0.5 * (-lam * g0) + prior_n * 0.5 * math.log(max(1 - q0, 1e-12))
        if ll > best[1]:
            best = (lam, ll)
    return float(best[0])


class Hazard:
    """lambda per class: 'global' | 'kind' | 'token' (attribute name last token, backs off to kind) | 'attr'."""

    def __init__(self, by="kind", min_pairs=8, mono_a=10.0, d0=0.1):
        self.by, self.min_pairs, self.mono_a, self.d0 = by, min_pairs, mono_a, d0
        self.glob, self.tab, self.down = 1 / 200.0, {}, {}

    def fit(self, world):
        P = anchor_pairs(world)
        if not P:
            return self
        g = np.array([x[0] for x in P]); s = np.array([x[1] for x in P])
        self.glob = mle_lambda(g, s)
        self.tab = {}
        # learned monotone prior per kind: P(down) ~ Beta posterior with prior mean d0 / (1 + d0) and strength
        # mono_a pseudo changes; weight of a downward switch d = P(down) / P(up), clipped to [0.01, 1]
        self.down = {}
        for kind in {x[2] for x in P}:
            ups = sum(1 for x in P if x[2] == kind and x[5] is True)
            dns = sum(1 for x in P if x[2] == kind and x[5] is False)
            pd = (dns + self.mono_a * self.d0 / (1 + self.d0)) / (ups + dns + self.mono_a)
            self.down[kind] = float(np.clip(pd / (1 - pd), 0.01, 1.0))
        for lvl, ix in (("kind", 2), ("token", 3), ("attr", 4)):
            vals = {}
            for x in P:
                vals.setdefault(x[ix], []).append(x)
            for c, xs in vals.items():
                if len(xs) >= self.min_pairs:
                    prior = self.tab.get(("kind", xs[0][2]), self.glob) if lvl != "kind" else self.glob
                    self.tab[(lvl, c)] = mle_lambda([x[0] for x in xs], [x[1] for x in xs], prior, 4.0)
        return self

    def lam(self, key):
        if self.by == "global":
            return self.glob
        kl = self.tab.get(("kind", key.kind), self.glob)
        if self.by == "kind":
            return kl
        if self.by == "token":
            return self.tab.get(("token", attr_token(key.attr)), kl)
        return self.tab.get(("attr", key.attr), self.tab.get(("token", attr_token(key.attr)), kl))


# ---------------------------------------------------------------- chain engines
def switch_matrix(k, p):
    """Row-stochastic off-diagonal switch distribution W (S x S)."""
    S = k.S
    W = np.ones((S, S))
    W[:, -1] = p.get("pi_o", 0.5)
    d = p.get("mono", 1.0)
    v = k.order if p.get("mono_all") else (np.array(k.vals) if k.num else None)
    if v is not None and d != 1.0 and S > 2:
        down = v[None, :] < v[:, None]
        W[:-1, :-1] = np.where(down, d, 1.0)
    np.fill_diagonal(W, 0.0)
    if S == 1:
        return np.ones((1, 1))
    return W / W.sum(1, keepdims=True)


def time_emissions(k, LL):
    """(T x S) summed log emissions per time point."""
    E = np.zeros((k.T, k.S))
    np.add.at(E, k.tix, LL.T)
    return E


def page_local(k, LL):
    """dict (page, t) -> (S,) summed log emissions of that page's observations at its time point."""
    out = {}
    for b in range(k.n):
        key = (int(k.page[b]), int(k.tix[b]))
        if key in out:
            out[key] = out[key] + LL[:, b]
        else:
            out[key] = LL[:, b].copy()
    return out


def hmm_post(k, p, lam):
    """Sum-product. -> dict (page, t) -> posterior over states at t from every observation not on that page."""
    LL = k.loglik(p)
    E = time_emissions(k, LL)
    W = switch_matrix(k, p)
    S, T = k.S, k.T
    prior = np.ones(S)
    prior[-1] = p.get("pi_o", 0.5)
    prior /= prior.sum()
    gaps = np.diff(k.times).astype(float)
    stay = np.exp(-lam * gaps)
    Es = np.exp(E - E.max(1, keepdims=True))
    pred = np.zeros((T, S)); beta = np.ones((T, S))
    a = prior
    for t in range(T):
        pred[t] = a
        al = a * Es[t]
        al /= al.sum()
        if t < T - 1:
            a = stay[t] * al + (1 - stay[t]) * (al @ W)
    for t in range(T - 2, -1, -1):
        v = Es[t + 1] * beta[t + 1]
        b = stay[t] * v + (1 - stay[t]) * (W @ v)
        beta[t] = b / b.sum()
    out = {}
    for (q, t), loc in page_local(k, LL).items():
        e = E[t] - loc
        x = pred[t] * np.exp(e - e.max()) * beta[t]
        out[q, t] = x / x.sum()
    return out


def max_chain(k, logE, logstay, logsw, Wlog):
    """Max-product over time points. logstay[t], logsw[t]: log P(stay), log P(switch) between t and t+1;
    Wlog (S x S) log switch distribution (diag ignored). -> predM (T x S), bM (T x S), bp, fp pointers."""
    S, T = k.S, k.T
    predM = np.zeros((T, S)); bM = np.zeros((T, S))
    bp = np.zeros((T, S), np.int64); fp = np.zeros((T, S), np.int64)
    a = np.zeros(S)
    for t in range(T):
        predM[t] = a
        if t < T - 1:
            d = a + logE[t]
            M = d[:, None] + logsw[t] + Wlog  # from s' (rows) to s (cols)
            np.fill_diagonal(M, d + logstay[t])
            bp[t + 1] = M.argmax(0)
            a = M.max(0)
            a = a - a.max()
    for t in range(T - 2, -1, -1):
        v = logE[t + 1] + bM[t + 1]
        M = v[None, :] + logsw[t] + Wlog
        np.fill_diagonal(M, v + logstay[t])
        fp[t] = M.argmax(1)
        b = M.max(1)
        bM[t] = b - b.max()
    return predM, bM, bp, fp


def chain_max_scores(k, p, lam, mode):
    """mode 'viterbi': HMM log probabilities; 'tecore': additive weights (agree with vote +w_v, anchor
    disagreement -H, false anchor agreement -H, switch -C); 'seg': HMM emissions with constant switch penalty
    beta = c * log(n). -> (logE, logstay, logsw, Wlog)."""
    T = k.T
    gaps = np.diff(k.times).astype(float)
    if mode == "tecore":
        A = k.Ag
        LL = np.zeros_like(A)
        Hh, wv = p.get("H", 50.0), p.get("w_v", 1.0)
        m = k.role == "A"; LL[:, m] = -Hh * (A[:, m] < 0.5) - 0.5 * Hh * (A[:, m] == 0.5)
        m = k.role == "F"; LL[:, m] = -Hh * (A[:, m] > 0.5)
        m = k.role == "V"; LL[:, m] = wv * A[:, m]
        Cc = p.get("C", 2.0)
        logstay = np.zeros(max(T - 1, 0)); logsw = np.full(max(T - 1, 0), -Cc)
        Wlog = np.zeros((k.S, k.S))
        Wlog[:, -1] = -p.get("C_o", 1.0)
        v = k.order if p.get("mono_all") else (np.array(k.vals) if k.num else None)
        if v is not None and p.get("mono_pen", 0.0) and k.S > 2:
            Wlog[:-1, :-1] = np.where(v[None, :] < v[:, None], -p["mono_pen"], 0.0)
    else:
        LL = k.loglik(p)
        W = switch_matrix(k, p)
        with np.errstate(divide="ignore"):
            Wlog = np.log(W)
        if mode == "viterbi":
            stay = np.exp(-lam * gaps)
            logstay = np.log(stay); logsw = np.log(np.clip(1 - stay, 1e-300, 1))
        else:  # seg: constant penalty, BIC-like
            beta = p.get("c", 1.0) * math.log(max(k.n, 2))
            logstay = np.zeros(max(T - 1, 0)); logsw = np.full(max(T - 1, 0), -beta)
    return LL, logstay, logsw, Wlog


def max_marginals(k, p, lam, mode, walk=False):
    """-> dict (page, t) -> (maxmarg (S,), extras) excluding that page; extras (if walk) = (s*, left change
    time or None, right change time or None, segment [t0, t1])."""
    LL, logstay, logsw, Wlog = chain_max_scores(k, p, lam, mode)
    logE = time_emissions(k, LL)
    predM, bM, bp, fp = max_chain(k, logE, logstay, logsw, Wlog)
    out = {}
    for (q, t), loc in page_local(k, LL).items():
        mm = predM[t] + logE[t] - loc + bM[t]
        ex = None
        if walk:
            s = int(mm.argmax())
            tl, cur = t, s
            while tl > 0:
                prev = bp[tl, cur]
                if prev != cur:
                    break
                tl -= 1
            tr, cur = t, s
            while tr < k.T - 1:
                nxt = fp[tr, cur]
                if nxt != cur:
                    break
                tr += 1
            ex = (s, tl, tr)
        out[q, t] = (mm, ex)
    return out


# ---------------------------------------------------------------- kernel point resolvers
def kernel_w(dtd, p):
    """dtd = D - d_obs. Kernel weight by type: exp | tri | box; asymmetric beta on later observations."""
    tau = p["tau"]
    a = np.abs(dtd).astype(float)
    kt = p.get("kernel", "exp")
    if kt == "exp":
        w = np.exp(-a / tau)
    elif kt == "tri":
        w = np.clip(1 - a / tau, 0, None)
    else:
        w = (a <= tau).astype(float)
    return np.where(dtd >= 0, w, p.get("beta", 1.0) * w)


def point_scores(world, p):
    """Per fact (sp, sm, has): mode 'kernel' = weighted agree / disagree mass (anchors wa, votes wu, false
    anchors as negative evidence wf); 'latest' = latest anchor at/before D (fallback earliest after);
    'nearest' = nearest anchor in |dt| (ties: before); 'bracket' = latest-before, but a mismatch confirmed by
    the next anchor after D counts as agreement (V2b). Votes stand in when no anchor exists (fallback)."""
    sp = np.zeros(world.n_facts); sm = np.zeros(world.n_facts)
    mode = p.get("mode", "kernel")
    for k in keys_of(world):
        A = k.cons.astype(float)
        other = k.page[:, None] != k.page[None, :]
        dtd = (k.date[:, None] - k.date[None, :]).astype(float)
        isA = k.role == "A"; isF = k.role == "F"; isV = k.role == "V"
        if mode == "kernel":
            K = kernel_w(dtd, p) * other
            w = np.where(isA, p.get("wa", 1.0), np.where(isV, p.get("wu", 0.3), 0.0))
            a = (K * w[None, :] * A).sum(1)
            b = (K * w[None, :] * (1 - A)).sum(1) + (K * (p.get("wf", 0.0) * isF)[None, :] * A).sum(1)
            sp[k.g] = a; sm[k.g] = b
            continue
        for x in range(k.n):
            for pool in (isA, isV):
                cand = np.flatnonzero(pool & other[x])
                if len(cand):
                    break
            if not len(cand):
                continue
            d = dtd[x, cand]  # >= 0: before or same day
            wgt = 1.0 if pool is isA else p.get("wu", 0.3)
            if mode == "nearest":
                m = np.abs(d).min()
                pick = cand[np.abs(d) == m]
                bef = pick[dtd[x, pick] >= 0]
                pick = bef if len(bef) else pick
            else:
                bef = cand[d >= 0]
                if len(bef):
                    pick = bef[dtd[x, bef] == dtd[x, bef].min()]
                else:
                    aft = cand
                    pick = aft[dtd[x, aft] == dtd[x, aft].max()]
            agree = A[x, pick].mean()
            if mode == "bracket" and agree <= 0.5 and (d >= 0).any():
                aft = cand[d < 0]
                if len(aft):
                    nx = aft[dtd[x, aft] == dtd[x, aft].max()]
                    if A[x, nx].mean() > 0.5:
                        agree = A[x, nx].mean()
            sp[k.g[x]] = wgt * agree; sm[k.g[x]] = wgt * (1 - agree)
    return sp, sm


# ---------------------------------------------------------------- bracket categories
def bracket_cells(world, vote_fallback=True, gapb=None):
    """Per fact: (before, same, after) symbols. Y/N = nearest labelled-true anchor (other page) on that side
    agrees / disagrees (majority at the nearest date); y/n = no anchor, nearest votes; '-' nothing.
    gapb: optional day threshold; appends 'c'/'f' (close / far) to the before and after symbols."""
    cells = [None] * world.n_facts
    for k in keys_of(world):
        A = k.cons
        other = k.page[:, None] != k.page[None, :]
        isA = k.role == "A"; isV = k.role == "V"
        for x in range(k.n):
            D = k.date[x]
            sym = []
            for side in ("b", "s", "a"):
                s = "-"
                for pool, (yes, no) in ((isA, "YN"), (isV, "yn")):
                    if pool is isV and not vote_fallback:
                        break
                    c = np.flatnonzero(pool & other[x])
                    if side == "b":
                        c = c[k.date[c] < D]
                        if len(c): c = c[k.date[c] == k.date[c].max()]
                    elif side == "a":
                        c = c[k.date[c] > D]
                        if len(c): c = c[k.date[c] == k.date[c].min()]
                    else:
                        c = c[k.date[c] == D]
                    if len(c):
                        s = yes if A[x, c].mean() > 0.5 else no
                        if gapb and side != "s":
                            s += "c" if abs(int(k.date[c[0]]) - int(D)) <= gapb else "f"
                        break
                sym.append(s)
            cells[k.g[x]] = "".join(sym) if not gapb else "|".join(sym)
    return cells


# ---------------------------------------------------------------- targets, calibration, decision
def two_class(world):
    """True if the world's labelled rows hold both true and false (refit possible)."""
    lab = world.label[world.labelled]
    return bool((lab == "true").any() and (lab == "false").any())


def fact_targets(world):
    """v9 targets: 1 = fact of a labelled true row, 0 = fact of a labelled single-fact false row, -1 otherwise."""
    nf = np.array([len(fs) for fs in world.facts])
    lab = world.label[world.frow]
    y = np.where(lab == "true", 1, np.where((lab == "false") & (nf[world.frow] == 1), 0, -1))
    y[~world.labelled[world.frow]] = -1
    return y


class FactMap:
    """Monotone map score -> P(fact true), fitted on labelled facts (isotonic, or Platt on the score);
    NaN score (no other-page evidence) -> smoothed rate of labelled facts with NaN score."""

    def __init__(self, how="iso"):
        self.how = how

    def fit(self, s, y):
        from sklearn.isotonic import IsotonicRegression
        from sklearn.linear_model import LogisticRegression
        m = y >= 0
        base = float(np.mean(y[m])) if m.any() else 0.85
        nan = m & np.isnan(s)
        self.nan_p = (float(np.sum(y[nan])) + 4 * max(base, 0.9)) / (nan.sum() + 4)
        ok = m & ~np.isnan(s)
        self.const = None
        if ok.sum() < 5 or len(set(y[ok])) < 2:
            self.const = base
            return self
        if self.how == "iso":
            self.m = IsotonicRegression(out_of_bounds="clip", y_min=0.005, y_max=0.995).fit(s[ok], y[ok])
        else:
            self.m = LogisticRegression(C=10.0).fit(s[ok, None], y[ok])
        return self

    def __call__(self, s):
        out = np.full(len(s), self.nan_p)
        ok = ~np.isnan(s)
        if self.const is not None:
            out[ok] = self.const
        elif self.how == "iso":
            out[ok] = self.m.predict(s[ok])
        else:
            out[ok] = self.m.predict_proba(s[ok, None])[:, 1]
        return np.clip(out, 1e-4, 1 - 1e-4)


def row_prob(world, pf, agg="prod"):
    out = np.ones(world.n)
    if agg == "prod":
        np.multiply.at(out, world.frow, pf)
    else:
        np.minimum.at(out, world.frow, pf)
    return out


def decide(pt, t, band):
    out = np.where(pt >= t, "true", "false").astype(object)
    out[np.abs(pt - t) < band] = "unsure"
    return out


class RowCal:
    """Row isotonic (or Platt on logit) on labelled true/false rows -> pc = P(true | not unsure). u = share of
    unsure among labelled rows. rule 'arena' (default): exact expected-points decision
    argmax{true: 2(1-u)pc - 1, false: 2(1-u)(1-pc) - 1, unsure: u}; confidence = (1-u)pc or (1-u)(1-pc), at least
    0.5. rule 'search': (threshold, unsure band) chosen by arena points on the labelled rows (the g1 grid)."""

    def __init__(self, how="iso", rule="arena"):
        self.how, self.rule = how, rule

    def fit(self, prow, world):
        from sklearn.isotonic import IsotonicRegression
        from sklearn.linear_model import LogisticRegression
        tr = world.labelled & (np.array([len(f) for f in world.facts]) > 0)
        Y = world.label
        m = tr & np.isin(Y, ["true", "false"])
        y = (Y[m] == "true").astype(float)
        self.u = float(np.mean(Y[tr] == "unsure")) if tr.any() else 0.0
        self.iso = None
        if m.sum() >= 5 and 0 < y.sum() < len(y):
            if self.how == "iso":
                self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(prow[m], y)
            else:
                z = np.log(np.clip(prow[m], 1e-6, 1)) - np.log(np.clip(1 - prow[m], 1e-6, 1))
                self.iso = LogisticRegression(C=10.0).fit(z[:, None], y)
        if self.rule == "arena":
            self.t, self.band = 0.5, max(0.0, (1 + self.u) / (2 * (1 - self.u)) - 0.5)
            return self
        pc = self.map(prow)
        ytr = Y[tr].astype(str)
        best = None
        for t in (0.5, 0.45, 0.55, 0.4, 0.6):  # ties resolve toward 0.5 (calibrated decision point)
            for band in (0.0, 0.03, 0.06, 0.1):
                o = decide(pc[tr], t, band).astype(str)
                sc = float(np.mean(np.where(o == "unsure", np.where(ytr == "unsure", 1, 0),
                                            np.where(o == ytr, 1, -1))))
                if best is None or sc > best[0] + 1e-12:
                    best = (sc, t, band)
        self.t, self.band = best[1], best[2]
        return self

    def map(self, prow):
        if self.iso is None:
            return prow
        if self.how == "iso":
            return self.iso.predict(prow)
        z = np.log(np.clip(prow, 1e-6, 1)) - np.log(np.clip(1 - prow, 1e-6, 1))
        return self.iso.predict_proba(z[:, None])[:, 1]

    def predict(self, prow, world):
        pc = self.map(prow)
        out = decide(pc, self.t, self.band)
        nofacts = np.array([len(f) == 0 for f in world.facts])
        out[nofacts] = "unsure"
        q = (1 - self.u) if self.rule == "arena" else 1.0
        conf = np.maximum(0.5, q * np.where(out == "true", pc, 1 - pc))  # confidence of the label, in [0.5, 1]
        conf = np.where(out == "unsure", np.nan, conf)
        return out, conf
