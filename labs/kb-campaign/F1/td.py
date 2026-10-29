"""F1 truth-discovery core: every method maps a World to P(fact true on its row's date) per flat fact
plus a per-page reliability. Observation level: each stated fact is a claim by its page (the source);
other-page claims of the same typed key (world.obs_typed) vote with a time kernel. Labelled rows of the
world are anchors (true rows: hard evidence for their values; single-fact false rows: their value is
false at their date; multi-fact false rows: blame-weighted). Nothing here reads gold of unlabelled rows.

Methods (fn(world, **p) -> (pf, page_rel, extra)):
  vote, truthfinder, accu (+ copy, dyna, liar, slim), crh, ds, ltm, dynworld (lifespan HMM), sums, avglog
"""
import math

import numpy as np

from variants.v5 import groups as v5_groups

EPS = 1e-9


# ---------------------------------------------------------------- world structures
def graph(world):
    """Edge list over ordered pairs (n, m) of facts with the same okey on different pages.
    dt = date(n) - date(m) (positive: m is before n). cons = interval overlap (exp.py V5), cont = m's
    interval inside n's (m true implies n true), same = equal canon. cid = global canon class id per fact."""
    c = world.__dict__.get("_f1_graph")
    if c is not None:
        return c
    fdate = world.date[world.frow].astype(np.int64)
    fpage = world.page[world.frow]
    N, M, CO, CT, SA = [], [], [], [], []
    cid = np.zeros(world.n_facts, np.int64)
    gid = np.zeros(world.n_facts, np.int64)
    ncls = 0
    for k, (g, cons, same) in enumerate(v5_groups(world).values()):
        gid[g] = k
        fs = [world.flat[x] for x in g]
        codes = {}
        cc = np.array([codes.setdefault(f.canon, len(codes)) for f in fs])
        cid[g] = cc + ncls
        ncls += len(codes)
        if fs[0].lo is None:
            cont = same
        else:
            lo = np.array([f.lo for f in fs], float)
            hi = np.array([f.hi for f in fs], float)
            tol = 1e-9 * np.maximum(1.0, np.where(np.isinf(lo), 1.0, np.abs(lo)))
            with np.errstate(invalid="ignore"):
                cont = (lo[:, None] <= lo[None, :] + tol[:, None]) & (hi[None, :] <= hi[:, None] + tol[:, None])
            cont |= same
        other = fpage[g][:, None] != fpage[g][None, :]
        a, b = np.nonzero(other)
        N.append(g[a]); M.append(g[b]); CO.append(cons[a, b]); CT.append(cont[a, b]); SA.append(same[a, b])
    cat = lambda xs, t: np.concatenate(xs).astype(t) if xs else np.zeros(0, t)  # noqa: E731
    G = dict(N=cat(N, np.int64), M=cat(M, np.int64), cons=cat(CO, bool), cont=cat(CT, bool), same=cat(SA, bool),
             cid=cid, gid=gid, ncls=ncls, fdate=fdate, fpage=fpage)
    G["dt"] = (fdate[G["N"]] - fdate[G["M"]]).astype(np.float64)
    G["nf_row"] = np.array([len(fs) for fs in world.facts], np.int64)
    G["psize"] = np.bincount(fpage, minlength=world.n_pages).astype(float)
    # exact-duplicate claims (same normalised row text, same fact position): only the earliest counts (dedup)
    tid = {}
    rcl = np.array([tid.setdefault(" ".join(t.casefold().split()), len(tid)) for t in world.text], np.int64)
    G["tcl"] = rcl[world.frow]
    fcl = G["tcl"] * 64 + world.fidx[:, 1]
    order = np.lexsort((fpage, fdate))
    _, first = np.unique(fcl[order], return_index=True)
    dupe = np.ones(world.n_facts, bool); dupe[order[first]] = False
    G["dupe"] = dupe
    world.__dict__["_f1_graph"] = G
    return G


def roles(world):
    """Per flat fact: A labelled-true anchor, NEG labelled false single-fact, MF labelled false multi-fact,
    LAT everything else (unlabelled, labelled unsure)."""
    lab = world.label[world.frow]
    lb = world.labelled[world.frow]
    nf = np.array([len(fs) for fs in world.facts])[world.frow]
    A = lb & (lab == "true")
    NEG = lb & (lab == "false") & (nf == 1)
    MF = lb & (lab == "false") & (nf > 1)
    return dict(A=A, NEG=NEG, MF=MF, LAT=~(A | NEG | MF))


def kernel(dt, tau=30.0, beta=1.0, win=None):
    """Weight of an observation dt days before (dt > 0) or -dt after (beta) the scored fact."""
    K = np.ones_like(dt) if tau is None or tau == float("inf") else np.exp(-np.abs(dt) / tau)
    if beta != 1.0:
        K = np.where(dt >= 0, K, beta * K)
    if win is not None:
        K = K * (np.abs(dt) <= win)
    return K


def edges(G, p):
    """Kernel weights for the edge list, edges with zero weight dropped (index array returned)."""
    K = kernel(G["dt"], p.get("tau", 30.0), p.get("beta", 1.0), p.get("win"))
    ok = K > 0
    if p.get("dedup"):  # a copy never supports its original, and later copies of a claim do not vote
        ok &= (G["tcl"][G["N"]] != G["tcl"][G["M"]]) & ~G["dupe"][G["M"]]
    keep = np.flatnonzero(ok)
    return keep, K[keep]


def row_prod(world, pf):
    pr = np.ones(world.n)
    np.multiply.at(pr, world.frow, pf)
    return pr


def blame(world, pf, MF):
    """P(fact true | its row is false) = P_n (1 - prod_{j != n} P_j) / (1 - prod_j P_j) for MF facts."""
    out = pf.copy()
    if not MF.any():
        return out
    pr = row_prod(world, np.clip(pf, 1e-6, 1 - 1e-6))
    q = np.clip(pf, 1e-6, 1 - 1e-6)
    rest = pr[world.frow] / q
    out[MF] = (q * (1 - rest) / np.maximum(1 - pr[world.frow], 1e-9))[MF]
    return out


def page_mean(world, G, val, alpha, prior):
    s = np.bincount(G["fpage"], val, world.n_pages)
    return (s + alpha * prior) / (G["psize"] + alpha), s


def page_loo(world, G, val, alpha, prior):
    """Reliability of each fact's page computed without the fact's own row."""
    s = np.bincount(G["fpage"], val, world.n_pages)
    rs = np.bincount(world.frow, val, world.n)[world.frow]
    nr = G["nf_row"][world.frow]
    return (s[G["fpage"]] - rs + alpha * prior) / (G["psize"][G["fpage"]] - nr + alpha)


def clamp(pf, R, mf_pf=None):
    pf = pf.copy()
    pf[R["A"]] = 1.0
    pf[R["NEG"]] = 0.0
    if mf_pf is not None:
        pf[R["MF"]] = mf_pf[R["MF"]]
    return pf


def sig(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


# ---------------------------------------------------------------- shared vote aggregation
def aggregate(world, G, keep, K, wv, wneg, sup_mode="overlap", rho_partial=0.0):
    """sup[n] = sum K wv[m] over supporting m; con[n] = sum K wv[m] over disjoint m (+ NEG facts consistent
    with n via wneg). Returns sup, con, and the per-(n, competitor class) masses for softmax methods."""
    N, M = G["N"][keep], G["M"][keep]
    cons, cont = G["cons"][keep], G["cont"][keep]
    nfx = world.n_facts
    w = K * wv[M]
    if sup_mode == "contain":
        sm = np.where(cont, 1.0, np.where(cons, rho_partial, 0.0))
    else:
        sm = cons.astype(float)
    sup = np.bincount(N, w * sm, nfx)
    dis = ~cons
    con = np.bincount(N, w * dis, nfx)
    neg = np.bincount(N, K * wneg[M] * cons, nfx)
    return sup, con, neg, (N, M, dis, w)


# ---------------------------------------------------------------- 1. vote baselines
def vote(world, dedup=False, wu=1.0, wa=1.0, wneg=1.0, wmf=0.0, tau=None, beta=1.0, win=None, sup="overlap", a=1.0,
         prior=0.8, anchors="soft", **_):
    """Unweighted (tau=None, win=None), windowed (win) or decayed (tau, beta) vote of all other-page claims.
    anchors='soft': labelled true facts vote with weight wa; 'hard': where any anchor is in reach of a fact,
    only anchors (and NEG) decide it; 'off': labels ignored, everything is a plain vote."""
    G, R = graph(world), roles(world)
    keep, K = edges(G, dict(tau=tau, beta=beta, win=win, dedup=dedup))
    if anchors == "off":
        wv = np.full(world.n_facts, wu); wn = np.zeros(world.n_facts)
    else:
        wv = np.where(R["A"], wa, np.where(R["NEG"], 0.0, np.where(R["MF"], wmf, wu)))
        wn = np.where(R["NEG"], wneg, 0.0)
    mode = sup
    sup, con, neg, _ = aggregate(world, G, keep, K, wv, wn, mode)
    if anchors == "hard":
        wva = np.where(R["A"], 1.0, 0.0); wna = np.where(R["NEG"], wneg, 0.0)
        s2, c2, n2, _ = aggregate(world, G, keep, K, wva, wna, mode)
        has = (s2 + c2 + n2) > 0
        sup, con, neg = np.where(has, s2, sup), np.where(has, c2, con), np.where(has, n2, neg)
    pf = (sup + a * prior) / (sup + con + neg + a)
    ev = sup + con + neg
    return pf, None, dict(sup=sup, con=con + neg, ev=ev)


# ---------------------------------------------------------------- 2. TruthFinder (+ temporal)
def truthfinder(world, dedup=False, t0=0.9, gamma=0.3, rho=0.5, rho_partial=0.3, tau=None, beta=1.0, win=None, sup="contain",
                ta=0.999, wneg=1.0, alpha=2.0, iters=20, selfw=1.0, **_):
    """Yin, Han, Yu: trust t(p) -> tau(p) = -ln(1 - t); claim score s*(n) = own page tau + sum over other
    claims of K * tau(m) * imp(m -> n), imp = +1 (m implies n: contained / equal), rho_partial (overlap),
    -rho (disjoint); conf = sigmoid(gamma s*); t(p) = smoothed mean conf of the page's claims.
    Anchors: tau = -ln(1 - ta); single-fact false rows subtract their weight from consistent claims."""
    G, R = graph(world), roles(world)
    keep, K = edges(G, dict(tau=tau, beta=beta, win=win, dedup=dedup))
    N, M = G["N"][keep], G["M"][keep]
    cons, cont = G["cons"][keep], G["cont"][keep]
    imp = np.where(cont, 1.0, np.where(cons, rho_partial, -rho)) if sup == "contain" else np.where(cons, 1.0, -rho)
    t = np.full(world.n_pages, t0)
    ta_w = -math.log(1 - ta)
    conf = np.full(world.n_facts, t0)
    for it in range(iters):
        tp = -np.log(1 - np.clip(t, 1e-6, 1 - 1e-6))
        tv = tp[G["fpage"]]
        wv = np.where(R["A"], ta_w, np.where(R["NEG"], 0.0, np.where(R["MF"], ta_w * conf, tv)))
        s = selfw * page_loo_tau(world, G, conf, alpha, t0) + np.bincount(N, K * wv[M] * imp, world.n_facts)
        s -= np.bincount(N, K * np.where(R["NEG"], wneg * ta_w, 0.0)[M] * cons, world.n_facts)
        new = sig(gamma * s)
        mf = blame(world, new, R["MF"])
        conf = clamp(new, R, mf)
        t_new, _ = page_mean(world, G, conf, alpha, t0)
        if np.max(np.abs(t_new - t)) < 1e-5:
            t = t_new
            break
        t = t_new
    return new, t, dict(score=s)


def page_loo_tau(world, G, conf, alpha, prior):
    return -np.log(1 - np.clip(page_loo(world, G, conf, alpha, prior), 1e-6, 1 - 1e-6))


# ---------------------------------------------------------------- 6. Accu / AccuCopy (+ dyna, liar, slim)
def copy_prob(world, G, keep, P, A, c=0.8, alpha=0.1, nfalse=10, wcopy=None):
    """AccuCopy dependence between page pairs from shared same-value claims (true and false, by current
    posterior P) and different-value claims within the copy window. Returns per-edge P(copy) for edges."""
    N, M = G["N"][keep], G["M"][keep]
    if wcopy is not None:
        ok = np.abs(G["dt"][keep]) <= wcopy
        N, M, idx = N[ok], M[ok], keep[ok]
    else:
        idx = keep
    pn, pm = G["fpage"][N], G["fpage"][M]
    upper = pn < pm  # count each unordered pair once
    same = G["same"][idx]
    key = pn * world.n_pages + pm
    ku = key[upper]
    u, inv = np.unique(ku, return_inverse=True)
    pt = P[N[upper]]
    kt = np.bincount(inv, same[upper] * pt, len(u))
    kf = np.bincount(inv, same[upper] * (1 - pt), len(u))
    kd = np.bincount(inv, (~same[upper]).astype(float), len(u))
    a, b = u // world.n_pages, u % world.n_pages
    Aa = np.clip((A[a] + A[b]) / 2, 0.05, 0.99)
    Pt, Pf = Aa ** 2, (1 - Aa) ** 2 / nfalse
    Pd = np.clip(1 - Pt - Pf, 1e-6, 1)
    lr = (kt * np.log((Aa * c + Pt * (1 - c)) / Pt) + kf * np.log(((1 - Aa) * c + Pf * (1 - c)) / Pf)
          + kd * math.log(1 - c))
    pc = sig(math.log(alpha / (1 - alpha)) + lr)
    # map back to every edge in keep (both directions)
    pa, pb = G["fpage"][G["N"][keep]], G["fpage"][G["M"][keep]]
    k2 = np.minimum(pa, pb) * world.n_pages + np.maximum(pa, pb)
    if not len(u):
        return np.zeros(len(k2))
    pos = np.clip(np.searchsorted(u, k2), 0, len(u) - 1)
    out = np.where(u[pos] == k2, pc[pos], 0.0)
    if wcopy is not None:
        out = np.where(np.abs(G["dt"][keep]) <= wcopy, out, 0.0)
    return out


def independence(world, G, keep, pc, c=0.8):
    """Per fact (as a voter): prod over same-value claims of the key that are earlier (date, then page id)
    of (1 - c * P(copy between the two pages)). A copied claim then votes once, not k times."""
    N, M = G["N"][keep], G["M"][keep]
    same = G["same"][keep]
    dn, dm = G["fdate"][N], G["fdate"][M]
    earlier = (dm < dn) | ((dm == dn) & (G["fpage"][M] < G["fpage"][N]))
    lg = np.log(np.clip(1 - c * pc, 1e-6, 1)) * (same & earlier)
    return np.exp(np.bincount(N, lg, world.n_facts))


def accu(world, dedup=False, A0=0.8, Aa=0.99, nfalse=10, tau=30.0, beta=1.0, win=None, sup="overlap", rho_partial=0.0,
         wneg=1.0, alpha=3.0, iters=20, selfw=1.0, copy=False, c=0.8, calpha=0.1, wcopy=None, dyna=None,
         liar=False, slim=None, softmax=True, prior_A=None, **_):
    """Dong, Berti-Equille, Srivastava (Accu): a claim by a source of accuracy A votes ln(nfalse A / (1 - A))
    for its value; P(value) = softmax over the claimed values (own, each disjoint competitor class, and
    nfalse unclaimed values at vote 0), all votes kernel-weighted by time distance to the scored claim.
    Page accuracy = Beta-smoothed mean posterior of its claims (labelled rows clamped: semi-supervised).
    copy=True: AccuCopy, voters discounted by their independence factor. dyna=(kappa, h): DynaTD-style
    smoothing of page accuracy toward the accuracy of pages near the same date. liar=True: page accuracy
    restricted to a two-level honest/liar mixture (EM). slim: per-fact prior accuracy array (SLiMFast)."""
    G, R = graph(world), roles(world)
    keep, K = edges(G, dict(tau=tau, beta=beta, win=win, dedup=dedup))
    N, M = G["N"][keep], G["M"][keep]
    cons, cont = G["cons"][keep], G["cont"][keep]
    smask = np.where(cont, 1.0, np.where(cons, rho_partial, 0.0)) if sup == "contain" else cons.astype(float)
    dis = ~cons
    wa = math.log(nfalse * Aa / (1 - Aa))
    A = np.full(world.n_pages, A0) if prior_A is None else prior_A.copy()
    P = np.full(world.n_facts, A0)
    P = clamp(P, R, np.full(world.n_facts, 0.5))
    ind = np.ones(world.n_facts)
    hl = np.array([0.95, 0.5]); hw = 0.8
    for it in range(iters):
        Af = A[G["fpage"]] if slim is None else np.clip(0.5 * A[G["fpage"]] + 0.5 * slim, 0.02, 0.995)
        Af = np.clip(Af, 0.02, 0.995)
        wl = np.log(nfalse * Af / (1 - Af))
        wv = np.where(R["A"], wa, np.where(R["NEG"], 0.0, np.where(R["MF"], np.log(nfalse * np.clip(P, 0.02, 0.98) / (1 - np.clip(P, 0.02, 0.98))), wl)))
        wv = wv * ind
        wn = np.where(R["NEG"], wneg * wa, 0.0)
        w = K * wv[M]
        own = np.bincount(N, w * smask, world.n_facts) - np.bincount(N, K * wn[M] * cons, world.n_facts)
        if selfw:
            Aself = np.clip(page_loo(world, G, P, alpha, A0), 0.02, 0.995) if slim is None else np.clip(slim, 0.02, 0.995)
            own = own + selfw * np.log(nfalse * Aself / (1 - Aself))
        if softmax:
            sel = dis
            code = N[sel] * (G["ncls"] + 1) + G["cid"][M[sel]]
            u, inv = np.unique(code, return_inverse=True)
            mass = np.bincount(inv, w[sel], len(u)) if len(u) else np.zeros(0)
            owner = u // (G["ncls"] + 1) if len(u) else np.zeros(0, np.int64)
            ex = np.exp(np.clip(mass - own[owner], -60, 60))
            den = 1 + np.bincount(owner, ex, world.n_facts) + nfalse * np.exp(np.clip(-own, -60, 60))
            new = 1.0 / den
        else:
            con = np.bincount(N, w * dis, world.n_facts)
            new = sig(own - con)
        mfp = blame(world, new, R["MF"])
        P = clamp(new, R, mfp)
        if liar:  # two-level page accuracy: honest hl[0] or liar hl[1], posterior per page
            s = np.bincount(G["fpage"], P, world.n_pages); n = G["psize"]
            lh = s * np.log(hl[0]) + (n - s) * np.log(1 - hl[0]) + math.log(hw)
            ll = s * np.log(hl[1]) + (n - s) * np.log(1 - hl[1]) + math.log(1 - hw)
            ph = sig(lh - ll)
            hw = float(np.clip(ph.mean(), 0.05, 0.99))
            hl = np.array([np.clip((ph * s).sum() / max((ph * n).sum(), 1e-9), 0.6, 0.999),
                           np.clip(((1 - ph) * s).sum() / max(((1 - ph) * n).sum(), 1e-9), 0.05, 0.9)])
            A_new = ph * hl[0] + (1 - ph) * hl[1]
        else:
            A_new, _ = page_mean(world, G, P, alpha, A0)
        if dyna is not None:
            kappa, h = dyna
            pd = np.full(world.n_pages, 0.0)
            pd[G["fpage"]] = G["fdate"]
            order = np.argsort(pd)
            ds, As, ns = pd[order], A_new[order], G["psize"][order]
            # kernel-smoothed accuracy of pages around the same date (window +-3h, exponential weights)
            cs_w = np.cumsum(ns); cs_a = np.cumsum(ns * As)
            lo = np.searchsorted(ds, ds - h, "left"); hi = np.searchsorted(ds, ds + h, "right") - 1
            tot = cs_w[hi] - np.where(lo > 0, cs_w[lo - 1], 0); acc = cs_a[hi] - np.where(lo > 0, cs_a[lo - 1], 0)
            Abar = np.empty(world.n_pages); Abar[order] = acc / np.maximum(tot, 1e-9)
            A_new = (G["psize"] * A_new + kappa * Abar) / (G["psize"] + kappa)
        if copy and it >= 1:
            pc = copy_prob(world, G, keep, P, A_new, c, calpha, nfalse, wcopy)
            ind = independence(world, G, keep, pc, c)
        if np.max(np.abs(A_new - A)) < 1e-5 and it > 1:
            A = A_new
            break
        A = A_new
    extra = dict(own=own, ind=ind, A=A)
    return new, A, extra


# ---------------------------------------------------------------- 3. CRH
def crh(world, dedup=False, tau=30.0, beta=1.0, win=None, wa=5.0, wneg=1.0, iters=10, numeric=True, agg="mean", a=1.0,
        prior=0.8, **_):
    """Li et al. CRH: source weight w_p = log(sum_q L_q / L_p) from each page's (mean or summed) loss against
    the current truths; truth at a claim's date = weighted kernel vote among all claims of the key
    (categorical loss 0/1 against the winner; numeric eq claims: relative distance to the winner, capped 1).
    Output score: weighted support share (sup + a prior) / (sup + con + a), ranked, calibrated outside."""
    G, R = graph(world), roles(world)
    keep, K = edges(G, dict(tau=tau, beta=beta, win=win, dedup=dedup))
    N, M = G["N"][keep], G["M"][keep]
    cons = G["cons"][keep]
    wp = np.ones(world.n_pages)
    isnum = np.array([isinstance(f.canon, float) and f.op == "eq" for f in world.flat])
    val = np.array([f.canon if isinstance(f.canon, float) else np.nan for f in world.flat])
    for it in range(iters):
        wv = np.where(R["A"], wa, np.where(R["NEG"], 0.0, wp[G["fpage"]]))
        wn = np.where(R["NEG"], wneg * wa, 0.0)
        w = K * wv[M]
        own = np.bincount(N, w * cons, world.n_facts) - np.bincount(N, K * wn[M] * cons, world.n_facts)
        own_self = own + wv  # the claim's own vote for the truth estimate (CRH uses all claims)
        dis = ~cons
        code = N[dis] * (G["ncls"] + 1) + G["cid"][M[dis]]
        u, inv = np.unique(code, return_inverse=True)
        mass = np.bincount(inv, w[dis], len(u)) if len(u) else np.zeros(0)
        owner = u // (G["ncls"] + 1) if len(u) else np.zeros(0, np.int64)
        best = np.full(world.n_facts, -np.inf); np.maximum.at(best, owner, mass)
        win_other = best > own_self
        loss = win_other.astype(float)
        if numeric and len(u):
            # value of the winning competitor class per fact
            cls = u % (G["ncls"] + 1)
            o2 = np.lexsort((-mass, owner)); first = np.r_[True, owner[o2][1:] != owner[o2][:-1]]
            wcls = np.full(world.n_facts, -1); wcls[owner[o2][first]] = cls[o2][first]
            cval = np.full(G["ncls"], np.nan); cval[G["cid"]] = val
            v2 = np.where(wcls >= 0, cval[np.maximum(wcls, 0)], np.nan)
            rel = np.minimum(1.0, np.abs(val - v2) / np.maximum(np.abs(v2), 1e-9))
            loss = np.where(win_other & isnum & np.isfinite(rel), rel, loss)
        loss = np.where(R["A"], 0.0, np.where(R["NEG"], 1.0, loss))
        Lp = np.bincount(G["fpage"], loss, world.n_pages)
        if agg == "mean":
            Lp = (Lp + 0.5 * a) / (G["psize"] + a)
        else:
            Lp = Lp + 0.1
        wp_new = np.log(Lp.sum() / np.maximum(Lp, 1e-9))
        wp_new = wp_new / max(wp_new.max(), 1e-9)
        if np.max(np.abs(wp_new - wp)) < 1e-5:
            wp = wp_new
            break
        wp = wp_new
    con = np.bincount(N, w * dis, world.n_facts) + np.bincount(N, K * wn[M] * cons, world.n_facts)
    sup = np.bincount(N, w * cons, world.n_facts)
    pf = (sup + a * prior) / (sup + con + a)
    return pf, wp, dict(sup=sup, con=con)


# ---------------------------------------------------------------- 4./5. Dawid-Skene and LTM on segment items
def page_clusters(world, k=12, seed=0):
    """Pages clustered by public style cues: size, first-person share, exclamation/question share,
    digits per row, mean length, distinct subjects. Deterministic k-means on standardised cues."""
    c = world.__dict__.get("_f1_pclust")
    if c is not None and c[0] == k:
        return c[1]
    import re
    fp = re.compile(r"\b(i|we|my|our|me|us)\b", re.I)
    cues = np.zeros((world.n_pages, 6))
    cnt = np.bincount(world.page, minlength=world.n_pages).astype(float)
    for i, t in enumerate(world.text):
        p = world.page[i]
        cues[p, 1] += bool(fp.search(t)); cues[p, 2] += ("!" in t) or ("?" in t)
        cues[p, 3] += sum(ch.isdigit() for ch in t) / 10.0; cues[p, 4] += len(t) / 100.0
    subj = [set() for _ in range(world.n_pages)]
    for n, f in enumerate(world.flat):
        subj[world.page[world.frow[n]]].add(f.key[0])
    cues[:, 1:5] /= np.maximum(cnt, 1)[:, None]
    cues[:, 0] = np.log1p(cnt); cues[:, 5] = [len(s) for s in subj]
    Z = (cues - cues.mean(0)) / (cues.std(0) + 1e-9)
    rng = np.random.default_rng(seed)
    cen = Z[rng.choice(len(Z), size=min(k, len(Z)), replace=False)]
    for _ in range(50):
        lab = np.argmin(((Z[:, None, :] - cen[None]) ** 2).sum(-1), 1)
        new = np.array([Z[lab == j].mean(0) if (lab == j).any() else cen[j] for j in range(len(cen))])
        if np.allclose(new, cen):
            break
        cen = new
    world.__dict__["_f1_pclust"] = (k, lab)
    return lab


def items(world, seg_w=None, bound="anchor"):
    """Items = (okey, segment): segments split each key's timeline at labelled-true anchor dates
    (bound='anchor'), optionally further cut into seg_w-day pieces; bound='fixed' uses only seg_w bins.
    Returns per fact: item id; item candidates (fact indices used as candidate representatives)."""
    G, R = graph(world), roles(world)
    item = np.zeros(world.n_facts, np.int64)
    nxt = 0
    for g, _, _ in v5_groups(world).values():
        d = G["fdate"][g]
        if bound == "anchor":
            ad = np.unique(d[R["A"][g]])
            seg = np.searchsorted(ad, d, "right")  # 0 before first anchor; s: [ad[s-1], ad[s])
            start = np.where(seg > 0, ad[np.maximum(seg - 1, 0)], d.min()) if len(ad) else np.full(len(g), d.min())
        else:
            seg = np.zeros(len(g), np.int64); start = np.full(len(g), d.min())
        if seg_w:
            seg = seg * 100000 + ((d - start) // seg_w)
        u, inv = np.unique(seg, return_inverse=True)
        item[g] = inv + nxt
        nxt += len(u)
    return item, nxt


def _item_claims(world, item, nitem, R, pages_as):
    """Binary claims (item-candidate, source, y): every claim of an item labels each distinct candidate
    class of the item 1 if consistent with its value, else 0. Candidates = distinct canon classes."""
    G = graph(world)
    cid = G["cid"]
    # candidate = (item, cid) pairs
    code = item * (G["ncls"] + 1) + cid
    cu, cinv = np.unique(code, return_inverse=True)  # cinv: fact -> candidate index
    cand_item = cu // (G["ncls"] + 1)
    rep = np.zeros(len(cu), np.int64); rep[cinv] = np.arange(world.n_facts)  # a representative fact
    # pairs of facts in the same item via the edge list (other pages) plus self
    N, M = G["N"], G["M"]
    same_item = item[N] == item[M]
    cons = G["cons"]
    # claim by fact m about candidate of fact n: y = cons(n, m). Deduplicate per (candidate(n), m).
    cc = cinv[N[same_item]]; mm = M[same_item]; yy = cons[same_item]
    key = cc * world.n_facts + mm
    k_u, k_i = np.unique(key, return_index=True)
    cc, mm, yy = cc[k_i], mm[k_i], yy[k_i]
    # self claims (m labels its own candidate 1)
    cc = np.r_[cc, cinv]; mm = np.r_[mm, np.arange(world.n_facts)]; yy = np.r_[yy, np.ones(world.n_facts, bool)]
    k2 = np.unique(cc * world.n_facts + mm, return_index=True)[1]
    cc, mm, yy = cc[k2], mm[k2], yy[k2]
    # end anchors: a labelled-true fact also annotates the candidates of the item just before it (same key)
    ig = np.full(nitem, -1); ig[item] = G["gid"]
    ec, em_, ey = [], [], []
    by_item = {}
    for c_, it_ in enumerate(cand_item):
        by_item.setdefault(int(it_), []).append(c_)
    for m in np.flatnonzero(R["A"]):
        ip = item[m] - 1
        if ip >= 0 and ig[ip] == G["gid"][m]:
            for c_ in by_item.get(int(ip), ()):
                ec.append(c_); em_.append(m); ey.append(world.flat[rep[c_]].consistent(world.flat[m]))
    endm = np.zeros(len(cc), bool)
    if ec:
        cc = np.r_[cc, ec]; mm = np.r_[mm, em_]; yy = np.r_[yy, ey]; endm = np.r_[endm, np.ones(len(ec), bool)]
    return cc, mm, yy.astype(float), cinv, len(cu), endm


def ds(world, dedup=False, pages_as="page", k=12, seg_w=None, bound="anchor", iters=50, a1=(8.0, 2.0), a0=(8.0, 2.0),
       pi0=0.5, anchor_acc=0.98, anchor_end=0.75, model="ds", burn=20, samples=40, seed=0, **_):
    """Two-coin Dawid-Skene (model='ds', MAP-EM) or LTM (model='ltm', Gibbs over truths and per-source
    sensitivity / specificity) on binary item-candidate truths. Sources = pages or page clusters
    (pages_as='cluster', k clusters). Anchors (labelled true facts) and single-fact false facts are fixed
    annotators of known accuracy for the candidates of their item. P(fact true) = P(its candidate true).
    a1 = Beta prior (pseudo-correct, pseudo-wrong) on sensitivity, a0 on specificity."""
    G, R = graph(world), roles(world)
    item, nitem = items(world, seg_w, bound)
    cc, mm, yy, cinv, ncand, endm = _item_claims(world, item, nitem, R, pages_as)
    src = G["fpage"] if pages_as == "page" else page_clusters(world, k)[G["fpage"]]
    nsrc = int(src.max()) + 1
    known = R["A"][mm] | R["NEG"][mm]
    mf = R["MF"][mm]
    lat = ~(known | mf)
    if dedup:
        lat &= ~G["dupe"][mm]
    s_m = src[mm]
    # fixed annotators: anchors say y (cons) with accuracy anchor_acc; NEG facts: candidate consistent with a
    # known-false value -> evidence false (y flipped), other candidates: no information (dropped)
    la = math.log(anchor_acc / (1 - anchor_acc))
    fixed = np.zeros(ncand)
    le_ = math.log(anchor_end / (1 - anchor_end))
    sa = R["A"][mm]
    fixed += np.bincount(cc[sa], np.where(yy[sa] > 0, 1.0, -1.0) * np.where(endm[sa], le_, la), ncand)
    sn = R["NEG"][mm] & (yy > 0) & ~endm
    fixed -= np.bincount(cc[sn], np.full(sn.sum(), la), ncand)
    sens = np.full(nsrc, a1[0] / sum(a1)); spec = np.full(nsrc, a0[0] / sum(a0))
    pi = pi0
    T = np.full(ncand, 0.5)
    rng = np.random.default_rng(seed)
    acc_T = np.zeros(ncand); nacc = 0
    cl, ml, yl, sl = cc[lat], mm[lat], yy[lat], s_m[lat]
    for it in range(iters if model == "ds" else burn + samples):
        l1 = yl * np.log(sens[sl]) + (1 - yl) * np.log(1 - sens[sl])
        l0 = yl * np.log(1 - spec[sl]) + (1 - yl) * np.log(spec[sl])
        L = math.log(pi / (1 - pi)) + fixed + np.bincount(cl, l1 - l0, ncand)
        Tn = sig(L)
        if model == "ltm":
            Ts = (rng.random(ncand) < Tn).astype(float)
            if it >= burn:
                acc_T += Tn; nacc += 1  # Rao-Blackwellised average of the conditional
        else:
            Ts = Tn
        t = Ts[cl]
        n11 = np.bincount(sl, t * yl, nsrc); n1 = np.bincount(sl, t, nsrc)
        n00 = np.bincount(sl, (1 - t) * (1 - yl), nsrc); n0 = np.bincount(sl, 1 - t, nsrc)
        if model == "ltm":
            sens = rng.beta(n11 + a1[0], n1 - n11 + a1[1]); spec = rng.beta(n00 + a0[0], n0 - n00 + a0[1])
        else:
            sens = (n11 + a1[0]) / (n1 + sum(a1)); spec = (n00 + a0[0]) / (n0 + sum(a0))
        sens = np.clip(sens, 0.01, 0.999); spec = np.clip(spec, 0.01, 0.999)
        pi = float(np.clip(Ts.mean(), 0.05, 0.95))
        if model == "ds" and it and np.max(np.abs(Tn - T)) < 1e-6:
            T = Tn
            break
        T = Tn
    if model == "ltm":
        T = acc_T / max(nacc, 1)
    pf = T[cinv]
    # page reliability: mean over its claims of P(own candidate true)
    rel = np.bincount(G["fpage"], pf, world.n_pages) / np.maximum(G["psize"], 1)
    return pf, rel, dict(sens=sens, spec=spec)


# ---------------------------------------------------------------- 7. dynamic world: lifespan HMM with exactness / freshness
def dynworld(world, dedup=False, slimE=0.0, lam_em=0.0, precise=False, lam=60.0, E0=0.85, F0=0.08, back=0.02, Ea=0.995, iters=4, alpha=3.0, selfx=True, order="median",
             **_):
    """Dong, Berti-Equille, Srivastava (dynamic world), simplified: per typed key a left-to-right HMM over the
    key's distinct values ordered by lifespan (median date of their claims); time steps = distinct claim
    dates; stay probability exp(-gap / lam), otherwise move to a later value (back: probability of moving
    to an earlier one). A page of exactness E states the current value, with freshness lapse F it states an
    earlier (stale) value, otherwise a false one. Anchors emit with Ea; single-fact false facts exclude
    their value. EM re-estimates each page's E and F (Beta-smoothed). selfx: a claim's own emission is
    divided out of its posterior (P from the other claims and the page prior only)."""
    G, R = graph(world), roles(world)
    if slimE:  # SLiMFast-style page prior: logistic claim accuracy from public source features, page mean
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        lab = R["A"] | R["NEG"]
        if lab.sum() >= 10 and R["A"][lab].any() and R["NEG"][lab].any():
            X = StandardScaler().fit_transform(source_feats(world))
            acc = LogisticRegression(C=0.5, max_iter=2000).fit(X[lab], R["A"][lab].astype(int)).predict_proba(X)[:, 1]
            pa = np.bincount(G["fpage"], acc, world.n_pages) / np.maximum(G["psize"], 1)
            E0 = np.clip((1 - slimE) * E0 + slimE * (E0 + (pa - acc[lab].mean())), 0.3, 0.99)
    E = np.full(world.n_pages, E0) if np.isscalar(E0) else E0.copy(); F = np.full(world.n_pages, F0)
    pf = np.full(world.n_facts, 0.5)
    grp = list(v5_groups(world).values())
    lamk = np.full(len(grp), lam)  # per-key expected lifespan; lam_em > 0: re-estimated (prior weight lam_em changes)
    for it in range(iters):
        ex_e = np.zeros(world.n_facts); ex_f = np.zeros(world.n_facts)
        for gi, (g, cons, same) in enumerate(grp):
            d = G["fdate"][g]
            codes = {}
            cc = np.array([codes.setdefault(world.flat[x].canon, len(codes)) for x in g])
            S = len(codes)
            rep = np.zeros(S, np.int64); rep[cc] = np.arange(len(g))
            if precise:  # states = exact values only (eq, full dates); op claims and partial dates are evidence
                fx = [world.flat[g[r_]] for r_ in rep]
                pr_ = np.array([f_.op == "eq" and not (f_.kind == "date" and len(str(f_.raw["value"])) < 10) for f_ in fx])
                if pr_.any() and not pr_.all():
                    keep_s = np.flatnonzero(pr_)
                    remap = np.full(S, -1); remap[keep_s] = np.arange(len(keep_s))
                    rep = rep[keep_s]; S = len(keep_s)
                    cc = remap[cc]  # -1: claim is not itself a state
            if S == 1:
                # one value only: truth is that value unless all claims are known false
                c1 = cons[:, rep[0]]
                p1 = (c1 & ~(R["NEG"][g] & c1).any()).astype(float)
                pf[g] = p1; ex_e[g] = p1
                continue
            Cs = cons[:, rep]  # claim x state consistency (len(g) x S)
            od = ~G["dupe"][g] if dedup else np.ones(len(g), bool)  # copies do not move a value's lifespan
            sel_ = lambda s_: (cc == s_) & od if ((cc == s_) & od).any() else (cc == s_)  # noqa: E731
            med = np.array([np.median(d[sel_(s)]) for s in range(S)]) if order == "median" else \
                np.array([d[sel_(s)].min() for s in range(S)])
            rank = np.argsort(np.argsort(med, kind="stable"), kind="stable")  # state order position
            older = rank[None, :] < rank[:, None]  # older[s, s'] : s' earlier than s
            ud, step = np.unique(d, return_inverse=True)
            T = len(ud)
            pg = G["fpage"][g]
            e, f = E[pg], F[pg]
            # emission of claim x under state s (len(g) x S)
            ncons = np.maximum(S - Cs.sum(1), 1)[:, None]
            stale = (Cs[:, None, :] & older[None, :, :]).any(-1)  # [x, s]: claim x matches a value older than s
            em = np.where(Cs, e[:, None], np.where(stale, f[:, None], (1 - e - f)[:, None] / ncons))
            em = np.maximum(em, 1e-6)
            A_ = R["A"][g]; NG = R["NEG"][g]
            em[A_] = np.where(Cs[A_], Ea, 1 - Ea)
            em[NG] = np.where(Cs[NG], 1 - Ea, 1.0)
            MFm = R["MF"][g]
            if MFm.any():
                q = np.clip(pf[g][MFm], 0.05, 0.95)[:, None]
                em[MFm] = np.where(Cs[MFm], q, 1 - q)
            if dedup:
                em[G["dupe"][g] & R["LAT"][g]] = 1.0
            le = np.log(em)
            LE = np.zeros((T, S)); np.add.at(LE, step, le)
            # transitions per gap
            gaps = np.diff(ud).astype(float)
            fw = rank[None, :] > rank[:, None]
            nf_ = np.maximum(fw.sum(1, keepdims=True), 1); nb_ = np.maximum((~fw).sum(1, keepdims=True) - 1, 1)
            al = np.zeros((T, S)); bt = np.zeros((T, S))
            init = np.where(rank == 0, 0.5, 0.5 / max(S - 1, 1))
            a = np.log(init) + LE[0]
            al[0] = a - np.logaddexp.reduce(a)
            TM = []
            for t in range(1, T):
                stay = math.exp(-gaps[t - 1] / lamk[gi])
                tm = np.where(np.eye(S, dtype=bool), stay, np.where(fw, (1 - stay) * (1 - back) / nf_, (1 - stay) * back / nb_))
                tm = tm / tm.sum(1, keepdims=True)
                ltm = np.log(np.maximum(tm, 1e-12)); TM.append(ltm)
                a = np.logaddexp.reduce(al[t - 1][:, None] + ltm, 0) + LE[t]
                al[t] = a - np.logaddexp.reduce(a)
            for t in range(T - 2, -1, -1):
                b = np.logaddexp.reduce(TM[t] + (LE[t + 1] + bt[t + 1])[None, :], 1)
                bt[t] = b - np.logaddexp.reduce(b)
            post = al + bt
            if lam_em and T > 1:  # expected number of value changes from the pairwise posteriors
                ech = 0.0
                for t in range(1, T):
                    xi = al[t - 1][:, None] + TM[t - 1] + (LE[t] + bt[t])[None, :]
                    xi = np.exp(xi - np.logaddexp.reduce(xi.ravel()))
                    ech += 1.0 - float(np.trace(xi))
                span = float(ud[-1] - ud[0])
                lamk[gi] = (span + lam_em * lam) / (ech + lam_em)
            post = post - np.logaddexp.reduce(post, 1, keepdims=True)
            lp = post[step]  # claim x state
            if selfx:
                lp = lp - le
                lp = lp - np.logaddexp.reduce(lp, 1, keepdims=True)
            P = np.exp(lp)
            pf[g] = (P * Cs).sum(1)
            pfull = np.exp(post[step])
            ex_e[g] = (pfull * Cs).sum(1)
            ex_f[g] = (pfull * (~Cs & stale)).sum(1)
        lat = R["LAT"]
        se = np.bincount(G["fpage"], ex_e * lat, world.n_pages); sf = np.bincount(G["fpage"], ex_f * lat, world.n_pages)
        nl = np.bincount(G["fpage"], lat.astype(float), world.n_pages)
        E = np.clip((se + alpha * E0) / (nl + alpha), 0.3, 0.995)
        F = np.clip((sf + alpha * F0) / (nl + alpha), 0.001, 0.5)
        F = np.minimum(F, 0.99 - E)
    pf = clamp_keep(pf)
    return pf, E, dict(F=F)


def clamp_keep(p):
    return np.clip(p, 1e-6, 1 - 1e-6)


# ---------------------------------------------------------------- 8. SLiMFast / KBT
def source_feats(world):
    """Public per-fact source features: page size, first-person / exclamation / question share of the page,
    row fact count, op != eq, coarse date, kind one-hot, position on page (first, last), text length."""
    import re
    G = graph(world)
    fp = re.compile(r"\b(i|we|my|our|me|us)\b", re.I)
    rowf = np.array([[bool(fp.search(t)), "!" in t, "?" in t, len(t) / 100.0] for t in world.text], float)
    cnt = np.bincount(world.page, minlength=world.n_pages).astype(float)
    pg = np.stack([np.bincount(world.page, rowf[:, j], world.n_pages) / np.maximum(cnt, 1) for j in range(3)], 1)
    first = np.r_[True, world.page[1:] != world.page[:-1]]
    last = np.r_[world.page[1:] != world.page[:-1], True]
    from world import KINDS
    kind = np.array([KINDS.index(f.kind) for f in world.flat])
    X = np.c_[np.log1p(G["psize"][G["fpage"]]), pg[world.page][world.frow], rowf[world.frow],
              G["nf_row"][world.frow], [float(f.op != "eq") for f in world.flat],
              [float(f.kind == "date" and len(str(f.raw["value"])) < 10) for f in world.flat],
              first[world.frow], last[world.frow], np.eye(len(KINDS))[kind]]
    return X


def slimfast(world, em_rounds=3, C=0.5, lam_u=0.3, **p):
    """SLiMFast-style: logistic P(claim correct) from public source features, fit on labelled claims
    (anchors 1, single-fact false 0), then EM: Accu posteriors with the logistic accuracy as each claim's
    own-source prior become soft targets for the unlabelled claims (weight lam_u) and the model is refit."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    R = roles(world)
    X = StandardScaler().fit_transform(source_feats(world))
    lab = R["A"] | R["NEG"]
    yl = R["A"][lab].astype(int)
    if lab.sum() < 10 or len(set(yl)) < 2:
        return accu(world, **p)
    clf = LogisticRegression(C=C, max_iter=2000).fit(X[lab], yl)
    acc = clf.predict_proba(X)[:, 1]
    pf = rel = ex = None
    for r in range(em_rounds):
        pf, rel, ex = accu(world, slim=acc, **p)
        u = R["LAT"]
        Xs = np.r_[X[lab], X[u], X[u]]
        ys = np.r_[yl, np.ones(u.sum(), int), np.zeros(u.sum(), int)]
        ws = np.r_[np.ones(lab.sum()), lam_u * pf[u], lam_u * (1 - pf[u])]
        clf = LogisticRegression(C=C, max_iter=2000).fit(Xs, ys, sample_weight=ws)
        acc = clf.predict_proba(X)[:, 1]
    ex["slim_acc"] = acc
    return pf, rel, ex


# ---------------------------------------------------------------- 9. Sums / Average-Log (Pasternack and Roth)
def sums(world, dedup=False, tau=30.0, beta=1.0, win=None, wa=5.0, wneg=1.0, iters=20, avglog=False, **_):
    """Hubs-and-authorities fact-finders on observations: belief B(n) = own page trust + sum K T(p_m) over
    consistent claims (anchors wa, minus NEG); T(p) = sum (Sums) or log|p| * mean (Average-Log) of its
    claims' beliefs, normalised by the max each iteration. Score = B(n) - contradicting mass, ranked only."""
    G, R = graph(world), roles(world)
    keep, K = edges(G, dict(tau=tau, beta=beta, win=win, dedup=dedup))
    N, M = G["N"][keep], G["M"][keep]
    cons = G["cons"][keep]
    T = np.ones(world.n_pages)
    for it in range(iters):
        wv = np.where(R["A"], wa, np.where(R["NEG"], 0.0, T[G["fpage"]]))
        wn = np.where(R["NEG"], wneg * wa, 0.0)
        w = K * wv[M]
        B = T[G["fpage"]] + np.bincount(N, w * cons, world.n_facts) - np.bincount(N, K * wn[M] * cons, world.n_facts)
        Bn = np.maximum(B, 0) / max(B.max(), 1e-9)
        Bc = np.where(R["A"], 1.0, np.where(R["NEG"], 0.0, Bn))
        s = np.bincount(G["fpage"], Bc, world.n_pages)
        Tn = np.log1p(G["psize"]) * s / np.maximum(G["psize"], 1) if avglog else s
        Tn = Tn / max(Tn.max(), 1e-9)
        if np.max(np.abs(Tn - T)) < 1e-6:
            T = Tn
            break
        T = Tn
    con = np.bincount(N, w * ~cons, world.n_facts)
    score = sig(B - con)
    return score, T, dict(B=B, con=con)


def blend(world, parts=(), how="logit", weights=None, **_):
    """Unsupervised ensemble of TD posteriors: parts = [[method, params], ...]; mean of logits (how='logit') or of
    probabilities ('mean'), optional weights. Page reliability from the first part."""
    outs = [run_method(world, m, **q) for m, q in parts]
    wts = np.ones(len(outs)) if weights is None else np.asarray(weights, float)
    wts = wts / wts.sum()
    if how == "mean":
        pf = sum(w_ * o[0] for w_, o in zip(wts, outs))
    else:
        pf = sig(sum(w_ * logit(o[0]) for w_, o in zip(wts, outs)))
    return pf, outs[0][1], {}


METHODS = dict(blend=blend, vote=vote, truthfinder=truthfinder, accu=accu, crh=crh, ds=ds, ltm=lambda w, **p: ds(w, model="ltm", **p),
               dynworld=dynworld, slimfast=slimfast, sums=sums, avglog=lambda w, **p: sums(w, avglog=True, **p))


def run_method(world, method, **p):
    return METHODS[method](world, **p)
