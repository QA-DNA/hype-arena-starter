import math
from collections import defaultdict
from datetime import date
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import cross_val_predict
from ..common import key, compat

KINDS = ["quantity", "money", "duration", "name", "percent", "boolean", "date", "version"]
TAU = 30.0


def ordv(s):
    return date.fromisoformat(s[:10]).toordinal()


class Judge:
    """Truth discovery by evidence aggregation around each fact's (hidden, piecewise-constant) timeline.
    Per (subject, attribute): labelled-true rows pin the value, labelled-false rows exclude it, and ALL rows
    (labelled or not, labels ignored) cast time-kernel votes. A GBM learns how reliable each kind of vote is
    (reliability learned, not fixed), then isotonic calibration on out-of-fold scores.
    Leakage: training features drop the row itself and, in date mode, every row of its page date."""
    name = "b_truth"

    def fit(self, train, unlabelled):
        self.obs = defaultdict(list)  # key -> (date_ord, value, label, idx, date)
        for r in list(train) + list(unlabelled):
            lab = r["label"] if r["label"] in ("true", "false") else None
            for f in r["facts"]:
                self.obs[key(f)].append((ordv(r["date"]), f["value"], lab, r["idx"], r["date"]))
        tr_dates = {r["date"] for r in train}
        self.date_mode = not any(r["date"] in tr_dates for r in unlabelled)
        X, y = [], []
        for r in train:
            if r["label"] not in ("true", "false"):
                continue
            for f in r["facts"]:
                X.append(self.feat(r, f, True)); y.append(r["label"] == "true")
        X, y = np.array(X), np.array(y)
        self.m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=20, l2_regularization=1.0)
        oof = cross_val_predict(self.m, X, y, cv=5, method="predict_proba")[:, 1]
        self.iso = IsotonicRegression(y_min=0.01, y_max=0.995, out_of_bounds="clip").fit(oof, y)
        self.m.fit(X, y)

    def feat(self, r, f, training):
        d, v, k = ordv(r["date"]), f["value"], key(f)
        excl_same = self.date_mode  # mimic unseen pages
        T, F, A, TV = [], [], [], []
        for (od, ov, lab, idx, ds) in self.obs.get(k, []):
            if idx == r["idx"] or (excl_same and ds == r["date"]):
                continue
            c = compat(v, ov)
            A.append((od - d, c))
            if lab == "true": T.append((od - d, c)); TV.append((od - d, ov))
            elif lab == "false": F.append((od - d, c))
        # no labels of the row's own fold may leak: unlabelled rows carry label None anyway
        out = []
        same = [c for g, c in T if g == 0]
        out += [(1 if all(same) else -1) if same else 0]
        for side in (-1, 1):
            s = [(abs(g), c) for g, c in T if g * side > 0]
            if s:
                g, c = min(s); out += [int(c), min(g, 400)]
            else:
                out += [-1, 999]
        b = [x for x in TV if x[0] < 0]; a = [x for x in TV if x[0] > 0]
        out += [(1 if compat(max(b, key=lambda x: x[0])[1], min(a, key=lambda x: x[0])[1]) else 0) if b and a else -1]
        # false evidence: compat false rows near the date argue against
        fc = [abs(g) for g, c in F if c]
        out += [min(fc) if fc else 999, len(fc), sum(1 for g, c in F if not c)]
        # kernel votes from all rows
        wy = sum(math.exp(-abs(g) / TAU) for g, c in A if c)
        wn = sum(math.exp(-abs(g) / TAU) for g, c in A if not c)
        out += [wy, wn, wy / (wy + wn + 0.1), len(A)]
        for side in (-1, 1):
            s = [(abs(g), c) for g, c in A if g * side > 0]
            if s:
                g, c = min(s); out += [int(c), min(g, 400)]
            else:
                out += [-1, 999]
        out += [KINDS.index(v["kind"]) if v["kind"] in KINDS else -1, len(r["facts"]),
                {None: 0, "eq": 0, "gt": 1, "ge": 2, "lt": 3, "le": 4}.get(v.get("op"), 5)]
        return out

    def predict(self, rows):
        out = []
        for r in rows:
            if not r["facts"]:
                out.append(0.9); continue
            X = np.array([self.feat(r, f, False) for f in r["facts"]])
            p = self.iso.predict(self.m.predict_proba(X)[:, 1])
            out.append(float(p.min()))
        return out
