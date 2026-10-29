from collections import defaultdict
from datetime import date as D
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_predict
from ..common import key, compat

KINDS = ["quantity", "money", "duration", "name", "percent", "boolean", "date", "version"]
OPS = [None, "eq", "gt", "ge", "lt", "le"]


def days(a, b):
    return (D.fromisoformat(b) - D.fromisoformat(a)).days


class Judge:
    """Algorithm A: leave-one-out bracketing features per fact -> HistGradientBoosting -> Platt calibration on out-of-fold scores."""
    name = "a_bracket_gbm"

    def fit(self, train, unlabelled):
        self.obs = defaultdict(list)  # key -> [(date, value, row id)] of TRUE rows
        for r in train:
            if r["label"] == "true":
                for f in r["facts"]:
                    self.obs[key(f)].append((r["date"], f["value"], r["id"]))
        for v in self.obs.values():
            v.sort(key=lambda o: o[0])
        tr = [r for r in train if r["label"] in ("true", "false")]
        X = np.array([self.row_feats(r) for r in tr])
        y = np.array([r["label"] == "true" for r in tr])
        g = [r["date"] for r in tr]
        mk = lambda: HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=150,
                                                    min_samples_leaf=20, l2_regularization=1.0, random_state=0)
        oof = cross_val_predict(mk(), X, y, groups=g, cv=GroupKFold(5), method="predict_proba")[:, 1]
        z = np.log(np.clip(oof, 1e-4, 1 - 1e-4) / (1 - np.clip(oof, 1e-4, 1 - 1e-4)))
        self.cal = LogisticRegression(C=100).fit(z[:, None], y)
        self.m = mk().fit(X, y)

    def fact_feats(self, r, f):
        v, d = f["value"], r["date"]
        obs = [o for o in self.obs.get(key(f), []) if o[2] != r["id"]]  # leave-one-out
        same = [o for o in obs if o[0] == d]
        b = [o for o in obs if o[0] < d]; a = [o for o in obs if o[0] > d]
        nan = np.nan
        cs = [compat(v, o[1]) for o in same]
        fe = {"n_obs": len(obs), "n_same": len(same), "same_ok": sum(cs), "same_bad": len(cs) - sum(cs)}
        cb = ca = None
        for nm, side in (("b", b[-1] if b else None), ("a", a[0] if a else None)):
            if side:
                c = compat(v, side[1]); dd = abs(days(side[0], d))
                fe[nm + "_ok"] = int(c); fe[nm + "_days"] = dd
                # how many rows on this side agree with the claim
                fe[nm + "_cnt"] = sum(compat(v, o[1]) for o in (b if nm == "b" else a)); fe[nm + "_n"] = len(b if nm == "b" else a)
                # nearest earlier/later: how many distinct consecutive rows share that value
                if nm == "b": cb = side
                else: ca = side
            else:
                fe[nm + "_ok"] = fe[nm + "_days"] = fe[nm + "_cnt"] = fe[nm + "_n"] = nan
        fe["has_b"], fe["has_a"] = int(bool(b)), int(bool(a))
        fe["ba_agree"] = int(compat(cb[1], ca[1])) if cb and ca else nan
        fe["gap"] = days(cb[0], ca[0]) if cb and ca else nan
        # any-time evidence: claim ever true elsewhere
        fe["ever_ok"] = sum(compat(v, o[1]) for o in obs)
        fe["frac_ok"] = fe["ever_ok"] / len(obs) if obs else nan
        # window of +-30 days
        w = [o for o in obs if abs(days(o[0], d)) <= 30]
        fe["w_ok"] = sum(compat(v, o[1]) for o in w); fe["w_bad"] = len(w) - fe["w_ok"]
        for k in KINDS: fe["k_" + k] = int(v["kind"] == k)
        fe["op"] = OPS.index(v.get("op")) if v.get("op") in OPS else -1
        fe["prec"] = len(str(v["value"])) if v["kind"] == "date" else nan
        fe["val"] = v["value"] if isinstance(v["value"], (int, float)) and not isinstance(v["value"], bool) else nan
        return fe

    def row_feats(self, r):
        fs = [self.fact_feats(r, f) for f in r["facts"]]
        if not fs:
            fs = [self.fact_feats(r, {"subject": "", "attribute": "", "value": {"kind": "", "value": ""}})]
        # worst fact: weakest corroboration (bad evidence first, then least support)
        def bad(fe):
            return (fe["same_bad"] > 0, -(fe["b_ok"] if fe["b_ok"] == fe["b_ok"] else 1) - (fe["a_ok"] if fe["a_ok"] == fe["a_ok"] else 1) , -fe["n_obs"])
        w = max(fs, key=bad)
        names = sorted(w)
        row = [w[k] for k in names]
        row += [len(fs), sum(fe["same_bad"] > 0 for fe in fs),
                min(np.nan_to_num(fe["frac_ok"], nan=1.0) for fe in fs),
                sum(np.nan_to_num(fe["b_ok"], nan=1) == 0 or np.nan_to_num(fe["a_ok"], nan=1) == 0 for fe in fs)]
        return row

    def predict(self, rows):
        X = np.array([self.row_feats(r) for r in rows])
        s = np.clip(self.m.predict_proba(X)[:, 1], 1e-4, 1 - 1e-4)
        z = np.log(s / (1 - s))
        return self.cal.predict_proba(z[:, None])[:, 1].tolist()
