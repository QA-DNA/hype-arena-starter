"""exp.py rule family (V3/V5/V6neg), default = V5: kernel-weighted support vs contradiction,
interval-overlap consistency, own page excluded. Vectorised per observation key (exp.py okey)."""
import numpy as np

from api import Base

BASE = dict(wu=0.3, tau=30.0, win="sym", beta=0.5, interval=True, neg=None)


def roles(world, p):
    """exp.roles(): per flat fact (weight, sign). Labelled true -> (1,+1); labelled false -> (neg,-1) if
    single-fact and neg set, else ignored; labelled unsure and unlabelled -> (wu,+1)."""
    w = np.full(world.n_facts, p["wu"])
    sg = np.ones(world.n_facts, np.int64)
    nf = np.array([len(fs) for fs in world.facts])
    for n, i in enumerate(world.frow):
        if world.labelled[i]:
            if world.label[i] == "true":
                w[n] = 1.0
            elif world.label[i] == "false":
                if p.get("neg") and nf[i] == 1:
                    w[n], sg[n] = p["neg"], -1
                else:
                    w[n], sg[n] = 0.0, 0
    return w, sg


def groups(world):
    """okey -> (flat indices, consistency matrix C[a, b] = facts[a].consistent(facts[b]), exact-equality matrix)."""
    cache = world.__dict__.setdefault("_v5_groups", {})
    if cache:
        return cache
    for okey, obs in world.obs_typed.items():
        g = np.array([world.fstart[i] + j for i, j in obs], np.int64)
        fs = [world.flat[n] for n in g]
        codes = {}
        cc = np.array([codes.setdefault(f.canon, len(codes)) for f in fs])
        same = cc[:, None] == cc[None, :]
        if fs[0].lo is None:
            cons = same
        else:
            lo = np.array([f.lo for f in fs], float)
            hi = np.array([f.hi for f in fs], float)
            tol = 1e-9 * np.maximum(1.0, np.where(np.isinf(lo), 1.0, np.abs(lo)))
            with np.errstate(invalid="ignore"):
                cons = np.maximum(lo[:, None], lo[None, :]) <= np.minimum(hi[:, None], hi[None, :]) + tol[:, None]
        cache[okey] = (g, cons, same)
    return cache


def kern(dtd, p, win):
    """dtd = D - d_obs (days); exp.kern vectorised."""
    tau = p["tau"]
    if tau == float("inf"):
        return np.ones_like(dtd, float)
    back = np.exp(-np.abs(dtd) / tau)
    return np.where(dtd >= 0, back, 0.0 if win == "fwd" else p.get("beta", 1.0) * back)


def fact_scores(world, p, w=None, sg=None):
    """-> sp, sm per flat fact (exp.fact_scores with rel=None)."""
    if w is None:
        w, sg = roles(world, p)
    sp = np.zeros(world.n_facts)
    sm = np.zeros(world.n_facts)
    pg = world.page[world.frow]
    dt = world.date[world.frow].astype(float)
    for g, cons, same in groups(world).values():
        C = cons if p.get("interval") else same
        other = pg[g][:, None] != pg[g][None, :]
        dtd = dt[g][:, None] - dt[g][None, :]
        wg, sgg = w[g][None, :], sg[g][None, :]
        for win in (p["win"], "sym") if p["win"] == "fwd" else (p["win"],):
            K = kern(dtd, p, win) * other * wg
            a = (K * (sgg > 0) * C).sum(1)
            b = (K * (sgg > 0) * ~C).sum(1) + (K * (sgg < 0) * C).sum(1)
            if win == p["win"]:
                sp[g], sm[g] = a, b
            else:  # fwd fallback: nothing before D -> use later observations
                fb = (sp[g] + sm[g] == 0) & other.any(1)
                sp[g] = np.where(fb, a, sp[g])
                sm[g] = np.where(fb, b, sm[g])
    return sp, sm


class Variant(Base):
    def __init__(self, **params):
        self.p = dict(BASE, **params)

    def predict(self, world):  # parameter-free: evidence = the world's own labelled rows
        sp, sm = fact_scores(world, self.p)
        tot = sp + sm
        marg = np.divide(sp - sm, tot, out=np.zeros_like(tot), where=tot > 0)
        labels = np.full(world.n, "unsure", dtype=object)
        conf = np.full(world.n, np.nan)
        for i, fs in enumerate(world.facts):
            if not fs:
                continue  # no facts: unsure (exp.py would crash)
            s = slice(world.fstart[i], world.fstart[i] + len(fs))
            dec = np.where(tot[s] == 0, "U", np.where(sm[s] > sp[s], "F", "T"))
            labels[i] = "false" if "F" in dec else "unsure" if "U" in dec else "true"
            conf[i] = 0.5 + 0.5 * abs(marg[s].min())
        return labels, conf, marg
