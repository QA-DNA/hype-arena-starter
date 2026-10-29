# Calibration, stacking and abstention for confidence-weighted scoring (Hype or Truth)

Scope: Task 1 (label ~18k rows true/false/unsure + confidence 0.5-1) and, briefly, Task 2 (confidence on 1,000 TRUE claims).
Note on sources: the researcher.md instruction file named in the brief did not exist on disk, and no web fetch was done. Citations below are from memory of the primary papers (titles/venues/years are reliable; page numbers omitted). Numbers marked MEASURED come from the brief; numbers marked SIM come from the simulation in section 1.4 (a made-up distribution matched to the measured 68% / 97.6% / acc 0.92 profile, NOT the real predictions); everything marked EST is my estimate and must be measured with bench/ before being believed.

## 0. Bottom line (read this first)

1. Report c = calibrated P(correct), capped at 0.99 and floored at 0.5. This is optimal for every proper rule (log, Brier, any "confidence-weighted log/Brier") and within a few percent of optimal for the improper "+c / -c" family once the model is well calibrated at the top. Do not report 1.0 ever (log-type scores explode, SIM: c=0.999 turns a log-score of 0.71 into 0.23 per row while gaining only 0.04 on the linear rule).
2. Abstain ("unsure") only for rows where P(gold = unsure) is high (no comparable observation exists for the claim's key, empty parse AND no text signal). Do NOT abstain because P(true/false) is merely low: under every plausible formula where unsure scores 0 and a wrong call costs at most its confidence, answering at c = p >= 0.5 weakly beats abstaining (SIM: every abstention threshold on p lowered the linear, log and Brier score; it only raises "accuracy of what you answered").
3. Biggest likely gains, in order: (A) row-level stacker of the existing judges plus parse-uncertainty features, fit on grouped out-of-fold predictions; (B) a small, honest calibration layer (Platt or beta calibration on the stacker logit, 2-3 parameters, fit on OOF scores) with a Venn-Abers interval used as a diagnostic / extra feature, not as the main method; (C) a three-class unsure head + tiny abstention rule; (D) a prior-shift check (EM) on the unlabelled 18k. Isotonic and conformal prediction are not worth it at n = 1,858.
4. Validation: date-clustered repeated CV + paired cluster bootstrap. With n = 1,858 a paired accuracy difference below ~0.012-0.015 or a log-loss difference below ~0.015-0.02 nats is within noise (derivation in section 5). Several of the gaps in the brief (0.869 vs 0.870; 0.350 vs 0.351) are noise; the 0.869 -> 0.920 gap (parser vs gold facts) is real and is the largest lever, bigger than anything calibration can do. Calibration and stacking polish a score; they cannot create the 14 points of coverage at conf >= 0.9 that parser errors lose.

## 1. Optimal reporting and abstention under plausible scoring formulas

Notation. For a row, the system picks label y_hat and confidence c in [0.5, 1]. Let p = P(y_hat is correct | everything we know) >= 0.5 by construction. Unsure rows (gold) are ~2% and, if we answer true/false on a gold-unsure row, we assume it counts as wrong (worst case) or is ignored (best case). Abstaining scores 0 unless stated.

### 1.1 Formulas and optimal policies

F1. Linear signed score S = +c if right, -c if wrong.
 E[S] = c(2p-1). Linear in c, so optimum is c = 1 whenever p > 0.5. The rule is improper (it rewards overclaiming). Abstain value 0 < E[S] for any p > 0.5, so never abstain on p alone. Risk: ties confidence to nothing; if the true formula is this one, the best possible policy is "always 1.0", and we lose (2p-1)(1-p) per row by reporting c = p (at p = 0.9: 0.08 of a possible 0.80, i.e. 10%).

F2. Linear in (2c-1): S = +(2c-1) right, -(2c-1) wrong (this is the `cw` proxy in bench/common.py). Same conclusion: c = 1.

F3. Brier-type reward. Points = 1 - (c - 1[right])^2 (or its rescaling 1 - 4(...)^2 /..., affine transforms don't change optima). E = 1 - [p(1-c)^2 + (1-p)c^2]; d/dc = 2p(1-c) - 2(1-p)c = 0 gives c = p. Proper (Brier 1950; Gneiting & Raftery 2007, Thm 1). Value at optimum 1 - p(1-p) >= 0.75, so answering beats abstaining unless unsure is scored above 0.75-1.0.

F4. Log score, S = log2(c) + 1 if right, log2(1-c) + 1 if wrong (zero at c = 0.5), or its natural-log version. E = p log2 c + (1-p) log2(1-c) + 1, maximized at c = p, value 1 - H2(p) >= 0 (so again answer beats abstain at 0). Strictly proper. Needs a floor on 1-c: a wrong answer at c = 0.999 costs ~10 bits. Cap at 0.99 (6.6 bits worst case) or 0.98.

F5. Accuracy weighted by confidence: A = sum_i c_i 1[right_i] / sum_i c_i (a plausible reading of "each call is weighted by its confidence"). Fractional-programming: row i should have weight c_i = 1 if p_i > A* and c_i = 0.5 (minimum) if p_i < A*, where A* is the optimal ratio (Dinkelbach). It is also improper, but now confidence acts as a bang-bang selector. If the unsure rows do not enter numerator or denominator, then abstaining on p_i < A* is equivalent to c = 0.5 and slightly better (the denominator shrinks). SIM: A* ~ 0.946 with step policy vs 0.9365 with c = p vs 0.9229 constant c; i.e. +0.01 over c = p. But the step policy costs a lot on proper rules (SIM log score 0.57 vs 0.71).

F6. Threshold reward: +1 if right and c >= tau, 0 below tau (or penalty -w if wrong and c >= tau). Chow's rule: answer ("report c >= tau") iff p >= w/(1+w); with w = 1 that is p >= 0.5; with w = 4 (a wrong call costs four rights) p >= 0.8. Chow (1970) proves this threshold is optimal for known posteriors; El-Yaniv & Wiener (2010) give the risk-coverage framing and show the optimal selective classifier thresholds the posterior (or any consistent monotone proxy).

F7. Brier or log on the full 3-class output where unsure is its own class with a confidence formula we cannot see: not applicable because the spec says unsure carries no confidence; treat unsure as a coverage decision (F6 with reward r_u for correct abstention, -w for wrong). Rule: abstain iff (1-u) * c(2p'-1)... simplest operational form: abstain iff u_hat >= u*, where u_hat = P(gold unsure) and u* = (cost of answering a gold-unsure row)/(cost + reward of a correct abstention) ~ 0.4-0.5 if unsure rows are scored like normal rows, higher if they are ignored.

### 1.2 A robust compromise policy

Because F1/F2/F5 push toward extremes and F3/F4/F6 toward c = p, a minimax-style compromise is:

 c_report = clip( p_cal , 0.5 , 0.99 ), and for p_cal >= 0.97 report 0.99.

Why the cap costs nothing: at p = 0.976, reporting 0.99 instead of 0.976 loses 0.0103 bits of expected log score (KL(p||c)) and gains 0.0133 expected points on F1. At p = 0.95 reporting 0.99 loses 0.077 bits and gains 0.036: not worth it, so only boost the top bin where the calibration curve is verified (>= 0.97 empirically).

Do not "sharpen" mid-range probabilities to hedge F1: SIM shows a 0.9 shrink toward 0.5 loses 0.04 on F1 and 0.03 on F4; sharpening is the mirror image and breaks F3/F4. The calibration curve is the only evidence-based anchor.

Do not floor confidence at something above 0.5 for low-p rows: c = 0.5 for a 50/50 row is correct under all formulas; F5 wants it, F3/F4 want it.

### 1.3 Abstention policy

 - Never abstain for p in [0.5, 0.85]: it costs more than it saves under every formula above except F5 (accuracy-only readout) and a high-penalty F6.
 - Abstain when the evidence says the dataset cannot decide the claim: no extracted fact AND no observation for the (subject, attribute) key on either side of the date AND no other row on the same page/date mentioning the entity. This is literally the definition of "unsure" in the task. Learn P(unsure) with a third class (see 3.3). With only ~37 gold-unsure rows in practice, hand-written structural rules beat a trained head: train/validate on rules like (n_obs == 0 and n_same == 0), and look at the precision of those rules on the 37 rows.
 - Expected gain: at most ~2% of rows x ~(score of correct abstention - answer value ~0.5-1.0) = 0.005-0.02 per row on the final score; the downside of over-abstaining (losing ~0.8 per true/false row on F1) is 40-80x larger per wrongly abstained row. So require u_hat >= 0.5 and validated precision.
 - Compare with F5: if the official text turns out to be "accuracy of weighted calls", you would want c = 0.5 or unsure for p < ~0.9. Hedge: for rows with p in [0.5, 0.6] (almost coin flips) the three options (c=0.5 answer, c = p answer, unsure) differ by little in every formula, so there is no regret in using c = 0.5 there.

### 1.4 Simulation used (SIM)

Mixture matched to the measured profile: 68% of rows from Beta(30, 0.75) (mean 0.976), 32% from Beta(5, 1.2) (mean ~0.81), outcome ~ Bernoulli(p), overall acc 0.923, 400k draws. Score per row:

| policy | F1 linear | F4 log2 (0 at 0.5) | F3 Brier (0 at 0.5) | F5 conf-weighted acc |
|---|---|---|---|---|
| c = p | 0.805 | 0.706 | 0.191 | 0.9365 |
| c = 0.999 | 0.845 | 0.230 | 0.173 | 0.9229 |
| c = min(p, 0.99) | 0.804 | 0.705 | 0.191 | 0.9364 |
| 0.99 if p >= 0.9 else p | 0.816 | 0.684 | 0.191 | 0.9366 |
| shrink 0.5 + 0.9(p - 0.5) | 0.767 | 0.675 | 0.189 | 0.9358 |
| step (1.0 if p > 0.92 else 0.5) | 0.770 | 0.567 | n/a | 0.9461 |
| abstain below p = 0.8 | 0.774 | 0.691 | 0.187 | 0.9627 on answered |
| abstain below p = 0.9 | 0.709 | 0.648 | 0.173 | 0.9753 on answered |

Reading: F1 is the only formula that wants more than c = p, and it gains 0.04 (5%) by going to 1.0, while F4 loses 0.48 (68%). The asymmetry decides it. Script: scratchpad sim.py (not kept in the repo).

### 1.5 Task 2 confidences

Same logic: the claim is graded true/false, confidence = P(true). All claims are intended to be true; the chance they are true is dominated by the generator, not by calibration of a model. Estimate it empirically: run the Task 1 judge on the synthetic claims (as if they were rows on their date) and fit the same calibrator; claims whose generator template and values come directly from a gold fact in the data can sit at 0.97-0.99, claims derived by arithmetic (compare, change) or by joining two facts at 0.9-0.95 with the error rate measured on a self-made validation set (data/synthetic_validation.csv has mutation types). Confidence for the types with unmeasured error rate = the Wilson lower bound of the measured accuracy for that type, not the point estimate (small bins).

### 1.6 Sources

 - Brier, G. W. (1950) "Verification of forecasts expressed in terms of probability", Monthly Weather Review 78.
 - Good, I. J. (1952) "Rational decisions", JRSS B 14 (log score).
 - Gneiting, T. & Raftery, A. E. (2007) "Strictly proper scoring rules, prediction, and estimation", JASA 102(477). Proper rules, their Savage representation, why linear rewards are improper.
 - Murphy, A. H. (1973) "A new vector partition of the probability score", J. Applied Meteorology 12 (reliability/resolution/uncertainty decomposition).
 - Chow, C. K. (1970) "On optimum recognition error and reject tradeoff", IEEE Trans. Information Theory 16(1) (also Chow 1957 for the original).
 - El-Yaniv, R. & Wiener, Y. (2010) "On the foundations of noise-free selective classification", JMLR 11. Geifman & El-Yaniv (2017) "Selective classification for deep neural networks", NeurIPS (SR threshold, risk-coverage curves).
 - Dinkelbach, W. (1967) "On nonlinear fractional programming", Management Science 13 (for the ratio objective F5).

## 2. Candidate techniques, ranked

### Rank 1. Row-level stacking of the judges with parse-uncertainty features (logistic regression meta-learner on grouped OOF logits)

What. Wolpert-style stacked generalisation: base judges (a_bracket_gbm, b_truth, c_rules, optionally e_text/d_knn) produce row-level scores on held-out folds; a low-capacity meta-model combines them. Breiman (1996) "Stacked regressions" shows non-negative constraint on weights stabilises it; for classification use logistic regression on logits.
Citation. Wolpert, D. H. (1992) "Stacked generalization", Neural Networks 5(2). Breiman, L. (1996) Machine Learning 24. Caruana et al. (2004) "Ensemble selection from libraries of models", ICML (forward-selection blending is the robust alternative at small n). Niculescu-Mizil & Caruana (2005) ICML on calibration of ensembles.
Why it fits. The two parser-fact judges have the same accuracy (0.869/0.870) and log-loss (0.350/0.351) but very different confidence profile (37% vs 56% rows >= 0.9 at 95% vs 92.6%), which means their errors are different. Mean of logits of two equally good but imperfectly correlated judges usually beats both. The parse-error mass (acc 0.869 vs 0.920 with gold) is the dominant error source, and it is partly predictable: features describing parse reliability tell the stacker when to trust the facts at all.
Needs. OOF scores of each base judge from the same outer folds (they exist in bench/run.py if it saves predictions; otherwise add a dump). Meta features (all cheap):
 - logit of each judge (clipped to +-6); their difference and max/min.
 - n_facts extracted, any_fact (0/1), fraction of the sentence's numbers/dates/names covered by a fact (parse coverage), parser self-confidence/margin if it has one, number of competing parses.
 - n_obs, n_same, bracket agreement from a_bracket_gbm (the strongest features), days to nearest bracketing observation.
 - row length, number of numeric tokens, hedge words (claims "sources claim", "reportedly", "may") as text features: these correlate with false/unsure strongly in this style of data (EST).
Runtime. Meta-model training < 1 s; the base judges are already in the 30-minute budget; keep inference to one pass over the 18k rows.
Expected gain. EST log-loss 0.350 -> 0.320-0.335 (a 4-9% reduction typical for blending two comparable, partly decorrelated models; Caruana 2004 reports bigger lifts with many models, little with 2); accuracy +0.5 to +1.0 points; share of rows at conf >= 0.9 up from ~37-56% to ~60% at >= 94% (EST). Measure it; if the gain is below 0.015 nats it is noise (section 5).
Recipe.
 1. Fix the outer folds (bench.common.fold_of(rows, 'date')). For each outer fold k, train every base judge on the other 4 folds, and produce its prediction on fold k only; concatenate -> OOF matrix Z (n x m). Inside each base judge training, the internal calibration already used a nested grouped CV (a_bracket_gbm does this); keep it.
 2. For the meta-learner, nested evaluation: to score meta on fold k, fit it on the OOF rows of the other four folds (those rows' base predictions came from models that did see fold k as training data in other outer iterations, which is a standard but slightly optimistic leak; to be clean, redo base judges with 4 folds only and an inner CV, 5x5 cost; at 1.9k rows with GBM of 150 trees that is minutes).
 3. Meta-model: LogisticRegression(C ~ 0.3-1.0) on [logit_a, logit_b, logit_c, logit_a - logit_b, any_fact, log1p(n_obs), parse_coverage, ...]. Standardise features. Optionally an interaction term (any_fact x logit_a) or HistGradientBoosting(max_depth=2, 60 trees, min_samples_leaf=40) as a second meta and average the two.
 4. Row without extracted facts: either give those rows a meta flag and let the intercept learn their own rate (prior 0.85, but text features may do better) or train a dedicated text-only judge (e_text) for them; calibrate that subgroup separately (Mondrian-style calibration by group: any_fact in {0, 1}).
 5. Final: refit the whole stack on all 1,858 rows, with base-judge OOF logits as meta inputs and base judges refit on all rows; at inference base judges see all labelled facts (slightly denser than in CV, which makes real accuracy slightly better than CV; keep calibration unchanged).
Pitfalls.
 - Leakage: meta-model fitted on in-sample base predictions (base judges trained on the same rows) is the classic failure; every base logit fed to the meta must be out-of-fold. Truth-discovery judges that estimate source reliability using ALL rows (including the test row's label if it was in train) must be recomputed per fold.
 - a_bracket_gbm uses leave-one-out observations from true-labelled train rows only; in the real 18k run rows that are unlabelled provide no labelled observations, so the feature density at inference is equal to the density at CV on the labelled rows; keep that consistent (never add predicted-true unlabelled rows as observations without simulating it in CV: pseudo-label feedback inflates agreement and confidence).
 - Stacking with 3+ correlated GBMs and a flexible meta-learner overfits and sharpens confidence; keep the meta linear, regularised, <10 features.
 - Averaging probabilities (not logits) of calibrated models yields under-confidence; logistic stacking on logits or re-calibration after averaging fixes it.
 - Do not tune the meta-learner by minimising accuracy; use log-loss, then check the high-confidence bin.

### Rank 2. Compact parametric recalibration of the stack: Platt or beta calibration on OOF scores, with grouped CV, plus reliability audit (ECE with bootstrap CI) and Venn-Abers as diagnostic

What. A monotone one-dimensional map from the stacker score to P(correct). Platt (1999): sigmoid(a s + b) fit with target smoothing (Lin, Lin & Weng 2007). Beta calibration (Kull, Silva Filho & Flach 2017): sigmoid(a ln s - b ln(1-s) + c), three parameters, contains the sigmoid and its inverse-sigmoid family; handles the skewed score distribution typical of tree models. Temperature scaling (Guo et al. 2017) is Platt with b fixed to 0, one parameter: use it on the logit of a well-centred model, but with a strong class imbalance (85/15) the bias term matters, so use Platt.
Why. Section 3 compares them; at n ~1,900 and 15% minority, a 2-3 parameter map is the only family with low variance. HistGradientBoosting log-loss training already yields roughly calibrated outputs; the measured ECE of 0.014 means the existing Platt step is working. The remaining gain is not in making the curve flatter but in (a) refitting after stacking and (b) subgroup calibration (any_fact, per attribute kind) because miscalibration hides in subgroups (a 0.014 global ECE can hide 0.05 miscalibration in the no-fact group, which is 5-20% of rows).
Needs. OOF stack scores; sklearn LogisticRegression; beta calibration is a 3-feature logistic regression on [ln s, -ln(1-s)] (no new package needed; the `betacal` package is optional).
Runtime. Milliseconds.
Expected gain. Over an already Platt-calibrated GBM: 0.000-0.01 log-loss overall, ECE 0.014 -> 0.008-0.012 (EST); the large effect is protective: it prevents the stacker from being overconfident. Where it matters is the top bin: moving 97.6%-accurate rows from 0.95 to 0.975 confidence is worth ~0.007 bits/row on proper rules.
Recipe.
 1. Take OOF stack score s (probability p_true), clip to [0.001, 0.999], z = logit(s).
 2. Fit LogisticRegression(C=1e4 (almost unregularised) or C=10) on features [z] (Platt) and on [ln s, -ln(1-s)] (beta). Select between them and "no calibration" by repeated grouped-CV log-loss (not by ECE alone: ECE binning noise at n = 1,858 is about +-0.01, section 5).
 3. Evaluate a 10-bin reliability table with Wilson intervals; the only bins that matter are >= 0.9 and 0.5-0.7.
 4. Subgroup check: the same table per group any_fact, kind of main fact (money, date, name, quantity), and attribute family. If a group has > 150 rows and deviates by > 2 SE, give it its own intercept offset (add the group indicator as an additional logistic regressor on z: z' = a z + b + b_g; shrink b_g with L2).
 5. Fit final calibrator on all OOF scores; apply to the final stack's scores for the 18k rows. Cap at 0.99, floor 0.5.
 6. Optional Venn-Abers (Vovk & Petej 2014, UAI; Vovk, Petej & Fedorova 2015 NIPS): inductive version, two isotonic fits with the new point added as 0 and as 1, giving [p0, p1]; cost O(n log n). Use p = p1/(1 - p0 + p1) as the point estimate or just the interval width (p1 - p0) as a feature/diagnostic: wide intervals flag rows where the calibration data is thin (they concentrate at extremes). It is well-calibrated by construction under exchangeability but exchangeability is violated here (date shift), and isotonic base fits are step functions with ~20 steps at n = 1.9k: a diagnostic, not the primary method.
Pitfalls.
 - Calibrating on the same rows the model was trained on (the Platt-on-train mistake). Use OOF scores only; a_bracket_gbm already does this inside, but the stack's top-level calibrator must again be fitted on outer-OOF scores, not on the inner calibrated outputs of a model that saw the rows.
 - Isotonic regression (Zadrozny & Elkan 2002, KDD) on ~1.9k rows with 15% minority: Niculescu-Mizil & Caruana (2005) found isotonic worse than Platt below roughly 1,000 positives-balanced samples because it overfits steps, and our minority class has ~280 rows. It also returns exact 1.0/0.0 plateaus: a gift for log-score disasters. Use only after a pooled, smoothed version (monotone GAM, 5 knots) if parametric forms fail the reliability test.
 - Temperature scaling on a tree/GBM output does nothing for class-prior miscalibration.
 - Do not use ECE as an objective; ECE is biased upward at small n (bins with 20-30 rows), and the bench ECE uses only 5 bins from 0.5; it ignores the 0.5-0.9 sub-structure.
 - Conformal prediction (Vovk, Gammerman & Shafer 2005; Angelopoulos & Bates 2021 "A gentle introduction to conformal prediction"): outputs sets {true}, {false}, {true,false}, not probabilities. Set size 2 maps naturally to unsure, but coverage guarantees are marginal and require exchangeability (broken by date shift), the 15% minority class needs Mondrian (class-conditional) calibration with ~280 points, and nothing here tells you what confidence to print. It adds nothing over a calibrated probability + threshold. Skip.

### Rank 3. Row-level aggregation of fact-level probabilities (learned noisy-AND) and calibration at the row level

What. A row is false if ANY fact is false; each fact has p_i = P(fact i true). Naive product (Pearl 1988, noisy-AND / independence) over-penalises rows with many facts when facts are positively correlated (parser/context errors are shared by facts from the same sentence), and misses that multiple facts in one sentence are often all edited together by the same generator mutation (a lie usually changes one value, not all).
Why. Rows with several facts have a different error structure from single-fact rows; row-level calibration is what is scored.
Recipe.
 1. Base: fact-level classifier outputs p_i for each fact (a_bracket_gbm builds fact-level features and aggregates them in row_feats; I did not read how, so check bench/judges/a_bracket_gbm.py).
 2. Row features: logit of min_i p_i, logit of product, mean logit, number of facts n, count of facts with p_i < 0.5, the most uncertain fact margin. Feed these to the meta-learner of Rank 1 (so Ranks 1 and 3 are one component: the stacker input includes row-level aggregates, not one product).
 3. Calibrate once at the row level (Rank 2) with group offset by n_facts in {1, 2, 3+}.
 4. If a fact is missing from the parse (parse empty or fewer facts than numbers in the sentence), the row-level probability must regress toward the prior: add feature unparsed_numeric_tokens = (# numbers/dates/names in text) - (# matched by facts); calibrate with it.
Expected gain. EST 0.003-0.01 log-loss compared with a plain product; larger on multi-fact rows. Evidence is weak; compare min vs product vs learned in the same grouped CV.
Pitfalls. Training the fact-level model with row labels produces noisy fact labels (a false row with 3 facts has only one false fact); the truth-discovery GBM already faces this; do not treat all facts of a false row as false. Use multiple-instance learning style: fit at the row level on aggregate features, never per-fact with the row's label.

### Rank 4. Prior-shift handling and a tiny abstention head (EM prior adjustment + structural unsure rule)

What. Saerens, Latinne & Decaestecker (2002) "Adjusting the outputs of a classifier to new a priori probabilities: a simple procedure", Neural Computation 14(1): EM re-estimation of class priors on an unlabelled target set from calibrated posteriors, then multiply by new/old prior ratios. Lipton, Wang & Smola (2018) "Detecting and correcting for label shift with black box predictors", ICML (BBSE) is the confusion-matrix alternative.
Why. The unlabelled 18k are the bulk of the score. Practice is 85/15/2; if the full set has 80% true, a model calibrated to 85% over-reports true confidence by ~5% on borderline rows. Also the unsure share may differ. Practice might be a stratified sample.
Needs. Predicted p on the 18k (available at inference). No labels.
Recipe.
 1. Compute mean calibrated p_true on the 18k vs on practice OOF. If |difference| < 0.02, ignore it (the sampling noise of the practice mean at n=1,858 is ~0.008, plus the model's error).
 2. If larger, run EM: pi_new <- mean over rows of posterior_new, with posterior_new ∝ p_i * pi_new/pi_old (and symmetric for false), iterate to convergence (10 iterations). Apply the logit shift log(pi_new/(1-pi_new)) - log(pi_old/(1-pi_old)) to the final scores. This is exact only if the shift is a pure label shift (P(x|y) same); here the shift mechanism is more likely covariate shift (more dates, other products). Treat EM as a diagnostic first.
 3. Do not apply it blindly: if the model's calibration on the 18k is off because of density differences (bracketing observations are sparser in the unlabelled universe), EM will wrongly read that as a prior shift.
 4. Unsure head: add a third class (n ~37 positives). Use rules (no observation both sides, no extracted fact, key unseen) instead of a learned head; evaluate precision/recall on the 37; abstain only when precision >= 0.6 on practice.
Expected gain. Prior shift: 0 if absent, up to 0.01 log-loss if present (EST). Abstention: 0.005-0.02 per-row score at most. This is the lowest rank because of small expected gain, but the cost is minutes and it protects against a bad surprise.
Pitfalls. EM on poorly calibrated posteriors amplifies errors; unsure rows in practice are only 2% (37 rows), which makes any learned abstention head high-variance; "unsure" might have a different definition in the unlabelled set (e.g. rows lacking a comparison point precisely because the dataset thins out later in the year: check whether p_unsure rises for the last months, since the label depends on future/past coverage and practice dates may not cover the same range).

## 3. Calibration methods at n ~ 1,900: comparison

| method | parameters | minority-class support needed | risk at this n | verdict |
|---|---|---|---|---|
| Temperature scaling (Guo 2017) | 1 | tiny | cannot fix bias (needs b with 85/15) | only if outputs already centred; else use Platt |
| Platt (Platt 1999; Lin-Lin-Weng 2007 target smoothing) | 2 | ~100 | low | default; what the best judge already uses |
| Beta calibration (Kull 2017) | 3 | ~200 | low | try it on tree scores; select by repeated grouped CV |
| Isotonic (Zadrozny & Elkan 2002) | ~15-30 steps | >1,000 | high; flat 1.0 plateaus; ties | avoid at 280 minority rows (Niculescu-Mizil & Caruana 2005) |
| Venn-Abers (Vovk & Petej 2014) | non-param., two isotonic fits | >1,000 | wide intervals at extremes; exchangeability | diagnostic only |
| Conformal (Vovk 2005) | none | n/a | no probability, marginal coverage only | skip |
| Histogram binning (Zadrozny & Elkan 2001) | #bins | >500 | coarse, discontinuous | skip |

Practicalities to avoid leakage and overfit on date-grouped splits:
 - Always calibrate on OOF scores whose folds are the date groups (a row's date partner rows must not appear in the training of the model that scored it). In sklearn: cross_val_predict(..., cv=GroupKFold(5), groups=date) as in a_bracket_gbm; do NOT use CalibratedClassifierCV(cv=5) without groups on this data (it would put same-date rows on both sides).
 - Repeat the grouped split with several shuffles of the date-to-fold map (GroupKFold has no shuffle; use the bench.common.fold_of with random.Random(seed) for seeds 0..9). Single-seed numbers on ~370 rows per fold have SD ~0.005 in log-loss.
 - The calibration map's own optimism: evaluate calibrated log-loss by fitting the calibrator on four outer folds and scoring the fifth; a calibrator fit and scored on the same OOF vector reports a flattering ECE.
 - Report both global calibration and calibration for p >= 0.9, the region that drives the weighted score.
 - ECE with n = 1,858: standard error of a bin with 100 rows at p = 0.95 is sqrt(.05*.95/100) = 0.022; any ECE difference below ~0.01 is noise. Prefer log-loss/Brier and the reliability table with Wilson intervals; see also Murphy decomposition: Brier = reliability - resolution + uncertainty, where only reliability is fixed by calibration.

## 4. Stacking details specific to this data

 - Base judges are not independent: a_bracket and b_truth both build on the same parsed facts, so they share parser errors (the main error source). The best-diversity candidate is a text-only judge (e_text, d_knn) that does not depend on the parse; its marginal value is largest on rows with an empty/failed parse. Quantify through the stacker's coefficient and the paired-bootstrap gain, not by intuition.
 - Rows with an empty parse. (1) A flag feature plus the group-wise calibrator (Rank 2); (2) text-only model for those rows only; (3) the prior 0.85 is the sensible fallback if nothing else is known, but 0.85 is the average over the whole set, not for those rows: estimate the empirical accuracy of "true" on the empty-parse practice rows (maybe they are lies the parser cannot read, or they are boilerplate, true) and use that rate, with a Wilson-bounded shrink toward 0.85 if the group has < 100 rows. EST: this group's rate differs from 0.85 by more than 0.05 in either direction; a fixed 0.85 on it costs ~0.01-0.02 log-loss per such row.
 - Parse uncertainty as an input, not a post-hoc fix. Alternatives: (a) feed parser margins as stacker features (cheap); (b) run the judge on the top-k parses and pass the disagreement (std of logit across parses) as a feature; (c) augment the training data by corrupting gold facts with the parser's measured error pattern so the judge sees noisy facts in training (noise-aware training; this narrows the 0.920 vs 0.869 gap on distribution; the benefit is calibration more than accuracy). Train the judge on parsed facts (OOF parser) rather than gold: it matches the test conditions; the brief already shows this is the honest setting.
 - Do not stack with a flexible GBM meta-learner on 1.9k rows with 5 or more correlated inputs: expected log-loss increases relative to LR (EST); if you try GBM meta, use depth 2, heavy regularisation, and compare in the same repeated CV.
 - Blending weights from forward selection over a grid (Caruana) are more stable than LR coefficients when judges are highly correlated; try a 1-parameter blend w*logit_a + (1-w)*logit_b + recalibration as the baseline for the stack, because it has 3 parameters total and is hard to overfit.

## 5. Honest validation with small data

Sampling error of the headline numbers (n = 1,858):
 - Accuracy 0.92: SE = sqrt(.92*.08/1858) = 0.0063 (95% half-width 0.012), before clustering.
 - Paired difference of two judges: SE = sqrt(d)/sqrt(n) where d is the disagreement rate; for accuracies 0.92 vs 0.87 with ~10% disagreement SE ~0.0073, so differences below ~0.015 are within 2 SE. Differences between judges within 0.01 of each other (0.869 vs 0.870) are ties.
 - Log-loss: per-row loss SD ~0.6; paired difference SD ~0.3-0.4, SE ~0.008-0.009; so detectable difference ~0.018 nats (95%). The gaps 0.350 vs 0.351 are noise; 0.222 vs 0.350 is far outside noise (but is a fact-source difference, not a modelling one).
 - ECE: see section 3; treat < 0.01 differences as noise.
 - Date clustering: rows sharing a date (and the same page) are correlated, so the effective sample size is smaller than 1,858 (design effect 1 + (m-1) rho; with ~20 rows/date and rho = 0.05, deff ~ 2). Compute CIs with a cluster bootstrap (resample dates with replacement, Cameron, Gelbach & Miller 2008 "Bootstrap-based improvements for inference with clustered errors", Rev. Econ. Stat.) rather than a row bootstrap; expect intervals ~1.3-1.5x wider than the naive ones.
Procedure.
 1. 5-fold grouped by date, repeated 10 times with different date permutations (bench.common.fold_of with new seeds), mean and SD of log-loss, Brier, accuracy, cw (the proxy) and the >= 0.9 bin accuracy/coverage.
 2. Paired cluster bootstrap on OOF predictions (2,000 resamples of dates) for every pairwise comparison; report the difference with 95% CI. Never compare means from different splits.
 3. Selection bias: if you try 30 variants and pick the best, the winner's CV score is optimistic by ~1 SE of the paired differences; hold out a final check: lock the model, then evaluate once on `data/synthetic_validation.csv` (its mutation types make a useful stress test, but note it is synthetic and its falsity distribution differs from the real set) and on the last K dates held out in time (train on earlier, test on later: the actual deployment has temporal structure).
 4. Report the full score under several candidate formulas (F1-F5) side by side so the decision does not hinge on one guess.
Leakage traps in this setup.
 - Row-wise split (the `check.sh`-style 'row' split in bench/common.py) lets same-date neighbours sit on both sides; the bracketing features then see the real neighbouring observation. In the real run, do the 18k unlabelled rows have neighbours in the practice set? Unknown, but practice is 1,897 of ~20k rows: ~9.5% of the pages, so most unlabelled rows have few labelled same-date neighbours. Date-grouped CV is the right (conservative) choice; the row split is optimistic. The mismatch between densities (80% of practice in CV training vs 100% at inference) is mild and conservative.
 - Leave-one-out features computed from the full labelled set, then used in a CV where the test fold's labels contribute to the observation table: a_bracket_gbm builds self.obs from `train` only, which is correct; the truth-discovery judge must be checked for the same property. Quick test: set all test-fold labels to a garbage value (e.g. flip them) and re-run; scores must not change.
 - Using the gold `form` (facts) on test rows overstates performance (0.920 vs 0.869): the 'parsed' mode must use out-of-fold parser output, and any parser lexicon/rule built by looking at all practice rows (data/lexicon.json derived from the practice set?) leaks if the lexicon encodes values from test-fold rows. Build lexicon per fold or treat the 0.869 figure as the optimistic bound.
 - Hyper-parameter selection on the same folds used for reporting (nested CV; Cawley & Talbot 2010, JMLR 11).
 - Tuning the confidence cap/boost (0.99, 0.97 threshold) on the data it is evaluated on: fix by rule, not by search.
 - Duplicates and template-based near-duplicates across folds (the dataset appears to have page/deck variants of the same sentence at different dates); the date grouping handles identical dates but not the same sentence one month later; see whether grouping by (subject, attribute) cluster changes the numbers: if the CV score drops materially, the model is relying on memorised attributes.
 - Reading the proxy: `cw` in bench/common.py = mean of ((2c-1) * sign) corresponds to F2 only.

## 6. What would NOT help (be critical)

 - Isotonic or histogram calibration on 1.9k rows: more variance than benefit.
 - Conformal sets: no calibrated confidence output, exchangeability broken.
 - Deep calibration tricks (focal loss, label smoothing, Dirichlet calibration, ensembles of dozens of GBMs): small-data overkill; the dominant error is the parse, not calibration. Calibration cannot raise coverage at conf >= 0.9 from 37% to 68%.
 - Abstaining on moderate-confidence rows to raise "accuracy on answered": it is the wrong objective unless the official formula is ratio-based and unsure is excluded from the denominator, which the text does not state ("an unlabelled row with no label counts as unsure" suggests unsure rows are in the sample and counted).
 - Reporting 1.0 or sharpening to "game" a linear formula: asymmetric downside under log/Brier-type scoring.
 - Pseudo-labelling the 18k unlabelled rows and retraining: self-confirmation inflates confidence; only permitted with a fold-simulated check; in a calibration-weighted metric it is dangerous.
 - Meta-learners with many features on 1,858 rows; GBM stacker; random hyper-parameter search with many trials (selection bias, section 5).
 - Estimating prior shift with EM when the real shift is covariate shift.

## 7. Concrete next steps (ordered, ~3-4 hours of work)

 1. Dump OOF predictions of every judge under date folds with 10 seeds (bench/run.py extension); store as npy (rows x judges x seeds).
 2. Add `bench/stack.py`: LR meta on logits + 6-8 cheap features; evaluate with paired cluster bootstrap against the best single judge. Accept only if the 95% CI of the log-loss gain excludes 0.
 3. Add Platt vs beta vs none on the stack output, group offsets for any_fact and n_facts; print the reliability table for p >= 0.9.
 4. Fix the output rule: conf = clip(p, 0.5, 0.99), 0.99 only if the verified top bin accuracy >= 0.975; label = argmax; unsure only for the structural rule with validated precision.
 5. Compute mean predicted p on the unlabelled set once it is available at run time; log it; apply the EM shift only if |delta| > 0.03 and the shift is plausible.
 6. Report side-by-side the F1-F5 scores in the final bench table.

## 8. Reference list (primary sources)

 - Platt, J. (1999) Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods. In Advances in Large Margin Classifiers, MIT Press. Lin, H.-T., Lin, C.-J. & Weng, R. C. (2007) A note on Platt's probabilistic outputs for SVMs. Machine Learning 68.
 - Zadrozny, B. & Elkan, C. (2001) Obtaining calibrated probability estimates from decision trees and naive Bayesian classifiers. ICML. (2002) Transforming classifier scores into accurate multiclass probability estimates. KDD.
 - Niculescu-Mizil, A. & Caruana, R. (2005) Predicting good probabilities with supervised learning. ICML.
 - Kull, M., Silva Filho, T. M. & Flach, P. (2017) Beta calibration: a well-founded and easily implemented improvement on logistic calibration for binary classifiers. AISTATS (PMLR 54).
 - Guo, C., Pleiss, G., Sun, Y. & Weinberger, K. Q. (2017) On calibration of modern neural networks. ICML.
 - Vovk, V. & Petej, I. (2014) Venn-Abers predictors. UAI. Vovk, V., Petej, I. & Fedorova, V. (2015) Large-scale probabilistic predictors with and without guarantees of validity. NeurIPS.
 - Vovk, V., Gammerman, A. & Shafer, G. (2005) Algorithmic Learning in a Random World. Springer. Angelopoulos, A. & Bates, S. (2021) A gentle introduction to conformal prediction and distribution-free uncertainty quantification. arXiv:2107.07511.
 - Gneiting, T. & Raftery, A. E. (2007) Strictly proper scoring rules, prediction, and estimation. JASA 102. Brier (1950), Good (1952), Murphy (1973) as in 1.6.
 - Chow, C. K. (1970) On optimum recognition error and reject tradeoff. IEEE Trans. IT 16. El-Yaniv & Wiener (2010) JMLR 11. Geifman & El-Yaniv (2017) NeurIPS.
 - Wolpert (1992) Neural Networks 5; Breiman (1996) Machine Learning 24; Caruana et al. (2004) ICML.
 - Saerens, M., Latinne, P. & Decaestecker, C. (2002) Neural Computation 14. Lipton, Z., Wang, Y.-X. & Smola, A. (2018) ICML.
 - Cawley, G. & Talbot, N. (2010) On over-fitting in model selection and subsequent selection bias in performance evaluation. JMLR 11. Roberts, D. R. et al. (2017) Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. Ecography 40. Cameron, A. C., Gelbach, J. & Miller, D. (2008) Bootstrap-based improvements for inference with clustered errors. Rev. Econ. Stat. 90. Efron, B. & Tibshirani, R. (1993) An Introduction to the Bootstrap. Nadeau, C. & Bengio, Y. (2003) Inference for the generalization error. Machine Learning 52.
 - scikit-learn docs: Probability calibration (sklearn.calibration, CalibratedClassifierCV, calibration_curve), GroupKFold, HistGradientBoostingClassifier.
