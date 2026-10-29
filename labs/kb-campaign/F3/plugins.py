"""F3 exports for other families and the combination phase (FINAL 02:30). Refs resolve with $KBC/F3 on sys.path,
or as 'F3/<file>.py:<name>' through harness api.resolve from $KBC.

Calibrators: calib.fit_calibrator(name, s, y01) -> f; f(s_new) -> (p, width or None). Fit on OUT-OF-FOLD scores.
             One-class or empty input gives a constant calibrator (never crashes).
Abstention:  calib.Decider(calib, policy, alpha, k, target, conf).fit(s_oof, y3, pages, noev).decide(s, noev)
             -> (labels, conf in [0.5, 1] or NaN on unsure, calibrated p). Policy parameters are chosen on
             cross-fitted calibrated scores (calibrator refitted without each page fold), objective = arena points
             (+1 correct incl. correct unsure, 0 wrong unsure, -1 wrong true/false).
             Policies: never05 (t = 0.5), never (t by points), points (t + unsure band by points), conformal
             (marginal split conformal), mondrian (per-class), confpts / mondpts (alpha by points), vaw (Venn-Abers
             width), noev, noev+points, arena3 (argmax{2P(t)-1, 2P(f)-1, P(u)}, P(u) binned on the score; no free
             threshold). calib.wrap(s_tr, y3_tr, pages_tr, s_te, calib=..., policy=...) is the one-call form.
Wrap ANY variant: fusion.Wrap(inner=<variant spec>, inner_params, calib, policy): out-of-fold row scores of any
             harness variant (score = conf if label true, 1-conf if false, 0.5 if unsure) by re-running it with
             one labelled page fold hidden at a time, then Decider. One-class worlds fall back to practice.
Transfer:    fusion.Variant(tmask=1): on ..t tracks, fit on masked copies of practice at the target world's
             labelled share instead of fully labelled practice.

RECOMMENDED for Phase 3 (P80/P10 evidence in the F3 report):
  * Wrapping an already well-calibrated scorer (F2 Chain and anything built on it): calib "none" or "temp",
    policy "never05" (or "points", +0.003 selection, within noise). DO NOT use "platt" on top of the chain at
    P10: it drops P10 from 0.7637 to 0.7158 (false recall 0.475 -> 0.243).
  * Wrapping a raw / uncalibrated scorer (LR margins, v9-style products): calib "va" or "beta" (best ECE), or
    "platt" (best P10 Brier); policy "never05" or "arena3". Abstention gave no measurable points gain anywhere.
"""
PLUGINS = {
    "platt": {"ref": "calib:fit_calibrator", "args": {"name": "platt"}, "kind": "calibrator", "k": 1,
              "desc": "Platt scaling on logit(score), Platt's smoothed targets"},
    "temp": {"ref": "calib:fit_calibrator", "args": {"name": "temp"}, "kind": "calibrator", "k": 1,
             "desc": "temperature scaling of logit(score), no bias: never moves the 0.5 decision"},
    "beta": {"ref": "calib:fit_calibrator", "args": {"name": "beta"}, "kind": "calibrator", "k": 1,
             "desc": "beta calibration (Kull 2017), 3 parameters, unconstrained"},
    "iso": {"ref": "calib:fit_calibrator", "args": {"name": "iso"}, "kind": "calibrator", "k": 1,
            "desc": "isotonic regression (PAV), clipped"},
    "hist": {"ref": "calib:fit_calibrator", "args": {"name": "hist"}, "kind": "calibrator", "k": 1,
             "desc": "equal-frequency histogram binning, 10 bins, Laplace-smoothed, monotone"},
    "va": {"ref": "calib:fit_calibrator", "args": {"name": "va"}, "kind": "calibrator", "k": 2,
           "desc": "inductive Venn-Abers: p = p1/(1-p0+p1) and interval width p1-p0"},
    "decider": {"ref": "calib:Decider", "kind": "abstention", "k": None,
                "args": {"calib": "none", "policy": "never05", "k": 5, "conf": "class"},
                "desc": "calibrator + policy (never05 never points conformal mondrian confpts mondpts vaw noev "
                        "noev+points arena3); conf = calibrated P(label) clipped to [0.5, 1]"},
    "wrap": {"ref": "calib:wrap", "kind": "abstention", "k": None,
             "desc": "one call: fit Decider on out-of-fold labelled scores, decide new scores"},
    "wrap_variant": {"ref": "fusion:Wrap", "kind": "abstention", "k": None,
                     "args": {"inner": "F2/f2var.py:Chain",
                              "inner_params": {"engine": "viterbi", "eps_a": 0.0005, "lam_scale": 1, "mono": 0.1,
                                               "pi_o": 2, "vote_lr": 48},
                              "calib": "none", "policy": "never05"},
                     "desc": "harness variant wrapping any variant with an F3 calibrator and policy"},
    "fusion_lr": {"ref": "fusion:Variant", "kind": "variant", "k": None,
                  "args": {"mp": {"C": 0.1}, "calib": "iso", "policy": "never05",
                           "drop_features": list(range(45)),
                           "extra_features": ["F3/feats.py:chain_vit", "F3/feats.py:chain_hmm"]},
                  "desc": "learned LR fusion on F2 chain scores only (F3 TOP 2); add tmask=1 for ..t tracks"},
    "chain_vit": {"ref": "feats:chain_vit", "kind": "feature", "k": 2,
                  "desc": "F2 Chain viterbi score (own page excluded) + NaN flag, F2 best params"},
    "chain_hmm": {"ref": "feats:chain_hmm", "kind": "feature", "k": 2,
                  "desc": "F2 Chain HMM posterior logit (own page excluded) + NaN flag, F2 best params"},
    "no_evidence": {"ref": "fusion:no_evidence", "kind": "row-flag", "k": 1,
                    "desc": "rows none of whose facts has an observation of its key on another page"},
}
