"""
Layer 4 - Calibrated Bayesian Scoring
=====================================
Turns Layer 3's evidence into  label in {true, false, unsure}  and  C in [0.5, 1].

Per atom, the evidence is a likelihood ratio  LR = P(e | true) / P(e | false).
With a prior odds O0 = P(true) / P(false) (learned from labelled rows) and
independent atoms (naive Bayes):
        log O = log O0 + sum_i log LR_i
        P(true | e) = sigma(log O)
Each LR is a Beta-smoothed frequency  (k + a) / (n + a + b)  fitted on
labelled rows grouped by evidence bucket (reason x support x allen relation).
Then
        label = true  if P >= 0.5 else false,   C = max(P, 1 - P)
        label = unsure if C < tau   (tau tuned to maximise the expected score)
Temperature scaling (Guo et al. 2017) fits one T on held-out rows so that the
reported C matches the observed accuracy (minimises log-loss).
"""
from __future__ import annotations

import json
import math
from collections import defaultdict

# Hand-set starting likelihood ratios, used until fit() learns real ones.
DEFAULT_LR = {
    "matches_state": 12.0,
    "contradicts_state": 0.04,
    "known_false_value": 0.02,
    "no_data": 1.0,
    "before_first_observation": 1.0,
    "incomparable_units": 1.0,
    "attribute_not_in_lexicon": 1.0,
    "unknown_subject": 1.0,
}


def bucket(atom) -> str:
    sup = "s1" if atom.support <= 1 else ("s2" if atom.support <= 3 else "s4")
    fuzzy = "fz" if atom.resolution_score < 0.97 else "ex"
    return f"{atom.reason}|{sup}|{atom.allen}|{fuzzy}"


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-max(-40, min(40, x))))


class BayesianScorer:
    def __init__(self, prior_true: float = 0.8, tau: float = 0.6, temperature: float = 1.0,
                 a: float = 1.0, b: float = 1.0):
        self.prior_true = prior_true
        self.tau = tau
        self.T = temperature
        self.a, self.b = a, b
        self.lr_bucket: dict[str, float] = {}
        self.uninformed_to_prior = True   # set False if the contest punishes wrong > unsure

    # -- inference ---------------------------------------------------------
    def atom_lr(self, atom) -> float:
        b = bucket(atom)
        if b in self.lr_bucket:
            return self.lr_bucket[b]
        lr = DEFAULT_LR.get(atom.reason, 1.0)
        if atom.reason == "matches_state":
            lr *= min(atom.support, 5) ** 0.5         # more witnesses, stronger
            if atom.allen not in ("during", "starts", "equals"):
                lr **= 0.7
        return lr ** max(atom.resolution_score, 0.5)

    def probability(self, claim_result) -> float:
        logit = math.log(self.prior_true / (1 - self.prior_true))
        for atom in claim_result.atoms:
            logit += math.log(max(self.atom_lr(atom), 1e-6))
        return sigmoid(logit / self.T)

    def score(self, claim_result) -> tuple[str, float | None, float]:
        """-> (label, confidence or None, P(true))"""
        p = self.probability(claim_result)
        informative = any(a.reason not in ("no_data", "unknown_subject", "attribute_not_in_lexicon",
                                           "before_first_observation", "incomparable_units")
                          for a in claim_result.atoms)
        conf = max(p, 1 - p)
        if any(a.reason in ("attribute_not_in_lexicon", "unknown_subject") for a in claim_result.atoms):
            return "unsure", None, p          # outside the universe: the data can't tell
        if not informative:
            # No witness in the KB: fall back to the prior (most rows are true)
            # only when the prior alone clears tau, else abstain.
            if self.prior_true >= self.tau and self.uninformed_to_prior:
                return "true", round(self.prior_true, 4), p
            return "unsure", None, p
        if conf < self.tau:
            return "unsure", None, p
        return ("true" if p >= 0.5 else "false"), round(min(max(conf, 0.5), 1.0), 4), p

    # -- learning ------------------------------------------------------------
    def fit(self, results_and_labels):
        """results_and_labels: iterable of (ClaimResult, gold) with gold true/false."""
        data = [(r, g) for r, g in results_and_labels if g in ("true", "false")]
        if not data:
            return self
        n_true = sum(g == "true" for _, g in data)
        self.prior_true = (n_true + 1) / (len(data) + 2)
        cnt = defaultdict(lambda: [0, 0])                  # bucket -> [true, false]
        for r, g in data:
            for atom in r.atoms:
                cnt[bucket(atom)][0 if g == "true" else 1] += 1
        tot_t = sum(c[0] for c in cnt.values()) or 1
        tot_f = sum(c[1] for c in cnt.values()) or 1
        for bk, (t, f) in cnt.items():
            if t + f < 5:
                continue                                   # keep the default
            p_e_true = (t + self.a) / (tot_t + self.a + self.b)
            p_e_false = (f + self.a) / (tot_f + self.a + self.b)
            self.lr_bucket[bk] = p_e_true / p_e_false
        return self

    def fit_temperature(self, results_and_labels, grid=None):
        data = [(r, g) for r, g in results_and_labels if g in ("true", "false")]
        if not data:
            return self
        best = (float("inf"), 1.0)
        for T in grid or [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4]:
            self.T = T
            nll = 0.0
            for r, g in data:
                p = min(max(self.probability(r), 1e-6), 1 - 1e-6)
                nll -= math.log(p if g == "true" else 1 - p)
            best = min(best, (nll / len(data), T))
        self.T = best[1]
        return self

    def tune_tau(self, results_and_labels, grid=None, unsure_reward=0.0):
        """Pick tau maximising accuracy where 'unsure' earns `unsure_reward`
        (set it to the contest's real payoff once known)."""
        data = list(results_and_labels)
        best = (-1.0, self.tau)
        for tau in grid or [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]:
            self.tau = tau
            s = 0.0
            for r, g in data:
                lab, _, _ = self.score(r)
                s += unsure_reward if lab == "unsure" and g != "unsure" else float(lab == g)
            best = max(best, (s / max(len(data), 1), tau))
        self.tau = best[1]
        return self

    def save(self, path):
        with open(path, "w") as f:
            json.dump({"prior_true": self.prior_true, "tau": self.tau, "T": self.T,
                       "lr_bucket": self.lr_bucket}, f, indent=1)

    @classmethod
    def load(cls, path):
        with open(path) as f:
            d = json.load(f)
        s = cls(d["prior_true"], d["tau"], d["T"])
        s.lr_bucket = d["lr_bucket"]
        return s
