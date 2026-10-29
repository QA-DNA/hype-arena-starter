"""Technique 1: judge A's bracketing features + parse-trust features + soft (runner-up / below-threshold) hypotheses,
with timeline evidence taken from the GOLD facts of labelled training rows (as in the real run, where practice rows come with forms)
while the rows being judged carry PARSED facts. Variants are switched by module flags so the benchmark can compare them.
Needs bench/hyps_<split>.json (written by bench.make_parsed); without it falls back to parse-trust features from the facts alone.
"""
import json, os
from collections import defaultdict
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, cross_val_predict
from .. import common
from ..common import key, compat
from .a_bracket_gbm import Judge as A

GOLD_EVIDENCE = True   # timeline from gold facts of labelled-true train rows
TRUST = True           # parse-trust row features
SOFT = True            # runner-up hypothesis block + pseudo-fact for rows with nothing emitted
HYPS = {}              # id -> per-candidate hypotheses (loaded lazily from bench/hyps_<split>.json)
SPLIT = "date"


def load_hyps(split):
    global HYPS
    p = common.PARSED[split].replace("parsed_", "hyps_")
    HYPS = json.load(open(p)) if os.path.exists(p) else {}


class Judge(A):
    name = "t1_soft"

    def fit(self, train, unlabelled):
        self.obs = defaultdict(list)
        for r in train:
            if r["label"] == "true":
                for f in (r.get("gold") if GOLD_EVIDENCE and r.get("gold") is not None else r["facts"]):
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

    def _alt_block(self, r, f):
        """Features of the runner-up (subject, attribute) hypothesis for the same value."""
        alt = f.get("_alt")
        nan = np.nan
        if not alt:
            return [nan] * 5
        g = {"subject": alt[0], "attribute": alt[1], "value": f["value"]}
        fe = self.fact_feats(r, g)
        return [alt[2], fe["b_ok"], fe["a_ok"], fe["same_bad"], fe["frac_ok"]]

    def row_feats(self, r):
        base = super().row_feats(r)
        extra = []
        facts = r["facts"]
        hy = HYPS.get(r["id"], [])
        if TRUST:
            num = [h for h in hy if h["kind"] not in ("boolean", "name")]
            emitted_num = sum(1 for h in num if h["emitted"])
            ps = [f["_p"] for f in facts if "_p" in f]
            ss = [f["_s"] for f in facts if "_s" in f]
            extra += [len(facts), int(bool(facts)), len(num), len(num) - emitted_num,
                      (emitted_num / len(num)) if num else np.nan,
                      min(ps) if ps else np.nan, float(np.mean(ps)) if ps else np.nan, min(ss) if ss else np.nan]
        if SOFT:
            worst = None
            if facts:
                # runner-up block of the least certain fact
                worst = min(facts, key=lambda f: f.get("_p", 1.0))
                extra += self._alt_block(r, worst) + [0]
            else:
                # nothing emitted: use the best below-threshold hypothesis as a pseudo fact
                cands = [h for h in hy if h["top"] and h["kind"] not in ("boolean",)]
                if cands:
                    h = max(cands, key=lambda h: h["top"][2])
                    pf = {"subject": h["top"][0], "attribute": h["top"][1], "value": h["value"]}
                    fe = self.fact_feats(r, pf)
                    extra += [h["top"][2], fe["b_ok"], fe["a_ok"], fe["same_bad"], fe["frac_ok"], 1]
                else:
                    extra += [np.nan] * 5 + [2]
        return base + extra
