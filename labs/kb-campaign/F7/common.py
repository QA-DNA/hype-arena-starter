"""F7 shared pieces: torch setup, training loop with page-grouped early stopping, evidence-set bank,
page-grouped OOF driver, row product, calibration (isotonic / Platt) and threshold selection.
CPU only. Threads: F7_THREADS (default 1, the harness runs one job per core)."""
import copy
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(os.path.dirname(HERE), "harness")
for p in (HERE, HARNESS):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402
import torch  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import f1_score  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402

from world import KINDS, LABELS  # noqa: E402

torch.set_num_threads(int(os.environ.get("F7_THREADS", "1")))
CODE = {"true": 1, "false": 2, "unsure": 3}
OPS = ("eq", "gt", "lt", "ge", "le")


def slog(X):
    X = np.asarray(X, float)
    return np.sign(X) * np.log1p(np.abs(X))


# ---------------------------------------------------------------- training
def inner_split(groups, seed, frac=0.2):
    """Page-grouped validation split for early stopping: returns boolean val mask over the training items."""
    u = np.unique(groups)
    rng = np.random.default_rng(seed)
    val_g = rng.choice(u, max(1, int(round(frac * len(u)))), replace=False) if len(u) > 1 else u[:0]
    return np.isin(groups, val_g)


def train(net, loss_fn, val_fn, lr=3e-3, wd=1e-3, epochs=400, patience=40, min_epochs=0):
    """Full-batch AdamW; keeps the state with the best validation loss (early stopping, never before
    min_epochs: tiny validation sets are noisy)."""
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=wd)
    best, state, bad, ep = math.inf, copy.deepcopy(net.state_dict()), 0, 0
    for ep in range(epochs):
        net.train()
        opt.zero_grad()
        loss = loss_fn(net, ep)
        loss.backward()
        opt.step()
        net.eval()
        with torch.no_grad():
            v = float(val_fn(net))
        if v < best - 1e-5 or ep < min_epochs:
            best, state, bad = min(v, best) if ep >= min_epochs else v, copy.deepcopy(net.state_dict()), 0
        else:
            bad += 1
            if bad >= patience:
                break
    net.load_state_dict(state)
    net.eval()
    net.stopped_at = ep
    return net


def bce(logit, y, balance=False):
    """BCE; balance=True up-weights the negatives to the positive count (calibration fixes the prior later)."""
    w = None
    if balance:
        npos, nneg = float(y.sum()), float((1 - y).sum())
        w = torch.where(y < 0.5, torch.tensor(npos / max(nneg, 1.0)), torch.tensor(1.0))
    return torch.nn.functional.binary_cross_entropy_with_logits(logit, y, weight=w)


def mlp(d_in, h, d_out=1, drop=0.2, layers=2):
    mods, d = [], d_in
    for _ in range(layers):
        mods += [torch.nn.Linear(d, h), torch.nn.ReLU(), torch.nn.Dropout(drop)]
        d = h
    mods.append(torch.nn.Linear(d, d_out))
    return torch.nn.Sequential(*mods)


# ---------------------------------------------------------------- evidence-set bank
def fact_targets(world):
    """V9 targets: 1 = fact of a labelled true row, 0 = fact of a labelled single-fact false row, -1 = none."""
    nf = np.array([len(fs) for fs in world.facts])
    lab_f = world.label[world.frow]
    return np.where(lab_f == "true", 1, np.where((lab_f == "false") & (nf[world.frow] == 1), 0, -1))


def bank(world, K=64):
    """Per fact: up to K other-row observations of the same observation key (okey), nearest in time.
    Static (label-free) element features; label channels are added per call from a visibility mask.
    Returns dict: src (n_facts x K flat index, -1 pad), E (n_facts x K x d_e float32), C (context), claim id."""
    cache = world.__dict__.setdefault("_f7_bank", {})
    if K in cache:
        return cache[K]
    from variants.v5 import groups
    nfct = world.n_facts
    nf = np.array([len(fs) for fs in world.facts])
    psize = np.bincount(world.page, minlength=world.n_pages)
    src = np.full((nfct, K), -1, np.int64)
    E = np.zeros((nfct, K, 9), np.float32)
    nobs = np.zeros(nfct)
    claim = np.zeros(nfct, np.int64)
    ncl = 0
    for g, cons, same in groups(world).values():
        rows = world.frow[g]
        d = world.date[rows].astype(float)
        dt = d[None, :] - d[:, None]  # [a, b] = date_b - date_a
        other = rows[None, :] != rows[:, None]
        labb = world.labelled[rows][None, :]
        kl = min(K // 2, len(g) - 1); ku = min(K - K // 2, len(g) - 1)
        nobs[g] = other.sum(1)
        codes = {}
        for a, n in enumerate(g):
            claim[n] = codes.setdefault(world.flat[n].canon, ncl + len(codes))
        ncl += len(codes)
        if len(g) < 2:
            continue
        # ponytail: half the slots for the nearest labelled sources, half for the nearest unlabelled ones
        kl_ = np.where(other & labb, np.abs(dt), np.inf); ku_ = np.where(other & ~labb, np.abs(dt), np.inf)
        nl = np.argsort(kl_, axis=1, kind="stable")[:, :kl]; nu = np.argsort(ku_, axis=1, kind="stable")[:, :ku]
        nb = np.c_[nl, nu]
        ok = np.c_[np.take_along_axis(kl_, nl, 1), np.take_along_axis(ku_, nu, 1)] < np.inf
        vals = np.array([f.canon if isinstance(f.canon, float) else np.nan for f in (world.flat[n] for n in g)])
        opne = np.array([world.flat[n].op != "eq" for n in g], float)
        for a in range(len(g)):
            b = nb[a][ok[a]]
            m = len(b)
            if not m:
                continue
            gap = dt[a, b]
            va, vb = vals[a], vals[b]
            with np.errstate(divide="ignore", invalid="ignore"):
                lr = np.clip(np.log10((np.abs(va) + 1e-9) / (np.abs(vb) + 1e-9)), -3, 3)
            lr = np.where(np.isnan(lr), 0.0, lr)
            src[g[a], :m] = g[b]
            E[g[a], :m] = np.c_[np.sign(gap) * np.log1p(np.abs(gap)) / 6, gap == 0, same[a, b], cons[a, b],
                                world.page[rows[b]] == world.page[rows[a]], np.log1p(psize[world.page[rows[b]]]) / 3,
                                opne[b], np.log1p(nf[rows[b]] - 1), lr / 3]
    C = np.zeros((nfct, 8 + 5 + 5), np.float32)
    for n, f in enumerate(world.flat):
        i = world.frow[n]
        C[n, KINDS.index(f.kind)] = 1
        C[n, 8 + OPS.index(f.op)] = 1
        C[n, 13:] = (float(f.kind == "date" and len(str(f.raw["value"])) < 10), math.log1p(nf[i] - 1),
                     math.log1p(nobs[n]) / 3, math.log1p(psize[world.page[i]]) / 3, float(nobs[n] == 0))
    out = dict(src=src, E=E, C=C, claim=claim, mask=src >= 0)
    cache[K] = out
    return out


def status(world, B, visible_rows):
    """Label channel per element: one-hot (true, false, unsure) of the source row if it is visible
    (labelled, not hidden) and on another page than the fact; else zeros (= unlabelled evidence)."""
    lab = np.zeros(world.n, np.int64)
    for i in np.flatnonzero(visible_rows):
        lab[i] = CODE.get(world.label[i], 0)
    src = B["src"]
    srow = world.frow[np.maximum(src, 0)]
    code = np.where(B["mask"], lab[srow], 0)
    code[world.page[srow] == world.page[world.frow][:, None]] = 0
    st = np.eye(4, dtype=np.float32)[code][..., 1:]
    # bracket flags: nearest visible-true anchor before / after, nearest observation before / after
    G, M = B["E"][..., 0], B["mask"]
    flags = []
    for sel in (M & (code == 1), M):
        gb = np.where(sel & (G < 0), G, -np.inf); mx = gb.max(1, keepdims=True)
        ga = np.where(sel & (G > 0), G, np.inf); mn = ga.min(1, keepdims=True)
        flags += [(gb == mx) & np.isfinite(mx), (ga == mn) & np.isfinite(mn)]
    return np.concatenate([st, np.stack(flags, -1).astype(np.float32)], -1)


# ---------------------------------------------------------------- OOF driver, product, calibration, decision
def row_prob(world, pf):
    p = np.ones(world.n)
    np.multiply.at(p, world.frow, pf)
    return p


def oof_full(world, fit, pred, k=4):
    """Page-grouped OOF over the labelled rows. fit(train_rows, hidden_rows) -> model or None (one class);
    pred(model, hidden_rows) -> P(fact true) for every fact. Hidden rows' labels never reach the model of
    their fold. Returns (pf_tr: OOF where labelled, full-model elsewhere; pf: full model; full model)."""
    lab = world.labelled & np.array([len(fs) > 0 for fs in world.facts])
    yrow = np.isin(world.label, ["true", "false"])
    rows = np.flatnonzero(lab)
    oof = np.full(world.n_facts, np.nan)
    pages = world.page[rows]
    kk = min(k, len(np.unique(pages)))
    nohide = np.zeros(world.n, bool)
    if kk >= 2:
        for a, b in GroupKFold(kk).split(rows, groups=pages):
            hidden = np.zeros(world.n, bool)
            hidden[world.labelled & np.isin(world.page, np.unique(pages[b]))] = True
            m = fit(world.labelled & yrow & ~hidden, hidden)
            if m is None:
                continue
            p = pred(m, hidden)
            sel = hidden[world.frow]
            oof[sel] = p[sel]
    full = fit(world.labelled & yrow, nohide)
    pf = pred(full, nohide) if full is not None else np.full(world.n_facts, 0.9)
    return np.where(np.isnan(oof), pf, oof), pf, full


def calibrator(kind, x, y):
    if kind == "iso":
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(x, y)
        return iso.predict
    if kind == "platt":
        z = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))[:, None]  # noqa
        lr = LogisticRegression(C=1e4, max_iter=2000).fit(z(x), y)
        return lambda p: lr.predict_proba(z(p))[:, 1]
    return lambda p: p


def decide(pt, t, band):
    out = np.where(pt >= t, "true", "false").astype(object)
    out[np.abs(pt - t) < band] = "unsure"
    return out


def choose(world, prow_tr, select="arena"):
    """(threshold, band) on the labelled rows, v9 grid."""
    tr = world.labelled
    ytr = world.label[tr].astype(str)
    best = None
    for t in (0.3, 0.4, 0.5, 0.6, 0.7):
        for band in (0.0, 0.05, 0.1):
            o = decide(prow_tr, t, band)[tr].astype(str)
            if select == "arena":  # A/score.py: correct unsure +1, wrong unsure 0, wrong true/false -1
                sc = float(np.mean(np.where(o == ytr, 1, np.where(o == "unsure", 0, -1))))
            elif select == "points":  # legacy: every unsure 0
                sc = float(np.mean(np.where(o == "unsure", 0, np.where(o == ytr, 1, -1))))
            else:
                sc = f1_score(ytr, o, labels=list(LABELS), average="macro", zero_division=0)
            if best is None or sc > best[0]:
                best = (sc, t, band)
    return best[1], best[2]


def finish(world, pf_tr, pf, calib="iso", select="arena"):
    """Row = product of fact probs; calibrate on labelled true/false rows (OOF probs); choose threshold.
    Returns labels, conf, (cal, t, band)."""
    prow_tr, prow = row_prob(world, pf_tr), row_prob(world, pf)
    m = world.labelled & np.isin(world.label, ["true", "false"])
    cal = calibrator(calib, prow_tr[m], (world.label[m] == "true").astype(float))
    prow_tr, prow = cal(prow_tr), cal(prow)
    t, band = choose(world, prow_tr, select)
    out = decide(prow, t, band)
    return out, conf_of(out, prow), (cal, t, band), prow


def apply_state(prow, state):
    cal, t, band = state
    p = cal(prow)
    out = decide(p, t, band)
    return out, conf_of(out, p)


def conf_of(out, p):
    """Confidence of the emitted label, never below 0.5 (contract: 0.5..1)."""
    return np.clip(np.where(out == "true", p, 1 - p), 0.5, 1.0)


def one_class(world, min_count=3):
    """True when the world's labelled true/false rows cannot train a classifier (refit fallback trigger)."""
    lab = world.label[world.labelled & np.isin(world.label, ["true", "false"])]
    return min((lab == "true").sum(), (lab == "false").sum()) < min_count


def practice_world():
    from world import practice_full
    return practice_full()[0]
