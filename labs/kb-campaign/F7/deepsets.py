"""F7 DeepSets over each fact's evidence set.

Each fact's set = up to K other-row observations of its observation key, nearest in time, each encoded as
(signed log day gap, same day, same value, consistent value, same page, source page size, source op != eq,
source row fact count, numeric log ratio, label one-hot true/false/unsure if the source row is labelled and on
another page). phi(element) -> mean / max / attention pooling -> rho([pools, fact context]) -> fact logit.
Row = product of fact probs (agg='product', V9 fact targets) or the same product trained end to end on row
labels (agg='mil', also uses multi-fact false rows). Page-grouped OOF (hidden pages' labels masked), isotonic
or Platt on OOF row probs, threshold and band chosen on labelled rows.

Params: K, h, drop, wd, lr, epochs, patience, min_epochs, balance (up-weight false facts), seeds (ensemble size), pool ('mean,max,att'), agg, with_v9
(append the 45 V9 features to the fact context), extra_features (plugin specs appended to the context), calib, select, k (OOF folds).
Plugin: features(world) -> 1 column, the logit of the fact score (OOF on labelled rows)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import torch  # noqa: E402

import common as K_  # noqa: E402
from api import Prediction  # noqa: E402


class Net(torch.nn.Module):
    def __init__(self, d_e, d_c, h=32, drop=0.2, pool=("mean", "max", "att")):
        super().__init__()
        self.pool = pool
        self.phi = torch.nn.Sequential(torch.nn.Linear(d_e, h), torch.nn.ReLU(), torch.nn.Linear(h, h), torch.nn.ReLU())
        self.att = torch.nn.Linear(h, 1)
        self.ctx = torch.nn.Sequential(torch.nn.Linear(d_c, h), torch.nn.ReLU())
        self.rho = K_.mlp(len(pool) * h + h + 1, h, 1, drop, layers=1)

    def forward(self, E, M, C):
        h = self.phi(E)
        Mf = M.unsqueeze(-1).float()
        cnt = Mf.sum(1)
        parts = []
        if "mean" in self.pool:
            parts.append((h * Mf).sum(1) / cnt.clamp(min=1))
        if "max" in self.pool:
            hm = h.masked_fill(~M.unsqueeze(-1), -1e9).max(1).values
            parts.append(torch.where(cnt > 0, hm, torch.zeros_like(hm)))
        if "att" in self.pool:
            s = self.att(h).squeeze(-1).masked_fill(~M, -1e9)
            a = torch.softmax(s, 1) * M.float()
            parts.append((a.unsqueeze(-1) * h).sum(1))
        return self.rho(torch.cat(parts + [self.ctx(C), torch.log1p(cnt) / 3], 1)).squeeze(-1)


def mil_loss(logit, frow_local, n_rows, y_row):
    """Row P(true) = prod sigmoid(fact logits); BCE on the row label."""
    lp = torch.nn.functional.logsigmoid(logit)
    lrow = torch.zeros(n_rows, dtype=lp.dtype).index_add(0, frow_local, lp)
    l1m = torch.log(-torch.expm1(lrow.clamp(max=-1e-6)))
    return -(y_row * lrow + (1 - y_row) * l1m).mean()


class Variant:
    def __init__(self, K=64, h=32, drop=0.2, wd=1e-3, lr=3e-3, epochs=400, patience=40, seeds=5,
                 pool="mean,max,att", agg="product", with_v9=False, calib="iso", select="arena", k=4, min_epochs=0,
                 balance=False, extra_features=()):
        self.min_epochs, self.balance, self.extra = min_epochs, balance, list(extra_features)
        self.K, self.h, self.drop, self.wd, self.lr = K, h, drop, wd, lr
        self.epochs, self.patience, self.seeds, self.pool = epochs, patience, seeds, tuple(pool.split(","))
        self.agg, self.with_v9, self.calib, self.select, self.k = agg, with_v9, calib, select, k
        self.scaler = None
        self.chosen = []

    # -------- inputs
    def prepare(self, world):
        B = K_.bank(world, self.K)
        C = B["C"]
        if self.with_v9 or self.extra:
            from api import feature_block
            from variants.v9 import fact_feats
            V = [fact_feats(world)] if self.with_v9 else []
            V = K_.slog(np.concatenate(V + [feature_block(world, s) for s in self.extra], 1))
            if self.scaler is None:
                self.scaler = (V.mean(0), V.std(0) + 1e-6)
            C = np.c_[C, (V - self.scaler[0]) / self.scaler[1]].astype(np.float32)
        self.world, self.B, self.C = world, B, torch.from_numpy(np.ascontiguousarray(C, np.float32))
        self.Es, self.M = torch.from_numpy(B["E"]), torch.from_numpy(B["mask"])

    def inputs(self, visible):
        st = torch.from_numpy(K_.status(self.world, self.B, visible))
        return torch.cat([self.Es, st], -1)

    # -------- fit / predict for one visibility mask
    def fit_masked(self, train_rows, hidden):
        w = self.world
        visible = w.labelled & ~hidden
        E = self.inputs(visible)
        if self.agg == "mil":
            rows = np.flatnonzero(train_rows & np.array([len(fs) > 0 for fs in w.facts]))
            yr = (w.label[rows] == "true").astype(np.float32)
            if len(set(yr)) < 2:
                return None
            facts = np.flatnonzero(np.isin(w.frow, rows))
            loc = np.searchsorted(rows, w.frow[facts])
            item_groups = w.page[rows]
        else:
            yf = K_.fact_targets(w)
            facts = np.flatnonzero(train_rows[w.frow] & (yf >= 0))
            if len(set(yf[facts])) < 2:
                return None
            item_groups = w.page[w.frow[facts]]
        Ef, Mf, Cf = E[facts], self.M[facts], self.C[facts]
        models = []
        for s in range(self.seeds):
            torch.manual_seed(1000 + s)
            val = K_.inner_split(item_groups, 7 + s)
            net = Net(E.shape[-1], self.C.shape[1], self.h, self.drop, self.pool)
            if self.agg == "mil":
                vrow = torch.from_numpy(val)
                fv = vrow[torch.from_numpy(loc)]
                y = torch.from_numpy(yr)
                ft, fvv = torch.from_numpy(np.flatnonzero(~fv.numpy())), torch.from_numpy(np.flatnonzero(fv.numpy()))
                # re-index rows inside each part
                rt, rv = np.flatnonzero(~val), np.flatnonzero(val)
                lt = torch.from_numpy(np.searchsorted(rt, loc[~fv.numpy()]))
                lv = torch.from_numpy(np.searchsorted(rv, loc[fv.numpy()]))

                def loss_fn(n, ep, ft=ft, lt=lt, rt=rt):
                    return mil_loss(n(Ef[ft], Mf[ft], Cf[ft]), lt, len(rt), y[rt])

                def val_fn(n, fvv=fvv, lv=lv, rv=rv):
                    if not len(rv):
                        return 0.0
                    return mil_loss(n(Ef[fvv], Mf[fvv], Cf[fvv]), lv, len(rv), y[rv])
            else:
                y = torch.from_numpy(yf[facts].astype(np.float32))
                vt = torch.from_numpy(val)

                def loss_fn(n, ep, vt=vt):
                    return K_.bce(n(Ef[~vt], Mf[~vt], Cf[~vt]), y[~vt], self.balance)

                def val_fn(n, vt=vt):
                    return K_.bce(n(Ef[vt], Mf[vt], Cf[vt]), y[vt], self.balance) if vt.any() else 0.0
            models.append(K_.train(net, loss_fn, val_fn, self.lr, self.wd, self.epochs, self.patience, self.min_epochs))
        self.chosen.append(("stop", [m.stopped_at for m in models]))
        return models

    def pred_masked(self, models, hidden):
        w = self.world
        E = self.inputs(w.labelled & ~hidden)
        out = np.zeros(w.n_facts)
        with torch.no_grad():
            for a in range(0, w.n_facts, 8192):
                sl = slice(a, a + 8192)
                out[sl] = np.mean([torch.sigmoid(m(E[sl], self.M[sl], self.C[sl])).numpy() for m in models], 0)
        return out

    # -------- harness API
    def run(self, world):
        if K_.one_class(world):  # refit impossible: fall back to the model fitted on practice
            self.chosen.append("fallback-transfer")
            pred = self.fit(K_.practice_world()).predict(world)
            self.pf_tr = pred.fact_scores
            return pred
        self.prepare(world)
        pf_tr, pf, self.models = K_.oof_full(world, self.fit_masked, self.pred_masked, self.k)
        out, conf, self.state, _ = K_.finish(world, pf_tr, pf, self.calib, self.select)
        self.pf_tr = pf_tr
        self.chosen.append(self.state[1:])
        return Prediction(out, conf, pf)

    def fit(self, train_world):
        self.run(train_world)
        return self

    def predict(self, world):
        self.prepare(world)
        if self.models is None:
            pf = np.full(world.n_facts, 0.9)
        else:
            pf = self.pred_masked(self.models, np.zeros(world.n, bool))
        out, conf = K_.apply_state(K_.row_prob(world, pf), self.state)
        return Prediction(out, conf, pf)


def _logit(p):
    p = np.clip(p, 1e-5, 1 - 1e-5)
    return np.log(p / (1 - p))


def features(world):
    """Plugin: DeepSets fact logit (OOF on labelled rows, full model on the rest), default params."""
    v = Variant(seeds=3)
    v.run(world)
    return _logit(v.pf_tr)[:, None]


def features_mil(world):
    v = Variant(seeds=3, agg="mil")
    v.run(world)
    return _logit(v.pf_tr)[:, None]
