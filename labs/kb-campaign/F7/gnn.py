"""F7 GNN: hand-written message passing in torch over facts, rows, (okey, value) claims and pages.

Graph: fact nodes; time-aware fact-fact edges to up to K other-row observations of the same observation key
(the DeepSets evidence bank: signed log gap, same value, consistent, same page, source page size, op, fact count,
log ratio, source label one-hot and bracket flags, labels only from visible rows on other pages); every fact
belongs to its row, its page (via the row) and its claim. Each round: messages m = MLP([h_src, edge]) pooled
by mean and attention, plus mean pooling over the row, the page and the claim, residual update. 2 to 3
rounds, then a fact head; row = product (V9 fact targets) or trained end to end on rows (agg='mil').

Own labels never enter: training uses the label trick at page level (each epoch a random share of the
training pages is hidden and becomes the loss set), the early-stopping pages stay hidden, and OOF folds hide
their pages' labels. Isotonic or Platt on OOF row probs, threshold and band on labelled rows.

Params: K, h, drop, wd, lr, epochs, patience, min_epochs, balance, seeds, rounds, q (label-trick target share), agg, calib, select, k.
Plugin: features(world) -> 1 column, GNN fact logit (OOF on labelled rows)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import torch  # noqa: E402

import common as K_  # noqa: E402
from api import Prediction  # noqa: E402
from deepsets import mil_loss, _logit  # noqa: E402


def smean(x, idx, n):
    s = torch.zeros(n, x.shape[1], dtype=x.dtype).index_add(0, idx, x)
    c = torch.zeros(n, dtype=x.dtype).index_add(0, idx, torch.ones(len(idx), dtype=x.dtype))
    return s / c.clamp(min=1).unsqueeze(1)


class GNN(torch.nn.Module):
    def __init__(self, d_e, d_c, h=32, drop=0.2, rounds=2):
        super().__init__()
        L, R = torch.nn.Linear, torch.nn.ReLU
        self.enc = torch.nn.Sequential(L(d_c, h), R())
        self.msg = torch.nn.ModuleList([torch.nn.Sequential(L(h + d_e, h), R(), L(h, h), R()) for _ in range(rounds)])
        self.att = torch.nn.ModuleList([L(h, 1) for _ in range(rounds)])
        self.upd = torch.nn.ModuleList([torch.nn.Sequential(L(6 * h + 1, h), R(), torch.nn.Dropout(drop))
                                        for _ in range(rounds)])
        self.out = K_.mlp(h, h, 1, drop, layers=1)

    def forward(self, E, M, C, g):
        h = self.enc(C)
        Mf = M.unsqueeze(-1).float()
        cnt = Mf.sum(1)
        for msg, att, upd in zip(self.msg, self.att, self.upd):
            m = msg(torch.cat([h[g["src"]], E], -1))
            mean = (m * Mf).sum(1) / cnt.clamp(min=1)
            a = torch.softmax(att(m).squeeze(-1).masked_fill(~M, -1e9), 1) * M.float()
            pa = (a.unsqueeze(-1) * m).sum(1)
            hr = smean(h, g["frow"], g["n_rows"])
            hp = smean(hr, g["rpage"], g["n_pages"])
            hc = smean(h, g["claim"], g["n_claims"])
            h = h + upd(torch.cat([h, mean, pa, hr[g["frow"]], hp[g["fpage"]], hc[g["claim"]], torch.log1p(cnt) / 3], 1))
        return self.out(h).squeeze(-1)


class Variant:
    def __init__(self, K=32, h=32, drop=0.2, wd=1e-3, lr=3e-3, epochs=300, patience=30, seeds=3, rounds=2, q=0.3,
                 agg="product", calib="iso", select="arena", k=4, min_epochs=0, balance=False):
        self.min_epochs, self.balance = min_epochs, balance
        self.K, self.h, self.drop, self.wd, self.lr = K, h, drop, wd, lr
        self.epochs, self.patience, self.seeds, self.rounds, self.q = epochs, patience, seeds, rounds, q
        self.agg, self.calib, self.select, self.k = agg, calib, select, k
        self.chosen = []

    def prepare(self, world):
        B = K_.bank(world, self.K)
        self.world, self.B = world, B
        self.Es, self.M, self.C = torch.from_numpy(B["E"]), torch.from_numpy(B["mask"]), torch.from_numpy(B["C"])
        t = lambda a: torch.from_numpy(np.ascontiguousarray(a, np.int64))  # noqa: E731
        self.g = dict(src=t(np.maximum(B["src"], 0)), frow=t(world.frow), n_rows=world.n, rpage=t(world.page),
                      n_pages=world.n_pages, fpage=t(world.page[world.frow]), claim=t(B["claim"]),
                      n_claims=int(B["claim"].max()) + 1 if world.n_facts else 1)

    def forward(self, net, visible):
        E = torch.cat([self.Es, torch.from_numpy(K_.status(self.world, self.B, visible))], -1)
        return net(E, self.M, self.C, self.g)

    def _loss(self, logit, rows_mask, yf):
        w = self.world
        if self.agg == "mil":
            rows = np.flatnonzero(rows_mask & np.array([len(fs) > 0 for fs in w.facts]))
            facts = np.flatnonzero(np.isin(w.frow, rows))
            loc = torch.from_numpy(np.searchsorted(rows, w.frow[facts]))
            y = torch.from_numpy((w.label[rows] == "true").astype(np.float32))
            return mil_loss(logit[torch.from_numpy(facts)], loc, len(rows), y)
        facts = np.flatnonzero(rows_mask[w.frow] & (yf >= 0))
        return K_.bce(logit[torch.from_numpy(facts)], torch.from_numpy(yf[facts].astype(np.float32)), self.balance)

    def fit_masked(self, train_rows, hidden):
        w = self.world
        yf = K_.fact_targets(w)
        if self.agg == "mil":
            if len(set(w.label[train_rows])) < 2:
                return None
        elif len(set(yf[train_rows[w.frow] & (yf >= 0)])) < 2:
            return None
        base_vis = w.labelled & ~hidden
        tr_pages = np.unique(w.page[train_rows])
        models = []
        for s in range(self.seeds):
            torch.manual_seed(3000 + s)
            rng = np.random.default_rng(50 + s)
            val_pages = tr_pages[K_.inner_split(tr_pages, 13 + s)]
            vrow = np.isin(w.page, val_pages)
            fit_rows = train_rows & ~vrow
            fit_pages = np.unique(w.page[fit_rows])
            vis = base_vis & ~vrow
            net = GNN(self.Es.shape[-1] + 7, self.C.shape[1], self.h, self.drop, self.rounds)

            def loss_fn(n, ep):
                tp = rng.choice(fit_pages, max(1, int(round(self.q * len(fit_pages)))), replace=False)
                trow = np.isin(w.page, tp)
                return self._loss(self.forward(n, vis & ~trow), fit_rows & trow, yf)

            def val_fn(n):
                return self._loss(self.forward(n, vis), train_rows & vrow, yf) if vrow.any() else 0.0
            models.append(K_.train(net, loss_fn, val_fn, self.lr, self.wd, self.epochs, self.patience, self.min_epochs))
        self.chosen.append(("stop", [m.stopped_at for m in models]))
        return models

    def pred_masked(self, models, hidden):
        vis = self.world.labelled & ~hidden
        with torch.no_grad():
            return np.mean([torch.sigmoid(self.forward(m, vis)).numpy() for m in models], 0)

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
        pf = (self.pred_masked(self.models, np.zeros(world.n, bool)) if self.models is not None
              else np.full(world.n_facts, 0.9))
        out, conf = K_.apply_state(K_.row_prob(world, pf), self.state)
        return Prediction(out, conf, pf)


def features(world):
    """Plugin: GNN fact logit (OOF on labelled rows, full model elsewhere), default params."""
    v = Variant()
    v.run(world)
    return _logit(v.pf_tr)[:, None]
