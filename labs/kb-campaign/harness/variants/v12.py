"""V12 feature plugins (port of labs/kb-experiments/v12.py extra_feats): count independent evidence, not rows.
pages(world, role) -> 5 columns: distinct other pages among anchor-consistent, anchor-inconsistent,
vote-consistent, vote-inconsistent, single-fact negative-consistent observations.
mmr(world, role) -> 4 columns: MMR-discounted masses (weight exp(-|dt|/30), TF-IDF char 3-5 similarity, same
page = 1) of the anchor-consistent, anchor-inconsistent, vote-consistent, vote-inconsistent pools.
Best published configuration (V12mmr-replace): v9 with selftrain=1, drop_features=[11, 12, 13, 14],
extra_features=["v12:mmr"]. Deviation: ties in relevance are broken by date-sorted position (exp.py used row order)."""
import math

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from variants.v5 import groups
from variants.v9 import evidence_role

_TFIDF = {}


def tfidf(world):  # label-free, cached per world content
    if world.static_key not in _TFIDF:
        _TFIDF[world.static_key] = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform(world.text)
    return _TFIDF[world.static_key]


def mmr_mass(items, G):
    """Greedy in relevance order: weight = rel * (1 - max similarity to the items already counted).
    Vectorised: row k of the sorted similarity block, max over the columns before k (empty -> 0)."""
    if not items:
        return 0.0
    items = sorted(items, key=lambda t: (-t[0], t[1]))
    rel = np.array([t[0] for t in items]); pos = np.array([t[1] for t in items])
    sub = np.where(np.tri(len(pos), k=-1, dtype=bool), G[np.ix_(pos, pos)], 0.0)  # G >= 0, so 0 = "nothing done"
    return float(np.dot(rel, 1.0 - sub.max(1)))


def _mmr_ref(items, G):  # the original loop, kept for the self-check
    items = sorted(items, key=lambda t: (-t[0], t[1])); tot = 0.0; done = []
    for rel, p in items:
        tot += rel * (1.0 - (max(G[p, q] for q in done) if done else 0.0)); done.append(p)
    return tot


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    for _ in range(200):
        m = int(rng.integers(1, 30)); A = rng.random((m, m)); G = np.clip((A + A.T) / 2, 0, 1)
        it = [(float(rng.random()), int(q)) for q in rng.choice(m, int(rng.integers(0, m + 1)), replace=False)]
        assert abs(mmr_mass(it, G) - _mmr_ref(it, G)) < 1e-12
    print("mmr selfcheck ok")


def _extra(world, role):
    T = tfidf(world)
    role = evidence_role(world, role)
    nf = np.array([len(fs) for fs in world.facts])
    out = np.zeros((world.n_facts, 9))
    for g, cons, _ in groups(world).values():
        rows = world.frow[g]; pages = world.page[rows]; dates = world.date[rows]
        G = np.clip((T[rows] @ T[rows].T).toarray(), 0.0, 1.0)
        G[pages[:, None] == pages[None, :]] = 1.0
        for a, n in enumerate(g):
            pool = {k: [] for k in ("ac", "ai", "vc", "vi", "nc")}
            for b in np.flatnonzero(pages != pages[a]):
                k = rows[b]; c = bool(cons[a, b]); e = (math.exp(-abs(int(dates[b] - dates[a])) / 30), b, pages[b])
                if role[k] == "true":
                    pool["ac" if c else "ai"].append(e)
                elif role[k] == "false":
                    if c and nf[k] == 1:
                        pool["nc"].append(e)
                else:
                    pool["vc" if c else "vi"].append(e)
            out[n] = ([len({e[2] for e in pool[q]}) for q in ("ac", "ai", "vc", "vi", "nc")]
                      + [mmr_mass([e[:2] for e in pool[q]], G) for q in ("ac", "ai", "vc", "vi")])
    return out


def pages(world, role=None):
    return _extra(world, role)[:, :5]


def mmr(world, role=None):
    return _extra(world, role)[:, 5:]


def features(world, role=None):
    return _extra(world, role)
