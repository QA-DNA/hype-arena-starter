"""Algorithm C: temporal-consistency rules -> naive-Bayes log-odds on the training prior.
rule_features(row, train_rows) -> {name: 0/1 or float}; train rows are used leave-one-out (own id skipped)."""
import math, re
from collections import defaultdict
from ..common import key, compat

HEDGE = re.compile(r"\b(about|around|roughly|nearly|almost|approximately|recalls?|rumou?r|reportedly|allegedly|supposedly|still|already|only)\b", re.I)
OPS = {"gt": ">", "lt": "<"}


def _num(v):
    x = v["value"]
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _index(train):
    obs = defaultdict(list)  # key -> [(date, id, value)] of true rows
    attr = defaultdict(lambda: [0, 0])  # attribute -> [true, false]
    for r in train:
        if r["label"] not in ("true", "false"):
            continue
        for f in r["facts"]:
            attr[f["attribute"]][r["label"] == "false"] += 1
            if r["label"] == "true":
                obs[key(f)].append((r["date"], r["id"], f["value"]))
    for v in obs.values():
        v.sort(key=lambda o: o[0])
    dirn = defaultdict(lambda: [0, 0])  # attribute -> [ups, downs] between consecutive true observations
    for k, v in obs.items():
        s = [(x[0], _num(x[2])) for x in v if _num(x[2]) is not None and not x[2].get("op")]
        for (d1, a), (d2, b) in zip(s, s[1:]):
            if d1 < d2 and a != b:
                dirn[k[1]][b < a] += 1
    attr_dir = {a: (1 if u > 3 * d else -1 if d > 3 * u else 0) for a, (u, d) in dirn.items() if u + d >= 2}
    return obs, attr, attr_dir


def _fact_feats(r, f, obs, attr, adir):
    o = [x for x in obs.get(key(f), []) if x[1] != r["id"]]
    v = f["value"]; d = r["date"]
    F = {"unseen": 0, "stale": 0, "never_true": 0, "out_env": 0, "mono_viol": 0, "same_diff": 0, "sandwich": 0, "match_both": 0, "match_one": 0, "same_match": 0}
    if not o:
        F["unseen"] = 1
        return F
    hit = [x for x in o if compat(v, x[2])]
    if not hit:
        F["never_true"] = 1
        if any(x[0] == d for x in o):
            F["same_diff"] = 1
    elif len(hit) < len(o):
        F["stale"] = 1  # true at some other time, not everywhere
    n = _num(v)
    if n is not None and v.get("op") is None:
        nums = [_num(x[2]) for x in o if _num(x[2]) is not None]
        if nums and (n < min(nums) or n > max(nums)):
            F["out_env"] = 1
        ser = [(x[0], _num(x[2])) for x in o if _num(x[2]) is not None]
        bef = [x for x in ser if x[0] < d]; aft = [x for x in ser if x[0] > d]
        g = adir.get(f["attribute"], 0)
        if g and ((bef and (n - bef[-1][1]) * g < 0) or (aft and (aft[0][1] - n) * g < 0)):
            F["mono_viol"] = 1
    b = [x for x in o if x[0] < d]; a = [x for x in o if x[0] > d]
    b = b[-1] if b else None; a = a[0] if a else None
    if any(x[0] == d and compat(v, x[2]) for x in o): F["same_match"] = 1
    if b and a:
        cb, ca = compat(v, b[2]), compat(v, a[2])
        F["match_both"] = int(cb and ca); F["match_one"] = int(cb != ca)
        F["sandwich"] = int(not cb and not ca and compat(b[2], a[2]))
    elif b or a:
        F["match_one"] = int(compat(v, (b or a)[2]))
    return F
    hit = [x for x in o if compat(v, x[2])]
    if not hit:
        F["never_true"] = 1
        if any(x[0] == d for x in o):
            F["same_diff"] = 1
    elif len(hit) < len(o):
        F["stale"] = 1  # true at some other time, not everywhere
    n = _num(v)
    if n is not None and v.get("op") is None:
        nums = [_num(x[2]) for x in o if _num(x[2]) is not None]
        if nums and (n < min(nums) or n > max(nums)):
            F["out_env"] = 1
        ser = [(x[0], _num(x[2])) for x in o if _num(x[2]) is not None]
        vals = [s[1] for s in ser]
        if len(set(vals)) > 1 and len(ser) >= 3:
            up = all(a <= b for a, b in zip(vals, vals[1:])); dn = all(a >= b for a, b in zip(vals, vals[1:]))
            bef = [s[1] for s in ser if s[0] < d]; aft = [s[1] for s in ser if s[0] > d]
            if up and ((bef and n < max(bef)) or (aft and n > min(aft))): F["mono_viol"] = 1
            if dn and ((bef and n > min(bef)) or (aft and n < max(aft))): F["mono_viol"] = 1
    return F


def rule_features(row, train_rows, _idx=None):
    obs, attr, adir = _idx or _index(train_rows)
    fs = [_fact_feats(row, f, obs, attr, adir) for f in row["facts"]]
    out = {k: float(any(F[k] for F in fs)) for k in ("unseen", "stale", "never_true", "out_env", "mono_viol", "same_diff", "sandwich", "match_both", "match_one", "same_match")}
    if not fs:
        out["no_facts"] = 1.0
    t = row["text"]
    out["hedge"] = float(bool(HEDGE.search(t)))
    out["today_date_mismatch"] = float(bool(re.search(r"\btoday\b", t, re.I)) and any(
        f["value"]["kind"] == "date" and len(str(f["value"]["value"])) == 10 and str(f["value"]["value"]) != row["date"] for f in row["facts"]))
    out["future_date_past_tense"] = float(any(
        f["value"]["kind"] == "date" and str(f["value"]["value"])[:10] > row["date"] for f in row["facts"]) and bool(re.search(r"\b(was|were|started|began|opened|founded|joined|launched)\b", t)))
    out["multi_fact"] = float(len(row["facts"]) > 1)
    ar = [attr[f["attribute"]] for f in row["facts"]]
    fr = max(((b + .5) / (a + b + 5) for a, b in ar), default=0.15)  # worst attribute's false rate (smoothed)
    out["attr_false_rate"] = fr
    out["attr_risky"] = float(fr > 0.2)
    return out


BIN = ["unseen", "stale", "never_true", "out_env", "mono_viol", "same_diff", "sandwich", "match_both", "match_one", "same_match", "hedge", "today_date_mismatch",
       "future_date_past_tense", "multi_fact", "attr_risky"]


class Judge:
    name = "c_rules"
    C = 1.0

    def _x(self, r):
        f = rule_features(r, self.train, self.idx)
        return [f[k] for k in BIN]

    def fit(self, train, unlabelled):
        from sklearn.linear_model import LogisticRegression
        tr = [r for r in train if r["label"] in ("true", "false")]
        self.idx = _index(train); self.train = train
        # ponytail: joint logistic fit of per-rule log-odds (NB double-counted correlated rules and lost accuracy)
        self.m = LogisticRegression(C=self.C, max_iter=500).fit([self._x(r) for r in tr], [r["label"] == "true" for r in tr])
        self.weights = dict(zip(BIN, self.m.coef_[0]))

    def predict(self, rows):
        return list(self.m.predict_proba([self._x(r) for r in rows])[:, 1])
