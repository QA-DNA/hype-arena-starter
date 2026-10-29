"""F2 feature plugins: func(world) -> (world.n_facts x k) float array, own page always excluded, finite values.
Use as "<path>/F2/f2feat.py:<func>" (for example in v9 extra_features). Label use: only labelled rows (anchors,
and the hazard fit on labelled anchors of the same world).

  hmm      [post, post_other, no_evidence]            HMM forward-backward P(state at the fact's date agrees)
  viterbi  [margin, seg_age, seg_left, gap_prev_cp, gap_next_cp, sup_anchor, sup_vote, sup_vote_dis,
            stale, premature, agrees_map, cp_dist]     MAP timeline (max-marginals + backtrack from the date)
  tecore   [margin]                                    max-weight consistent timeline, anchors hard
  seg      [sweep_post]                                penalised segmentation, share of a penalty sweep agreeing
  stale    [S_back, S_fwd, S_back_anchor_agree, S_back_anchor_dis, stale_anchor, premature_anchor]
           hazard survival S(g) = exp(-lambda_kind g) of the gap to the nearest agreeing evidence
  bracket  15 one-hot columns (before/same/after x Y N y n -)
  all      hmm + viterbi + tecore + seg + stale (23 columns)
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import f2core as K  # noqa: E402

# defaults (selected on P80/P10, see REPORT.md); lam fitted per kind on the world's labelled anchors
HMM_P = dict(eps_a=0.0005, eps_f=0.2, vote_lr=48.0, pi_o=1.0, mono="fit", wm=0.0)  # mono fit: learned per kind
VIT_P = dict(HMM_P)
TEC_P = dict(H=50.0, w_v=4.0, C=2.0, C_o=0.5, mono_pen=2.0)
SEG_P = dict(HMM_P)
SEG_SWEEP = (0.25, 0.5, 1.0, 2.0, 4.0)
L1 = lambda x: math.log1p(abs(x))  # noqa: E731


def _hazard(world, by="kind"):
    c = world.__dict__.setdefault("_f2_hz", {})
    if by not in c:
        c[by] = K.Hazard(by, mono_a=10.0, d0=0.1).fit(world)
    return c[by]


def _kp(p, hz, k):
    """mono='fit' -> the learned downward-switch weight of the key's kind (all ordered kinds)."""
    if p.get("mono") == "fit":
        return dict(p, mono=hz.down.get(k.kind, 1.0), mono_all=True)
    return p


def _cache(world, name, fn):
    c = world.__dict__.setdefault("_f2_feat", {})
    if name not in c:
        c[name] = fn()
    return c[name]


def hmm(world, p=None, lam_by="kind", lam_scale=1.0):
    p = dict(HMM_P, **(p or {}))

    def go():
        hz = _hazard(world, lam_by)
        X = np.zeros((world.n_facts, 3)); X[:, 0] = 0.5; X[:, 2] = 1.0
        for k in K.keys_of(world):
            if len(np.unique(k.page)) < 2:
                continue
            post = K.hmm_post(k, _kp(p, hz, k), hz.lam(k) * lam_scale)
            for b in range(k.n):
                ps = post[int(k.page[b]), int(k.tix[b])]
                X[k.g[b]] = (float(ps @ k.Ag[:, b]), float(ps[-1]), 0.0)
        return X
    return _cache(world, ("hmm", tuple(sorted(p.items())), lam_by, lam_scale), go)


def viterbi(world, p=None, mode="viterbi", lam_by="kind"):
    p = dict(VIT_P if mode == "viterbi" else TEC_P, **(p or {}))

    def go():
        hz = _hazard(world, lam_by)
        X = np.zeros((world.n_facts, 12))
        X[:, 1:5] = 9.0; X[:, 11] = 9.0
        for k in K.keys_of(world):
            if len(np.unique(k.page)) < 2:
                continue
            LL, logstay, logsw, Wlog = K.chain_max_scores(k, _kp(p, hz, k), hz.lam(k), mode)
            logE = K.time_emissions(k, LL)
            predM, bM, bp, fp = K.max_chain(k, logE, logstay, logsw, Wlog)
            T, S = k.T, k.S
            agree = k.Ag > 0.5
            cA = np.zeros((T, S)); cV = np.zeros((T, S)); cVd = np.zeros((T, S))
            isA = k.role == "A"; isV = k.role == "V"
            np.add.at(cA, k.tix[isA], agree[:, isA].T)
            np.add.at(cV, k.tix[isV], agree[:, isV].T)
            np.add.at(cVd, k.tix[isV], (k.Ag[:, isV] < 0.5).T)
            CA, CV, CVd = (np.vstack([np.zeros(S), np.cumsum(c, 0)]) for c in (cA, cV, cVd))
            loc = K.page_local(k, LL)
            own = {}
            for b in range(k.n):
                key = (int(k.page[b]), int(k.tix[b]))
                o = own.setdefault(key, [np.zeros(S), np.zeros(S), np.zeros(S)])
                if isA[b]: o[0] += agree[:, b]
                if isV[b]: o[1] += agree[:, b]; o[2] += k.Ag[:, b] < 0.5
            res = {}
            for (q, t), lc in loc.items():
                mm = predM[t] + logE[t] - lc + bM[t]
                s = int(mm.argmax())
                left = []; cur = s; tl = t; tt = t
                while tt > 0:
                    prev = int(bp[tt, cur])
                    if prev != cur:
                        left.append(prev)
                    elif not left:
                        tl = tt - 1
                    cur = prev; tt -= 1
                right = []; cur = s; tr = t; tt = t
                while tt < T - 1:
                    nxt = int(fp[tt, cur])
                    if nxt != cur:
                        right.append(nxt)
                    elif not right:
                        tr = tt + 1
                    cur = nxt; tt += 1
                o = own[q, t]
                supA = CA[tr + 1, s] - CA[tl, s] - o[0][s]
                supV = CV[tr + 1, s] - CV[tl, s] - o[1][s]
                supVd = CVd[tr + 1, s] - CVd[tl, s] - o[2][s]
                res[q, t] = (mm, s, tl, tr, set(left), set(right), supA, supV, supVd)
            for b in range(k.n):
                mm, s, tl, tr, left, right, supA, supV, supVd = res[int(k.page[b]), int(k.tix[b])]
                ag = k.Ag[:, b]
                a = mm[ag > 0.5].max() if (ag > 0.5).any() else -60.0
                d = mm[ag < 0.5].max() if (ag < 0.5).any() else -60.0
                D = k.date[b]
                agm = float(ag[s] > 0.5)
                gp = L1(D - k.times[tl - 1]) if tl > 0 else 9.0
                gn = L1(k.times[tr + 1] - D) if tr < T - 1 else 9.0
                X[k.g[b]] = (float(np.clip(a - d, -60, 60)), L1(D - k.times[tl]), L1(k.times[tr] - D), gp, gn,
                             L1(supA), L1(supV), L1(supVd),
                             float(not agm and any(ag[x] > 0.5 for x in left)),
                             float(not agm and any(ag[x] > 0.5 for x in right)), agm, min(gp, gn))
        return X
    return _cache(world, (mode, tuple(sorted(p.items())), lam_by), go)


def tecore(world):
    return viterbi(world, mode="tecore")[:, :1]


def seg(world, sweep=SEG_SWEEP):
    def go():
        hz = _hazard(world)
        X = np.full((world.n_facts, 1), 0.5)
        for k in K.keys_of(world):
            if len(np.unique(k.page)) < 2:
                continue
            acc = np.zeros(k.n)
            for c in sweep:
                mm = K.max_marginals(k, dict(_kp(SEG_P, hz, k), c=c), hz.lam(k), "seg")
                for b in range(k.n):
                    v, _ = mm[int(k.page[b]), int(k.tix[b])]
                    acc[b] += float(k.Ag[int(v.argmax()), b] > 0.5)
            X[k.g, 0] = acc / len(sweep)
        return X
    return _cache(world, ("seg", tuple(sweep)), go)


def stale(world):
    def go():
        hz = _hazard(world)
        X = np.zeros((world.n_facts, 6))
        for k in K.keys_of(world):
            lam = hz.lam(k)
            other = k.page[:, None] != k.page[None, :]
            A = k.cons
            isA = k.role == "A"
            for x in range(k.n):
                D = k.date[x]
                o = other[x]
                ag = o & A[x]
                bef = ag & (k.date <= D); aft = ag & (k.date >= D)
                sb = math.exp(-lam * (D - k.date[bef].max())) if bef.any() else 0.0
                sf = math.exp(-lam * (k.date[aft].min() - D)) if aft.any() else 0.0
                ab = bef & isA
                sab = math.exp(-lam * (D - k.date[ab].max())) if ab.any() else 0.0
                db = o & ~A[x] & isA & (k.date <= D)
                sdb = math.exp(-lam * (D - k.date[db].max())) if db.any() else 0.0
                anb = o & isA & (k.date < D); ana = o & isA & (k.date > D)
                st = pm = 0.0
                if anb.any():
                    last = k.date[anb].max()
                    lm = A[x, anb & (k.date == last)].mean() > 0.5
                    st = float(not lm and (A[x] & anb).any())
                if ana.any():
                    nxt = k.date[ana].min()
                    nm = A[x, ana & (k.date == nxt)].mean() > 0.5
                    lastm = (A[x, anb & (k.date == k.date[anb].max())].mean() > 0.5) if anb.any() else False
                    pm = float(nm and anb.any() and not lastm)
                X[k.g[x]] = (sb, sf, sab, sdb, st, pm)
        return X
    return _cache(world, ("stale",), go)


def bracket(world):
    def go():
        cells = K.bracket_cells(world, True, None)
        X = np.zeros((world.n_facts, 15))
        sy = "YNyn-"
        for n, c in enumerate(cells):
            for side in range(3):
                X[n, side * 5 + sy.index(c[side])] = 1.0
        return X
    return _cache(world, ("bracket",), go)


def all(world):  # noqa: A001
    return np.c_[hmm(world), viterbi(world), tecore(world), seg(world), stale(world)]


def core(world):
    """Compact block for other families: hmm post, viterbi margin, cp_dist, seg support (anchor, vote), stale,
    premature, staleness S_back, S_fwd."""
    v = viterbi(world)
    s = stale(world)
    return np.c_[hmm(world)[:, :2], v[:, [0, 11, 5, 6, 8, 9]], s[:, :2]]


BLOCKS = dict(hmm=hmm, viterbi=viterbi, tecore=tecore, seg=seg, stale=stale, bracket=bracket)
