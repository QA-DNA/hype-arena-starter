# F3 report: learned fusion, calibration and abstention

Saved by the orchestrator from F3's final message (02:20). Plugins final in `F3/plugins.py` (13 entries, every ref checked). Results: `results/F3.jsonl` (local, 551 lines), `results/F3-remote.jsonl` (remote g1, 2256 lines, pulled 02:17); paired deltas `F3/paired.jsonl`; practice-only transfer `F3/ptransfer.jsonl`. Selection on P80 and P10 only; suite tracks are tests.

## Bottom line

- Best: F2's chain with no calibration of its own, `fusion.py:Wrap` calib none, policy points: sel 0.8003 (P80 0.8334, P10 0.7671), vs v9 bar 0.809 / 0.674.
- Calibration and abstention add nothing measurable on the chain: paired vs plain never05 P10 +0.0034 (se 0.0041, wins 3/10).
- Platt on the chain is harmful at P10: -0.048 points (se 0.015).
- Learned fusion is significantly worse than the chain's own probabilities: LR on chain scores loses 0.008 on P80 and 0.021 on P10 (paired).
- Abstention never paid: every abstaining policy equal to or worse than threshold 0.5.
- On a raw V9-feature scorer, only `tmask=1` gave a large transfer gain: Sdev-jt 0.660 -> 0.841.

## 1. Results by family (P80 / P10)

Baselines: harness V9 select=points P80 0.8092, P10 0.6739; always-true 0.6668 / 0.6621.

Models (45 V9 base columns and stage 2; best sel per family):

| Model / granularity / aggregation | sel | P80 pts (ECE) | P10 pts (ECE, Brier) |
|---|---|---|---|
| lr, fact, prod, C0.1 platt selftrain 1 | 0.7531 | 0.8197 (0.022) | 0.6864 (0.035, 0.114) |
| rf, fact, min, iso, leaf 3 | 0.7502 | 0.8292 (0.015) | 0.6712 (0.046, 0.114) |
| lr, fact, min | 0.7489 | 0.8081 (0.011) | 0.6897 (0.050, 0.118) |
| hgb, row (stage2 off), platt | 0.7489 | 0.8113 (0.011) | 0.6865 (0.049, 0.115) |
| rf, fact, prod | 0.7472 | 0.8255 (0.033) | 0.6690 (0.036, 0.113) |
| lr, fact, learned aggregator | 0.7458 | 0.8134 (0.021) | 0.6781 (0.049, 0.123) |
| rf, row | 0.7455 | 0.8113 (0.012) | 0.6798 (0.050, 0.114) |
| lr, row, C0.5 | 0.7393 | 0.8071 (0.010) | 0.6716 (0.053, 0.126) |
| lr, fact, geo | 0.7387 | 0.7918 (0.012) | 0.6856 (0.051, 0.120) |
| hgb, fact, prod, depth 2 | 0.7329 | 0.7912 (0.013) | 0.6746 (0.039, 0.116) |

P10 smoke tests with default parameters: blend 0.6783 (ECE 0.044, 34.6 s per P10 job), stack 0.6683 (0.048, 124.8 s), mlp 0.6679 (0.068, 10.1 s), svm + Platt 0.6640 (0.057, 1.8 s), et 0.6512 (0.047, 12.6 s), knn 0.6471 (0.053, 1.5 s). None beats LR.

Granularity: fact+prod, fact+min and row-level within noise; learned aggregator and geo never better.

LR options (best sel with the option on): selftrain 1 0.7531 (0.8197 / 0.6864); target tvf 0.7491; conf = max(p, 1-p) 0.7489; stage2 off 0.7485 (0.8039 / 0.6930); L1 0.7443; onehot kind 0.7430; class weights balanced 0.7321; C auto 0.8028 / 0.6811; cscale 0.5 0.8155 / 0.6833; rmask 0.5 0.784 / 0.679; rmask 0.8 0.791 / 0.685. All within noise of plain LR C0.1 or worse.

Regularization vs label count (max points over calibrators and policies):

| C | 0.003 | 0.01 | 0.03 | 0.1 | 0.3 | 1 | 3 | 10 |
|---|---|---|---|---|---|---|---|---|
| P80 | 0.7860 | 0.8071 | 0.8123 | 0.8176 | 0.8113 | 0.7976 | 0.8007 | 0.7891 |
| P10 | 0.6624 | 0.6792 | 0.6918 | 0.6955 | 0.6888 | 0.6801 | 0.6747 | 0.6683 |

Other families' plugins in LR fusion (never05 or arena3):

| Features | sel | P80 / P10 |
|---|---|---|
| chain only (drop 45 base columns, add `chain_vit` + `chain_hmm`), C0.1 iso never05 | 0.7828 | 0.8229 / 0.7428 |
| chain + F1 td_all + base, C0.01 platt arena3 | 0.7775 | 0.8218 / 0.7332 (P10 ECE 0.025, best) |
| chain + td_all + f2all + F5 generic, C0.01 iso | 0.7768 | 0.8092 / 0.7444 |
| td_all + f2all + F5 generic, C0.03 platt | 0.7698 | 0.8166 / 0.7230 |
| F1 td_all, C0.03 platt | 0.7665 | 0.8123 / 0.7207 |
| f2core, C0.1 platt | 0.7602 | 0.8239 / 0.6965 |

F5 alone about 0.69 on P10; v12 features no gain.

Calibrators (mean over grid A of LR base configs):

| Calibrator | mean sel | P80 ECE | P10 ECE | P80 Brier | P10 Brier |
|---|---|---|---|---|---|
| beta | 0.7226 | 0.0128 | 0.0412 | 0.0846 | 0.1230 |
| iso | 0.7226 | 0.0159 | 0.0500 | 0.0853 | 0.1258 |
| platt | 0.7223 | 0.0199 | 0.0422 | 0.0854 | 0.1217 |
| va | 0.7212 | 0.0135 | 0.0376 | 0.0850 | 0.1232 |
| hist | 0.7211 | 0.0181 | 0.0649 | 0.0886 | 0.1288 |
| temp | 0.7205 | 0.0442 | 0.0856 | 0.0958 | 0.1391 |
| none | 0.7153 | 0.0704 | 0.1319 | 0.0986 | 0.1509 |

Abstention policies (best sel per policy): points 0.8003 (Wrap Chain); arena3 0.7976 (Wrap Chain); never05 0.7975 (Wrap Chain); conformal alpha 0.2 0.7516; never 0.7509; confpts 0.7509; vaw 0.7446; noev 0.7336; noev+points 0.7318; mondpts 0.6671; mondrian 0.6125 (LR base). On a fixed LR C0.1 base (grid B2, corrected arena objective) every policy lands between 0.743 and 0.752 (noise).

Wrap on F2 Chain (inner `{"engine":"viterbi","eps_a":0.0005,"lam_scale":1,"mono":0.1,"pi_o":2,"vote_lr":48}`):

| calib / policy | sel | P80 pts / ECE / Brier | P10 pts (sd) / ECE / Brier | P10 false P/R |
|---|---|---|---|---|
| none / points | 0.8003 | 0.8334 / 0.014 / 0.070 | 0.7671 (0.010) / 0.040 / 0.094 | 0.769 / 0.511 |
| temp / arena3 | 0.7976 | 0.8318 / 0.014 / 0.070 | 0.7633 (0.012) / 0.037 / 0.091 | 0.790 / 0.474 |
| none / arena3 | 0.7976 | 0.8318 / 0.012 / 0.070 | 0.7633 (0.012) / 0.039 / 0.090 | 0.790 / 0.474 |
| none / never05 (= F2 standalone) | 0.7975 | 0.8313 / 0.013 / 0.070 | 0.7637 (0.016) / 0.041 / 0.094 | 0.790 / 0.475 |
| iso / never05 | 0.7958 | 0.8313 / 0.006 / 0.069 | 0.7603 (0.015) / 0.039 / 0.097 | 0.811 / 0.448 |
| va / arena3 | 0.7950 | 0.8271 / 0.011 / 0.070 | 0.7630 (0.012) / 0.041 / 0.094 | |
| platt / points | 0.7887 | 0.8324 / 0.015 / 0.070 | 0.7450 (0.038) / 0.045 / 0.099 | 0.719 / 0.400 |
| platt / never05 | 0.7735 | 0.8313 / 0.014 / 0.070 | 0.7158 (0.045) / 0.050 / 0.101 | 0.769 / 0.243 |

Best wrap of v9: va never05 with selftrain 1, sel 0.7525.

Paired per-fold test (`F3/paired.py`, reference Wrap none never05; 5 P80 folds, 10 P10 seeds):

| Config | P80 delta (se, wins) | P10 delta (se, wins) |
|---|---|---|
| Wrap none points | +0.0021 (0.0021, 1/5) | +0.0034 (0.0041, 3/10) |
| Wrap platt never05 | +0.0000 | -0.0479 (0.0150, 2/10) |
| LR chain-only fusion | -0.0084 (0.0027, 0/5) | -0.0209 (0.0058, 2/10) |

Why Platt hurts on the chain (console diagnostic on P10 seeds 0 to 2, not in a results file): 158, 217, 192 labelled rows with only 24, 23, 31 false rows; Platt slope 0.57, 0.36, 0.39 with bias +0.71, +1.02, +0.96 moves the false cutoff to a logit of about -1.2 to -2.8 and flips 120 to 152 of about 1700 test rows from false to true. Temperature has no bias term and never moves the 0.5 decision: the safe calibrator for a well-calibrated inner scorer.

Transfer vs refit at 10% labels (`ptransfer.jsonl`, practice only, page halves A and B, 6 splits): transfer plain 0.6014 (sd 0.104, ECE 0.149); transfer `tmask=1` 0.7006 (0.012, 0.028); `tmask=1, tmask_r=2` 0.7023 (0.018, 0.025); refit 0.6688 (0.017, 0.068). With Platt: 0.6079, 0.6998, 0.6733. `tmask` is validated on practice alone.

## 2. Suite tracks (tests only; points, ECE in brackets; never05 unless named)

A = LR chain-only fusion; D = LR base C0.1 platt; -tm = with `tmask=1`; W = Wrap on the chain.

| Track | A | A-tm | D | D-tm | W none never05 | W none points | W none arena3 | W temp arena3 |
|---|---|---|---|---|---|---|---|---|
| Sdev-jt | 0.9357 (.012) | 0.9346 (.009) | 0.6604 (.164) | 0.8412 (.032) | 0.9417 (.016) | 0.9417 (.016) | 0.9418 (.016) | 0.9418 (.017) |
| Sdev-jr | 0.9409 (.006) | - | 0.8825 (.011) | - | 0.9205 (.018) | 0.9422 (.009) | 0.9206 (.028) | 0.9205 (.028) |
| Sdev-nt | 0.9370 | 0.9367 | 0.6604 | 0.8360 | 0.9411 | 0.9411 | 0.9411 | 0.9411 |
| Sdev-nr | 0.9198 | - | 0.7283 | - | 0.9174 | 0.9175 | 0.9176 | 0.9176 |
| Ssealed-jt | 0.9372 (.013) | 0.9370 | 0.6644 | 0.8199 | 0.9414 (.015) | 0.9414 (.014) | 0.9414 (.015) | 0.9414 |
| Ssealed-jr | 0.9355 (.008) | - | 0.6751 | - | 0.9378 (.009) | 0.9343 (.009) | 0.9345 (.010) | 0.9346 |
| Ssealed-nt | 0.9410 | 0.9401 | 0.6639 | 0.8182 | 0.9443 | 0.9443 | 0.9448 | 0.9448 |
| Ssealed-nr | 0.8896 (.029) | - | 0.7084 | - | 0.9289 | 0.9289 | 0.9300 | 0.9298 |
| Scal-jt | 0.9387 | 0.9381 | 0.6470 | 0.8327 | 0.9437 | 0.9437 | 0.9439 | 0.9439 |
| Scal-jr | 0.8899 (.028) | - | 0.8431 | - | 0.9420 | 0.9407 | 0.9430 | 0.9429 |
| Scal-nt | 0.9410 | - | 0.6457 | - | 0.9458 | 0.9458 | - | - |
| Scal-nr | 0.7737 (.078) | - | 0.6976 | - | 0.9353 | 0.9376 | - | - |
| Ssyn-jt | 0.9350 | 0.9350 | 0.6711 | 0.8981 | 0.9370 | 0.9370 | 0.9371 | 0.9371 |
| Ssyn-jr | 0.9055 | - | 0.8244 | - | 0.9271 | 0.9351 | 0.9269 | 0.9269 |
| Ssyn-nt | 0.9375 | - | 0.6703 | - | 0.9405 | 0.9405 | - | - |
| Ssyn-nr | 0.9293 | - | 0.7404 | - | 0.9338 | 0.9342 | - | - |
| Sprac-jr / jt | 0.7628 / 0.7628 | - / 0.7597 | 0.6791 / 0.6791 | - / 0.7138 | 0.7597 / 0.7597 | 0.7597 / 0.7597 | - | - |
| Sdiag-jr / jt | -0.0368 / 0.0412 | - | -0.3332 / -0.2791 | - | -0.0173 / 0.0743 | 0.0431 / 0.0743 | - | - |
| Sextdev-jr / jt | -0.2455 / -0.2096 | - / -0.2156 | -0.2754 / -0.3473 | - / -0.2395 | -0.2874 / -0.2455 | -0.2874 / -0.2455 | - | - |
| Spilot-jr / jt | -0.1796 / -0.1796 | - | -0.2635 / -0.2635 | - | -0.1317 / -0.1317 | -0.1317 / -0.1317 | - | - |

## 3. What worked and what did not

Worked: wrapping F2's chain while leaving its own probabilities intact (calib none or temp); `tmask=1` for transfer on raw features (D Sdev-jt 0.660 -> 0.841; practice-only transfer 0.601 -> 0.701); cross-fitting the calibrator by page (removes V9's in-sample threshold optimism); VA and beta for the best ECE on raw LR scores.

Did not work: abstention of any kind (points threshold, conformal, Mondrian, VA width, no-evidence rule all equal to or below never05; Mondrian and the no-evidence rule cost points); model classes beyond LR (stacking and blending slower and not better); learned aggregators and row-level models; rmask, C auto, cscale, class weights, L1, onehot; a 2-parameter recalibration of an already calibrated scorer on few labels (Platt); learned LR fusion over the chain scores (significantly worse than the chain alone; it also collapses on Scal-nr 0.774 and Ssealed-nr 0.890, a test observation not used for selection).

## 4. Top 3

1. sel 0.8003, P80 0.8334 (ECE 0.014, Brier 0.070), P10 0.7671 (sd 0.010, ECE 0.040, Brier 0.094); Sdev-jt 0.9417, Sdev-jr 0.9422, Ssealed-jt 0.9414, Ssealed-jr 0.9343.
   `F3/fusion.py:Wrap {"inner":"F2/f2var.py:Chain","inner_params":{"engine":"viterbi","eps_a":0.0005,"lam_scale":1,"mono":0.1,"pi_o":2,"vote_lr":48},"calib":"none","policy":"points"}`
2. F2's chain unchanged (ranks 2 to 5 tied within 0.0003): sel 0.7975, P80 0.8313 (ECE 0.013), P10 0.7637 (sd 0.016, ECE 0.041); Sdev-jt 0.9417, Sdev-jr 0.9205, Ssealed-jt 0.9414, Ssealed-jr 0.9378.
   `F3/fusion.py:Wrap {"inner":"F2/f2var.py:Chain","inner_params":{same},"calib":"none","policy":"never05"}`
3. Best learned fusion: sel 0.7828, P80 0.8229 (ECE 0.013, Brier 0.072), P10 0.7428 (sd 0.009, ECE 0.038, Brier 0.101); Sdev-jt 0.9357, Sdev-jr 0.9409, Ssealed-jt 0.9372, Ssealed-jr 0.9355.
   `F3/fusion.py:Variant {"mp":{"C":0.1},"calib":"iso","policy":"never05","drop_features":[0,...,44],"extra_features":["F3/feats.py:chain_vit","F3/feats.py:chain_hmm"]}`

## 5. Exported plugins (`F3/plugins.py`)

- Calibrators via `calib:fit_calibrator` (platt, temp, beta, iso, hist, va), fitted on OOF scores, return `(p, width or None)`; one-class input gives a constant calibrator.
- `calib:Decider` (abstention): `fit(s_oof, y3, pages, noev)` then `decide(s, noev)` -> `(labels, conf in [0.5, 1] or NaN on unsure, p)`; calibrator cross-fitted by page; policy objective = arena points. Policies never05, never, points, conformal, mondrian, confpts, mondpts, vaw, noev, noev+points, arena3 (argmax{2P(t)-1, 2P(f)-1, P(u)}).
- `calib:wrap`: one-call array form for any scorer.
- `fusion:Wrap`: harness variant wrapping any variant spec; OOF row scores by re-running the inner variant with each labelled page fold hidden; one-class worlds fall back to practice.
- `fusion:Variant` (`fusion_lr`, Top #3); `feats:chain_vit`, `feats:chain_hmm` (chain score plus NaN flag); `fusion:no_evidence` (row flag).
- Recommendation for Phase 3: on a calibrated chain use calib "none" or "temp" with policy "never05" (or "points", non-significant +0.003); never "platt" at low label counts. On raw scorers use "va" or "beta" (best ECE) or "platt" (best P10 Brier) with never05 or arena3, plus `tmask=1` for transfer.
- `python -I F3/calib.py` prints "calib selfcheck ok".

## 6. Runtime (one 18,103-row suite world, Mac, one thread per job, 2 jobs)

Wrap: jt 1.1 to 1.2 s, jr 3.4 to 4.6 s (5 inner re-runs + final), 214 to 228 MB. A: jt 3.0 s, jr 5.0 s (max 6.2 s on Scal-jr), 274 to 291 MB. D: 2.5 s / 4.7 s, about 300 MB. Load 0.1 s. Every finalist under 10 s at 20k rows.

## 7. Harness requests

1. Per-fold and per-seed points in P80 and P10 result lines (`F3/paired.py` does it today).
2. A `remote.sh stop <tag>` command (F3-g1 was still running at 02:17; the orchestrator stopped it at 02:22).
3. An optional 2-CPU cgroup timing mode.

## 8. Suspicious items and caveats

- No gold-label path found in F3 code; Wrap and tmask use only labelled rows; hidden rows carry `label=None`.
- One in-sample optimism, not a leak: in `feats.py` the F2 hazard for a labelled training row's chain feature is fitted with that row's own label visible (own page's evidence excluded); test rows unaffected.
- Mixed code versions in g1: results before the points fix used the old objective (points, confpts, vaw rows); never05 and never unaffected; src_hash separates versions; grid B2 reran those policies locally with the fix.
- P10 has only 23 to 31 false labels per seed: any policy or calibrator with 2 or more parameters is dominated by noise; seed sd 0.01 to 0.016, ranks 1 to 7 statistically tied.
- Sdiag, Sextdev, Spilot negative for every config, F2's chain included.
- On jr tracks W points vs never05 is mixed (Sdev-jr +0.022, Ssyn-jr +0.008, Ssealed-jr -0.0035): test-only observation.
- F4's and F7's plugins were not integrated.
