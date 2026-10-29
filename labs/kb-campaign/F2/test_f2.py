"""Self-check: the one-pass leave-own-page-out HMM posterior equals a brute-force rerun without that page,
and the max-marginal margin of the chain equals brute-force enumeration on small keys. python -I test_f2.py"""
import copy
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "harness"))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
from world import load_track  # noqa: E402
import f2core as K  # noqa: E402


def drop_page(k, q, D):
    """Key copy without page q's observations plus one emission-free placeholder observation at date D."""
    m = k.page != q
    c = copy.copy(k)
    for a in ("g", "row", "date", "page", "role", "nf", "eq"):
        setattr(c, a, getattr(k, a)[m])
    c.Ag = k.Ag[:, m]
    # placeholder: a vote that agrees with every state (emission constant) at date D
    c.date = np.r_[c.date, D]; c.page = np.r_[c.page, -1]; c.role = np.append(c.role, "V")
    c.nf = np.r_[c.nf, 1]; c.eq = np.r_[c.eq, True]; c.Ag = np.c_[c.Ag, np.ones(k.S)]
    c.n = len(c.date)
    c.times, c.tix = np.unique(c.date, return_inverse=True)
    c.T = len(c.times)
    return c, int(np.searchsorted(c.times, D))


def main():
    w = load_track("P80").folds[0][0]
    p = dict(eps_a=0.01, eps_f=0.2, vote_lr=4.0, pi_o=0.5, mono=0.5, wm=0.5)
    keys = [k for k in K.keys_of(w) if len(np.unique(k.page)) >= 3]
    assert all(len(np.unique(k.date[k.page == q])) == 1 for k in keys for q in np.unique(k.page)), "page with 2 dates"
    nchk = 0
    for k in sorted(keys, key=lambda k: -k.n)[:40]:
        post = K.hmm_post(k, p, 0.006)
        for q in np.unique(k.page):
            t = int(k.tix[np.flatnonzero(k.page == q)[0]])
            c, tc = drop_page(k, q, k.times[t])
            ref = K.hmm_post(c, p, 0.006)[-1, tc]
            assert np.allclose(post[int(q), t], ref, atol=1e-9), (k.okey, q, post[int(q), t], ref)
            nchk += 1
    # max-product vs brute force on small keys (T <= 6, S <= 4): margin of the best path through each state
    nmax = 0
    for k in keys:
        if k.T > 6 or k.S > 4:
            continue
        LL, ls, lw, Wl = K.chain_max_scores(k, p, 0.006, "viterbi")
        mm = K.max_marginals(k, p, 0.006, "viterbi")
        for (q, t), (v, _) in mm.items():
            keep = k.page != q
            E = np.zeros((k.T, k.S)); np.add.at(E, k.tix[keep], LL[:, keep].T)
            best = np.full(k.S, -np.inf)
            for path in itertools.product(range(k.S), repeat=k.T):
                sc = sum(E[i, s] for i, s in enumerate(path))
                for i in range(k.T - 1):
                    sc += ls[i] if path[i] == path[i + 1] else lw[i] + Wl[path[i], path[i + 1]]
                best[path[t]] = max(best[path[t]], sc)
            assert np.allclose(v - v.max(), best - best.max(), atol=1e-6), (k.okey, v, best)
            nmax += 1
    print(f"test_f2 ok: {nchk} leave-page-out posteriors, {nmax} max-marginals checked")


if __name__ == "__main__":
    main()
