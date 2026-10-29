"""F3 learned fusion: model x granularity x aggregation x calibrator x abstention policy, on V9 bracket features
(harness variants/v9.fact_feats) plus any feature plugins.

Variant params
  model   lr | hgb | rf | et | knn | mlp | svm | stack | blend         mp: dict of model params (see make_model);
          lr extras: C="auto" (inner page-CV log loss), cscale=g (C scaled by (n_train/1000)**g)
  gran    fact (per-fact model, rows aggregated with agg) | row (direct row model on min/mean/max of fact features)
  agg     prod | min | geo | learned (LR over log prod, log min, mean, max, n_facts on out-of-fold fact probs)
  calib   none | platt | temp | beta | iso | hist | va                   (calib.py, fitted on out-of-fold row scores)
  policy  never05 | never | points | conformal | confpts | vaw | noev | noev+points   alpha: conformal level
  target  tvn (unsure counts as not true in the calibrator) | tvf (unsure rows dropped)
  conf    class (calibrated P of the returned label, floored at 0.5) | max (max(p, 1-p))
One-class worlds (public labels all one class): run() falls back to fit(practice) + predict(world).
  stage2  page-suspicion columns from stage-1 out-of-fold P(false) of the page's other facts (V9)
  onehot  replace the kind index (column 21) by 8 one-hot columns
  extra_features / drop_features: as V9; selftrain/hi/lo: V11 rounds; k: inner page folds
  tmask   transfer only: 0 = fit on the train world as given (fully labelled practice); d > 0 = fit on R=tmask_r
          random page masks of the train world at the TARGET world's labelled share (read at predict time), every
          row of the train world a training example under each mask (its own page never counts as its evidence).
  rmask   refit only: 0 = off; f in (0, 1) = fit on tmask_r copies of the world, each keeping a random share f of
          its labelled pages as anchors (all labelled rows remain training examples): feature-view augmentation.
Transfer tracks: fit(train) keeps the fitted state, predict(world) applies it (the world's labels = evidence only).
"""
import math
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import calib as CAL  # noqa: E402
from api import Prediction, feature_block, run_variant  # noqa: E402
from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402
from sklearn.neighbors import KNeighborsClassifier  # noqa: E402
from sklearn.neural_network import MLPClassifier  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from sklearn.svm import LinearSVC  # noqa: E402
from variants.v9 import fact_feats, page_susp  # noqa: E402

import warnings  # noqa: E402

warnings.filterwarnings("ignore")

DEFAULT_BASE = [["lr", {"C": 0.5}], ["hgb", {}], ["rf", {}], ["et", {}], ["mlp", {}]]


# ------------------------------------------------------------------ models
class Const:
    def __init__(self, p):
        self.p = p

    def predict_proba(self, X):
        return np.c_[np.full(len(X), 1 - self.p), np.full(len(X), self.p)]


class KNN:
    def __init__(self, k, w):
        self.k, self.w = k, w

    def fit(self, X, y):
        self.m = make_pipeline(StandardScaler(), KNeighborsClassifier(min(self.k, len(y)), weights=self.w)).fit(X, y)
        return self

    def predict_proba(self, X):
        return self.m.predict_proba(X)


class Ensemble:
    """stack: meta LR on logits of base models' inner out-of-fold probabilities (GroupKFold by page);
    blend: mean of base probabilities."""

    def __init__(self, kind, base, seed, meta_C=1.0):
        self.kind, self.base, self.seed, self.meta_C = kind, base, seed, meta_C

    def fit(self, X, y, groups=None):
        self.ms = [fit_model(make_model(n, mp, self.seed), X, y) for n, mp in self.base]
        if self.kind == "stack":
            Z = np.zeros((len(y), len(self.base)))
            ng = len(set(groups.tolist())) if groups is not None else 0
            if groups is None or ng < 3:
                groups = np.arange(len(y)) % 3
            for a, b in GroupKFold(3).split(X, y, groups):
                for c, (n, mp) in enumerate(self.base):
                    Z[b, c] = fit_model(make_model(n, mp, self.seed), X[a], y[a]).predict_proba(X[b])[:, 1]
            self.meta = LogisticRegression(C=self.meta_C, max_iter=2000).fit(CAL._logit(Z), y)
        return self

    def predict_proba(self, X):
        P = np.c_[[m.predict_proba(X)[:, 1] for m in self.ms]].T
        if self.kind == "stack":
            return self.meta.predict_proba(CAL._logit(P))
        p = P.mean(1)
        return np.c_[1 - p, p]


def make_model(name, mp=None, seed=0):
    mp = dict(mp or {})
    cw = mp.get("cw")
    if name == "lr":
        pen = mp.get("penalty", "l2")
        return make_pipeline(StandardScaler(), LogisticRegression(
            C=mp.get("C", 0.5), penalty=pen, solver="liblinear" if pen == "l1" else "lbfgs", class_weight=cw,
            max_iter=5000))
    if name == "hgb":
        return HistGradientBoostingClassifier(max_depth=mp.get("depth", 3), learning_rate=mp.get("lr", 0.05),
                                              max_iter=mp.get("iters", 200), l2_regularization=mp.get("l2", 0.0),
                                              min_samples_leaf=mp.get("leaf", 8), class_weight=cw, random_state=seed)
    if name in ("rf", "et"):
        cls = RandomForestClassifier if name == "rf" else ExtraTreesClassifier
        return cls(n_estimators=mp.get("n", 300), min_samples_leaf=mp.get("leaf", 3), max_depth=mp.get("depth"),
                   max_features=mp.get("mf", "sqrt"), class_weight=cw, random_state=seed, n_jobs=1)
    if name == "knn":
        return KNN(mp.get("k", 25), mp.get("w", "distance"))
    if name == "mlp":
        return make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=tuple(mp.get("h", (32,))),
                                                             alpha=mp.get("alpha", 1e-2), max_iter=mp.get("iters", 600),
                                                             random_state=seed))
    if name == "svm":
        return make_pipeline(StandardScaler(), CalibratedClassifierCV(LinearSVC(C=mp.get("C", 0.1), class_weight=cw),
                                                                      method="sigmoid", cv=3))
    if name in ("stack", "blend"):
        return Ensemble(name, mp.get("base", DEFAULT_BASE), seed, mp.get("meta_C", 1.0))
    raise ValueError(name)


def fit_model(m, X, y, groups=None):
    y = np.asarray(y)
    if len(set(y.tolist())) < 2:
        return Const(float(y.mean()) if len(y) else 0.5)
    try:
        return m.fit(X, y, groups) if isinstance(m, Ensemble) else m.fit(X, y)
    except ValueError:  # e.g. CalibratedClassifierCV with < 3 members of a class: fall back to the prior
        return Const(float(y.mean()))


# ------------------------------------------------------------------ helpers
def no_evidence(world):
    """Rows none of whose facts has an observation of its key on another page (label-free)."""
    out = np.ones(world.n, bool)
    for obs in world.obs.values():
        rows = np.array([r for r, _ in obs]); pg = world.page[rows]
        if len(set(pg.tolist())) > 1:
            out[rows] = False
    out[[len(f) == 0 for f in world.facts]] = True
    return out


def row_agg(world, pf, how):
    pf = np.clip(pf, 1e-6, 1 - 1e-6)
    if how == "min":
        out = np.ones(world.n); np.minimum.at(out, world.frow, pf); return out
    lp = np.zeros(world.n); np.add.at(lp, world.frow, np.log(pf))
    if how == "geo":
        nf = np.maximum(np.bincount(world.frow, minlength=world.n), 1)
        return np.exp(lp / nf)
    return np.exp(lp)


def agg_feats(world, pf):
    pf = np.clip(pf, 1e-6, 1 - 1e-6)
    nf = np.bincount(world.frow, minlength=world.n)
    lp = np.zeros(world.n); np.add.at(lp, world.frow, np.log(pf))
    mn = np.ones(world.n); np.minimum.at(mn, world.frow, pf)
    mx = np.zeros(world.n); np.maximum.at(mx, world.frow, pf)
    sm = np.zeros(world.n); np.add.at(sm, world.frow, pf)
    return np.c_[lp, np.log(mn), sm / np.maximum(nf, 1), mx, (nf == 1).astype(float), np.log1p(nf)]


def row_feats(world, X):
    nf = np.bincount(world.frow, minlength=world.n)
    K = X.shape[1]
    mn = np.full((world.n, K), np.inf); mx = np.full((world.n, K), -np.inf); sm = np.zeros((world.n, K))
    np.minimum.at(mn, world.frow, X); np.maximum.at(mx, world.frow, X); np.add.at(sm, world.frow, X)
    z = nf == 0
    mn[z] = 0; mx[z] = 0
    return np.c_[nf, mn, sm / np.maximum(nf, 1)[:, None], mx]


def row_page_susp(world, p):
    """Leave-row-out mean/max of P(false) of the other rows of the page."""
    q = 1 - p
    s = np.bincount(world.page, q, world.n_pages); c = np.bincount(world.page, None, world.n_pages)
    out = np.full((world.n, 2), 0.15)
    o = c[world.page] - 1
    out[o > 0, 0] = ((s[world.page] - q) / np.maximum(o, 1))[o > 0]
    order = np.argsort(world.page, kind="stable")
    bounds = np.r_[0, np.flatnonzero(np.diff(world.page[order])) + 1, world.n]
    for a, b in zip(bounds[:-1], bounds[1:]):
        idx = order[a:b]
        if len(idx) > 1:
            qq = q[idx]; top2 = np.sort(qq)[-2:]
            out[idx, 1] = np.where(qq == top2[1], top2[0], top2[1])  # max over the others
    return out


def onehot_kind(X):
    k = X[:, 21].astype(int)
    return np.c_[np.delete(X, 21, axis=1), np.eye(8)[k]]


# ------------------------------------------------------------------ variant
class Variant:
    def __init__(self, model="lr", mp=None, gran="fact", agg="prod", calib="iso", policy="points", alpha=0.1,
                 target="tvn", conf="class", stage2=True, onehot=False, extra_features=(), drop_features=(),
                 selftrain=0, hi=0.95, lo=0.2, k=5, seed=0, tmask=0, tmask_r=5, agg_C=1.0, rmask=0):
        self.model, self.mp, self.gran, self.agg = model, dict(mp or {}), gran, agg
        self.calib, self.policy, self.alpha, self.target, self.conf = calib, policy, alpha, target, conf
        self.stage2, self.onehot, self.extra, self.drop = stage2, onehot, list(extra_features), list(drop_features)
        self.selftrain, self.hi, self.lo, self.k, self.seed = selftrain, hi, lo, k, seed
        self.tmask, self.tmask_r, self.agg_C, self.rmask = tmask, tmask_r, agg_C, rmask
        self.chosen = []

    # ---- features
    def features(self, world, role=None):
        X = fact_feats(world, role)
        if self.onehot:
            X = onehot_kind(X)
        if self.drop:
            X = np.delete(X, self.drop, axis=1)
        blocks = [feature_block(world, s, role) for s in self.extra]
        return np.c_[(X, *blocks)] if blocks else X

    def _new(self):
        return make_model(self.model, getattr(self, "_mp_eff", None) or self.mp, self.seed)

    def _resolve_mp(self, X, y, g):
        """mp C='auto': inner GroupKFold(4) log loss over a C grid on this training set; mp cscale=gamma:
        C *= (n_train / 1000) ** gamma (regularization tied to label count)."""
        mp = dict(self.mp)
        if mp.get("C") == "auto":
            best = None
            ng = len(set(g.tolist()))
            for Cv in (0.003, 0.01, 0.03, 0.1, 0.3, 1.0):
                oof = np.full(len(y), float(np.mean(y)))
                if ng >= 2:
                    for a, b in GroupKFold(min(4, ng)).split(X, y, g):
                        oof[b] = fit_model(make_model(self.model, dict(mp, C=Cv), self.seed), X[a], y[a]).predict_proba(X[b])[:, 1]
                ll = CAL._nll(oof, y)
                if best is None or ll < best[0] - 1e-12:
                    best = (ll, Cv)
            mp["C"] = best[1]
            self.chosen.append(["C", best[1]])
        if "cscale" in mp:
            mp["C"] = float(mp["C"]) * (len(y) / 1000.0) ** mp.pop("cscale")
        return mp

    # ---- one fitted pass: returns (state, out-of-fold row scores of labelled rows, in-world row scores)
    def _folds(self, world, members):
        """GroupKFold over the pages of `members` (indices into facts or rows)."""
        g = world.page[world.frow[members]] if self._unit == "fact" else world.page[members]
        k = min(self.k, len(set(g.tolist())))
        return list(GroupKFold(k).split(members, groups=g)) if k >= 2 else []

    def _oof(self, world, X, train_mask, y, pred_mask):
        """Out-of-fold probs for pred_mask members (page folds), full model on train_mask, probs for all."""
        oof = np.full(len(X), np.nan)
        members = np.flatnonzero(pred_mask)
        pg0 = world.page[world.frow] if self._unit == "fact" else world.page
        self._mp_eff = self._resolve_mp(X[train_mask], np.asarray(y)[train_mask], pg0[train_mask])
        for a, b in self._folds(world, members):
            tr_pages = set((world.page[world.frow[members[a]]] if self._unit == "fact" else world.page[members[a]]).tolist())
            pg = world.page[world.frow] if self._unit == "fact" else world.page
            tr = train_mask & np.isin(pg, list(tr_pages))
            m = fit_model(self._new(), X[tr], y[tr], pg[tr])
            oof[members[b]] = m.predict_proba(X[members[b]])[:, 1]
        pg = world.page[world.frow] if self._unit == "fact" else world.page
        full = fit_model(self._new(), X[train_mask], y[train_mask], pg[train_mask])
        return oof, full.predict_proba(X)[:, 1], full

    def _targets(self, world):
        if self.gran == "fact":
            nf = np.array([len(fs) for fs in world.facts])
            lab_f = world.label[world.frow]
            yf = np.where(lab_f == "true", 1, np.where((lab_f == "false") & (nf[world.frow] == 1), 0, -1))
            return world.labelled[world.frow] & (yf >= 0), yf, world.labelled[world.frow]
        y = (world.label == "true").astype(int)
        tm = world.labelled & ((world.label != "unsure") if self.target == "tvf" else True)
        return tm, y, world.labelled.copy()

    def _fit_pass(self, world, X):
        """Fit models on `world` (labels from world.label / labels_y3). Returns state and OOF row scores."""
        self._unit = self.gran
        trm, y, predm = self._targets(world)
        if self.gran == "row":
            X = row_feats(world, X)
        oof, pf, m1 = self._oof(world, X, trm, y, predm)
        m2 = None
        if self.stage2:
            p1 = np.where(np.isnan(oof), pf, oof)
            S = page_susp(world, p1) if self.gran == "fact" else row_page_susp(world, p1)
            oof, pf, m2 = self._oof(world, np.c_[X, S], trm, y, predm)
        lab = world.labelled
        if self.gran == "fact":
            pf_tr = np.where(np.isnan(oof), pf, oof)
            aggm = None
            if self.agg == "learned":
                self._unit = "row"
                A_tr = agg_feats(world, pf_tr)
                yr = (world.label == "true").astype(int)
                tm = lab & ((world.label != "unsure") if self.target == "tvf" else True)
                mk = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=self.agg_C, max_iter=2000))  # noqa
                save = self._new
                self._new = mk
                s_oof, _, aggm = self._oof(world, A_tr, tm, yr, lab.copy())
                self._new = save
                s_tr = s_oof
            else:
                s_tr = row_agg(world, pf_tr, self.agg)
        else:
            s_tr = np.where(np.isnan(oof), pf, oof)
            aggm = None
        nof = np.array([len(f) == 0 for f in world.facts])
        base = float(np.mean(world.label[lab] == "true")) if lab.any() else 0.83
        s_tr = np.where(nof, base, s_tr)
        y3 = world.label[lab].astype(object)
        dec = CAL.Decider(self.calib, self.policy, self.alpha, self.k, self.target, self.conf)
        noev = no_evidence(world) if "noev" in self.policy else None
        dec.fit(s_tr[lab], y3, world.page[lab], None if noev is None else noev[lab])
        self.chosen.append([str(sorted(dec.prm.items()))])
        return (m1, m2, aggm, dec, base)

    def _apply_pass(self, world, X, st):
        m1, m2, aggm, dec, base = st
        if self.gran == "row":
            X = row_feats(world, X)
        pf = m1.predict_proba(X)[:, 1]
        if m2 is not None:
            S = page_susp(world, pf) if self.gran == "fact" else row_page_susp(world, pf)
            pf = m2.predict_proba(np.c_[X, S])[:, 1]
        if self.gran == "fact":
            s = aggm.predict_proba(agg_feats(world, pf))[:, 1] if aggm is not None else row_agg(world, pf, self.agg)
        else:
            s = pf
        nof = np.array([len(f) == 0 for f in world.facts])
        s = np.where(nof, base, s)
        noev = no_evidence(world) if "noev" in self.policy else None
        lab, conf, p = dec.decide(s, noev)
        return lab, conf, p, (pf if self.gran == "fact" else None)

    # ---- public API
    def fit(self, train_world):
        self.train_world = train_world
        if not self.tmask:
            self.states = self._fit_all(train_world)
        return self

    def _fit_all(self, world):
        states = []
        X = self.features(world)
        st = self._fit_pass(world, X)
        states.append(st)
        for _ in range(self.selftrain):
            _, _, p, _ = self._apply_pass(world, X, st)
            role = np.full(world.n, "", dtype=object)
            role[p >= self.hi] = "true"; role[p <= self.lo] = "false"
            X = self.features(world, role)
            st = self._fit_pass(world, X)
            states.append(st)
        return states

    def predict(self, world):
        if self.tmask:
            tw = self.train_world
            self.states = self._fit_masked(tw, round(float(world.labelled.mean()) * tw.n_pages))
        X = self.features(world)
        lab, conf, p, pf = self._apply_pass(world, X, self.states[0])
        for st in self.states[1:]:
            role = np.full(world.n, "", dtype=object)
            role[p >= self.hi] = "true"; role[p <= self.lo] = "false"
            X = self.features(world, role)
            lab, conf, p, pf = self._apply_pass(world, X, st)
        return Prediction(lab, conf, pf)

    def _one_class(self, world):
        self._unit = self.gran
        trm, y, _ = self._targets(world)
        return len(set(np.asarray(y)[trm].tolist())) < 2

    def run(self, world):
        if self._one_class(world):  # e.g. a world whose public labels are all true: transfer from practice
            from world import practice_full
            self.chosen.append(["one-class world: fitted on practice"])
            return self.fit(practice_full()[0]).predict(world)
        if self.rmask:
            self.states = self._fit_masked(world, round(self.rmask * len(set(world.page[world.labelled].tolist()))))
        else:
            self.states = self._fit_all(world)
        X = self.features(world)
        lab, conf, p, pf = self._apply_pass(world, X, self.states[0])
        for st in self.states[1:]:
            role = np.full(world.n, "", dtype=object)
            role[p >= self.hi] = "true"; role[p <= self.lo] = "false"
            X = self.features(world, role)
            lab, conf, p, pf = self._apply_pass(world, X, st)
        return Prediction(lab, conf, pf)

    # ---- masked copies: transfer at the target density (tmask) or refit augmentation (rmask)
    def _fit_masked(self, train, n_keep):
        """Stack R copies of `train`; copy r keeps only n_keep randomly drawn labelled pages as anchors, so features
        are computed at that anchor density; every row with a label becomes a training example in every copy
        (its own page never counts as its evidence). Copies keep the original page id: GroupKFold by page keeps
        every copy of a page in one fold. Stage 2 (page suspicion) is computed per copy."""
        if self.gran != "fact" or self.selftrain or self.agg == "learned":
            raise ValueError("tmask/rmask support gran=fact, selftrain=0, agg!=learned")
        gold = train.label.copy()
        R = self.tmask_r
        labpages = sorted(set(train.page[train.labelled].tolist()))
        nf = np.array([len(fs) for fs in train.facts])
        Ws, Xs, ys = [], [], []
        for r in range(R):
            rng = random.Random(1000 + r)
            keep = rng.sample(labpages, max(1, min(len(labpages), n_keep)))
            w = train.with_labels(np.isin(train.page, keep) & train.labelled, gold)
            Ws.append(w); Xs.append(self.features(w))
            lab_f = gold[w.frow]
            ys.append(np.where(lab_f == "true", 1, np.where((lab_f == "false") & (nf[w.frow] == 1), 0, -1)))
        y = np.concatenate(ys); pg = np.tile(train.page[train.frow], R); trm = y >= 0
        k = min(self.k, len(labpages))
        nfct = train.n_facts

        def oof_fit(X):
            self._mp_eff = self._resolve_mp(X[trm], y[trm], pg[trm])
            oof = np.full(len(y), np.nan)
            for a, b in GroupKFold(k).split(X, groups=pg):
                a = a[trm[a]]
                oof[b] = fit_model(self._new(), X[a], y[a], pg[a]).predict_proba(X[b])[:, 1]
            m = fit_model(self._new(), X[trm], y[trm], pg[trm])
            return oof, m
        X = np.vstack(Xs)
        oof, m1 = oof_fit(X)
        m2 = None
        if self.stage2:
            S = np.vstack([page_susp(Ws[r], oof[r * nfct:(r + 1) * nfct]) for r in range(R)])
            oof, m2 = oof_fit(np.c_[X, S])
        s = np.concatenate([row_agg(train, oof[r * nfct:(r + 1) * nfct], self.agg) for r in range(R)])
        has = np.tile(train.labelled, R)
        base = float(np.mean(gold[train.labelled] == "true"))
        s = np.where(np.tile(nf == 0, R), base, s)
        dec = CAL.Decider(self.calib, self.policy, self.alpha, self.k, self.target, self.conf)
        dec.fit(s[has], np.tile(gold, R)[has].astype(object), np.tile(train.page, R)[has], None)
        self.chosen.append([str(sorted(dec.prm.items())), n_keep])
        return [(m1, m2, None, dec, base)]


class Wrap:
    """Wrap any harness variant with an F3 calibrator + abstention policy. Out-of-fold row scores of the labelled
    rows come from re-running the inner variant on k worlds, each hiding one page fold of the labelled rows.
    Row score = P(true) implied by the inner prediction (conf if true, 1 - conf if false, 0.5 if unsure)."""

    def __init__(self, inner="v9", inner_params=None, calib="platt", policy="points", alpha=0.1, k=5,
                 target="tvn", conf="class"):
        self.inner, self.ip = inner, dict(inner_params or {})
        self.dec = CAL.Decider(calib, policy, alpha, k, target, conf)
        self.k, self.chosen = k, []

    def _cls(self):
        from api import resolve
        return resolve(self.inner, "Variant")[0]

    @staticmethod
    def _score(pred):
        lab = np.asarray(pred[0], dtype=object); c = np.asarray(pred[1], float)
        return np.where(lab == "true", c, np.where(lab == "false", 1 - c, 0.5))

    def _oof(self, world):
        cls = self._cls(); lab = np.flatnonzero(world.labelled)
        s = np.full(world.n, np.nan)
        g = world.page[lab]
        for _, b in GroupKFold(min(self.k, len(set(g.tolist())))).split(lab, groups=g):
            m = world.labelled.copy(); m[lab[b]] = False
            w = world.with_labels(m, world.label)
            s[lab[b]] = self._score(run_variant(cls(**self.ip), w))[lab[b]]
        noev = no_evidence(world) if "noev" in self.dec.policy else None
        self.dec.fit(s[lab], world.label[lab].astype(object), g, None if noev is None else noev[lab])
        self.chosen.append([str(sorted(self.dec.prm.items()))])

    def fit(self, train_world):
        self.train = train_world
        self._oof(train_world)
        return self

    def predict(self, world):
        v = self._cls()(**self.ip)
        p = run_variant(v, world, self.train)
        noev = no_evidence(world) if "noev" in self.dec.policy else None
        lab, conf, _ = self.dec.decide(self._score(p), noev)
        return Prediction(lab, conf, None)

    def run(self, world):
        lab = world.label[world.labelled]
        if len(set(lab.tolist()) & {"true", "false"}) < 2:  # one-class world: transfer from practice
            from world import practice_full
            self.chosen.append(["one-class world: fitted on practice"])
            return self.fit(practice_full()[0]).predict(world)
        self._oof(world)
        v = self._cls()(**self.ip)
        p = run_variant(v, world)
        noev = no_evidence(world) if "noev" in self.dec.policy else None
        lab, conf, _ = self.dec.decide(self._score(p), noev)
        return Prediction(lab, conf, None)
