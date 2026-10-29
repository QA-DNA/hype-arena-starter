from collections import defaultdict
from ..common import key, compat


class Judge:
    """Reference rule from tasks/algorithms.md: value on both sides of the date decides; fixed probabilities per bucket."""
    name = "bracket_rule"

    def fit(self, train, unlabelled):
        self.obs = defaultdict(list)  # key -> [(date, value)] of true rows
        for r in train:
            if r["label"] == "true":
                for f in r["facts"]:
                    self.obs[key(f)].append((r["date"], f["value"]))
        for v in self.obs.values():
            v.sort(key=lambda o: o[0])

    def one(self, r, f):
        obs = self.obs.get(key(f))
        if not obs:
            return 0.95
        same = [o for o in obs if o[0] == r["date"]]
        if same:
            return 0.97 if all(compat(f["value"], o[1]) for o in same) else 0.25
        b = [o for o in obs if o[0] < r["date"]]; a = [o for o in obs if o[0] > r["date"]]
        b = b[-1] if b else None; a = a[0] if a else None
        if b and a:
            cb, ca = compat(f["value"], b[1]), compat(f["value"], a[1])
            if cb and ca: return 0.99
            if cb or ca: return 0.88
            return 0.03 if compat(b[1], a[1]) else 0.5
        o = b or a
        return 0.99 if compat(f["value"], o[1]) else 0.6

    def predict(self, rows):
        out = []
        for r in rows:
            ps = [self.one(r, f) for f in r["facts"]]
            out.append(min(ps) if ps else 0.95)
        return out
