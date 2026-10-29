"""F1 feature plugins (world -> n_facts x k), for V9-style learned models and the combination phase.
Labelled facts get their values from an inner run with their page fold's labels hidden (GroupKFold 5 by
page), so a labelled fact never sees its own label (an anchor would otherwise be clamped to 1 or 0);
unlabelled facts get the full run. Same columns on every world. Cached per (world, labelled mask).

  plugins:td_post       [dynworld posterior, accu posterior]           TD posterior of the fact at its date
  plugins:page_rel      [accu page accuracy (row left out), dynworld page exactness, log page size]
  plugins:indep_support [log1p distinct supporting pages, log1p distinct contradicting pages (30 days),
                         log1p copy-adjusted support, log1p copy-adjusted contradiction]
  plugins:copy_margin   [copy-adjusted kernel vote margin, unadjusted margin, mean independence of supporters]
  plugins:td_all        all of the above plus truthfinder conf, crh score, ds posterior, ltm posterior
"""
import hashlib
import os
import sys

import numpy as np
from sklearn.model_selection import GroupKFold

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import td  # noqa: E402

# best stage-1/2 settings on P80+P10 (see REPORT)
DYN = dict(lam=120.0, F0=0.03, back=0.005, E0=0.85, Ea=0.999)
ACCU = dict(tau=30.0, alpha=10.0, nfalse=30, selfw=1.0)
TF = dict(tau=15.0, gamma=1.0, rho=1.0, sup="overlap", t0=0.9)
CRH = dict(tau=15.0, wa=2.0, agg="mean", numeric=False)
DS = dict(bound="fixed", seg_w=15)


def _oof(world, fn, inner=5):
    """fn(world) -> (n_facts x k). Labelled facts from hidden-fold runs, the rest from the full run."""
    td.graph(world)
    X = np.asarray(fn(world), float)
    lab = world.labelled
    pages = np.unique(world.page[lab])
    k = min(inner, len(pages))
    if k >= 2:
        for _, te in GroupKFold(k).split(pages, groups=pages):
            hide = np.isin(world.page, pages[te]) & lab
            Xf = np.asarray(fn(world.with_labels(lab & ~hide, world.label)), float)
            fh = hide[world.frow]
            X[fh] = Xf[fh]
    return X


def _cached(world, name, fn):
    h = hashlib.sha1(np.packbits(world.labelled).tobytes()).hexdigest()
    c = world.__dict__.setdefault("_f1_plug", {})
    if (name, h) not in c:
        c[name, h] = _oof(world, fn)
    return c[name, h]


def _core(w):
    G = td.graph(w)
    pd, E, _ = td.dynworld(w, **DYN)
    pa, A, ex = td.accu(w, copy=True, **ACCU)
    R = td.roles(w)
    Aloo = td.page_loo(w, G, td.clamp(pa, R, pa), 3.0, 0.8)
    keep, K = td.edges(G, dict(win=30))
    N, M = G["N"][keep], G["M"][keep]
    cons = G["cons"][keep]
    ind = ex["ind"]
    pm = G["fpage"][M]

    def distinct(mask):
        u = np.unique(N[mask] * (w.n_pages + 1) + pm[mask])
        return np.bincount(u // (w.n_pages + 1), None, w.n_facts)
    sup_p, con_p = distinct(cons), distinct(~cons)
    sup_i = np.bincount(N, ind[M] * cons, w.n_facts); con_i = np.bincount(N, ind[M] * ~cons, w.n_facts)
    keep2, K2 = td.edges(G, dict(tau=30.0))
    N2, M2 = G["N"][keep2], G["M"][keep2]
    c2 = G["cons"][keep2]
    s_a = np.bincount(N2, K2 * ind[M2] * c2, w.n_facts); c_a = np.bincount(N2, K2 * ind[M2] * ~c2, w.n_facts)
    s_r = np.bincount(N2, K2 * c2, w.n_facts); c_r = np.bincount(N2, K2 * ~c2, w.n_facts)
    marg = lambda s, c: np.divide(s - c, s + c, out=np.zeros_like(s), where=(s + c) > 0)  # noqa: E731
    nsup = np.bincount(N2, c2.astype(float), w.n_facts)
    mind = np.divide(np.bincount(N2, ind[M2] * c2, w.n_facts), nsup, out=np.ones(w.n_facts), where=nsup > 0)
    return np.c_[pd, pa, Aloo, E[G["fpage"]], np.log1p(G["psize"][G["fpage"]]),
                 np.log1p(sup_p), np.log1p(con_p), np.log1p(sup_i), np.log1p(con_i),
                 marg(s_a, c_a), marg(s_r, c_r), mind]


def _extra(w):
    tf, _, _ = td.truthfinder(w, **TF)
    cr, _, _ = td.crh(w, **CRH)
    d1, _, _ = td.ds(w, **DS)
    d2, _, _ = td.ds(w, model="ltm", **DS)
    return np.c_[tf, cr, d1, d2]


def td_post(world):
    return _cached(world, "core", _core)[:, 0:2]


def page_rel(world):
    return _cached(world, "core", _core)[:, 2:5]


def indep_support(world):
    return _cached(world, "core", _core)[:, 5:9]


def copy_margin(world):
    return _cached(world, "core", _core)[:, 9:12]


def td_all(world):
    return np.c_[_cached(world, "core", _core), _cached(world, "extra", _extra)]


# discovery table for other families and the combination phase (refs resolve from the $KBC root, as run.py does)
PLUGINS = {
    "td_post": {"ref": "F1/plugins.py:td_post", "k": 2,
                "desc": "TD posterior P(fact true at its date): [dynworld lifespan HMM, Accu-copy temporal]"},
    "page_rel": {"ref": "F1/plugins.py:page_rel", "k": 3,
                 "desc": "row page reliability: [Accu page accuracy without the row, dynworld page exactness, log1p page size]"},
    "indep_support": {"ref": "F1/plugins.py:indep_support", "k": 4,
                      "desc": "log1p [distinct supporting pages, distinct contradicting pages (30 d), copy-adjusted support, copy-adjusted contradiction]"},
    "copy_margin": {"ref": "F1/plugins.py:copy_margin", "k": 3,
                    "desc": "[copy-adjusted kernel vote margin (tau 30), unadjusted margin, mean independence of supporters]"},
    "td_all": {"ref": "F1/plugins.py:td_all", "k": 16,
               "desc": "the 12 columns above plus [truthfinder conf, crh support share, Dawid-Skene posterior, LTM posterior]"},
}
