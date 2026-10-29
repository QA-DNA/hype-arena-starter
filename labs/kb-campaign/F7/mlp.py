"""F7 MLP on the V9 fact features: harness V9 pipeline (stage 2 page suspicion, row product, isotonic,
threshold choice, transfer predict, extra_features plugins) with the per-fact LR/HGB replaced by a small
torch MLP: signed-log + one-hot kind + standardize, 2 hidden layers, dropout, AdamW weight decay, early
stopping on an inner page-grouped split, ensemble of seeds (mean probability).

Params: h, drop, wd, lr, epochs, patience, min_epochs, balance, seeds, layers, blend (weight of the V9 LR probability mixed
into the MLP probability, 0 = pure MLP), plus every V9 param (stage2, calib, select,
extra_features, drop_features, selftrain). model='mlp' is fixed."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import torch  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402

import common as K_  # noqa: E402
from variants import v9  # noqa: E402

KIND_COL = 21


class MLPEst:
    def __init__(self, h=32, drop=0.2, wd=1e-3, lr=3e-3, epochs=400, patience=40, seeds=5, layers=2, kind_col=KIND_COL,
                 blend=0.0, min_epochs=0, balance=False, offset_col=None):
        self.blend, self.min_epochs, self.balance, self.offset_col = blend, min_epochs, balance, offset_col
        self.h, self.drop, self.wd, self.lr, self.epochs = h, drop, wd, lr, epochs
        self.patience, self.seeds, self.layers, self.kind_col = patience, seeds, layers, kind_col

    def _x(self, X):
        X = np.asarray(X, float)
        if self.kind_col is not None:
            oh = np.eye(8)[np.clip(X[:, self.kind_col].astype(int), 0, 7)]
            X = np.c_[np.delete(X, self.kind_col, 1), oh]
        return K_.slog(X)

    def fit(self, X, y, groups):
        Z = self._x(X)
        self.mu, self.sd = Z.mean(0), Z.std(0) + 1e-6
        Z = torch.from_numpy(((Z - self.mu) / self.sd).astype(np.float32))
        yt = torch.from_numpy(np.asarray(y, np.float32))
        off = self._off(X)
        self.nets = []
        for s in range(self.seeds):
            torch.manual_seed(2000 + s)
            val = torch.from_numpy(K_.inner_split(np.asarray(groups), 11 + s))
            net = K_.mlp(Z.shape[1], self.h, 1, self.drop, self.layers)
            if off is not None:
                net = Offset(net, off)
            fw = lambda n, sel: n(Z[sel], sel) if off is not None else n(Z[sel])  # noqa: E731
            lf = lambda n, ep, v=val: K_.bce(fw(n, ~v).squeeze(-1), yt[~v], self.balance)  # noqa: E731
            vf = lambda n, v=val: K_.bce(fw(n, v).squeeze(-1), yt[v], self.balance) if v.any() else 0.0  # noqa: E731
            self.nets.append(K_.train(net, lf, vf, self.lr, self.wd, self.epochs, self.patience, self.min_epochs))
        self.lr_ = v9.make("lr").fit(X, y) if self.blend else None
        return self

    def _off(self, X):
        if self.offset_col is None:
            return None
        p = np.clip(np.asarray(X, float)[:, self.offset_col], 1e-4, 1 - 1e-4)
        return torch.from_numpy(np.log(p / (1 - p)).astype(np.float32))[:, None]

    def predict_proba(self, X):
        Z = torch.from_numpy(((self._x(X) - self.mu) / self.sd).astype(np.float32))
        off = self._off(X)
        with torch.no_grad():
            for n in self.nets:
                if off is not None:
                    n.off = off
            p = np.mean([torch.sigmoid(n(Z).squeeze(-1)).numpy() for n in self.nets], 0)
        if self.lr_ is not None:  # blend with the V9 logistic regression on the same columns
            p = (1 - self.blend) * p + self.blend * self.lr_.predict_proba(X)[:, 1]
        return np.c_[1 - p, p]


class Offset(torch.nn.Module):
    """logit = a * offset + net(x): a starts at 1 and net's last layer at 0, so the model starts exactly at the
    offset probability (a strong prior such as a truth-discovery posterior) and weight decay pulls the
    correction back towards it. The offset tensor is bound per call site (train rows, then predict rows)."""

    def __init__(self, net, off):
        super().__init__()
        self.net, self.off, self.a = net, off, torch.nn.Parameter(torch.ones(1))
        torch.nn.init.zeros_(net[-1].weight)
        torch.nn.init.zeros_(net[-1].bias)

    def forward(self, Z, idx=None):
        o = self.off if idx is None else self.off[idx]
        return self.a * o + self.net(Z)


class Variant(v9.Variant):
    def __init__(self, h=32, drop=0.2, wd=1e-3, lr=3e-3, epochs=400, patience=40, seeds=5, layers=2, blend=0.0, min_epochs=0, balance=False,
                 offset_col=None, **kw):
        kw.setdefault("select", "arena")
        super().__init__(model="mlp", **kw)
        kc = KIND_COL if KIND_COL not in self.drop else None
        if kc is not None and self.drop:
            kc -= sum(d < KIND_COL for d in self.drop)
        self.est = dict(h=h, drop=drop, wd=wd, lr=lr, epochs=epochs, patience=patience, seeds=seeds, layers=layers,
                        kind_col=kc, blend=blend, min_epochs=min_epochs, balance=balance,
                        offset_col=offset_col)

    def _fit_oof(self, X, trf, yf, g, k, model):
        oof = np.full(len(yf), np.nan)
        idx = np.where(trf)[0]
        for a, b in GroupKFold(k).split(X[trf], yf[trf], g):
            if len(set(yf[idx[a]])) < 2:
                continue
            oof[idx[b]] = MLPEst(**self.est).fit(X[idx[a]], yf[idx[a]], g[a]).predict_proba(X[idx[b]])[:, 1]
        full = MLPEst(**self.est).fit(X[trf], yf[trf], g)
        return oof, full.predict_proba(X)[:, 1], full

    def run(self, world):
        if K_.one_class(world):  # refit impossible: fall back to the model fitted on practice
            self.chosen.append("fallback-transfer")
            return self.fit(K_.practice_world()).predict(world)
        return _clip(super().run(world))

    def predict(self, world):
        return _clip(super().predict(world))


def _clip(p):
    from api import Prediction
    return Prediction(p.labels, K_.conf_of(np.asarray(p.labels, dtype=object), np.where(p.labels == "true", p.conf, 1 - p.conf)),
                      p.fact_scores)
