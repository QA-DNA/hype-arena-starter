# F1 report: truth discovery and source reliability

Saved by the orchestrator from F1's final message (02:17). Plugins final in `F1/plugins.py`.

## Summary

- Winner: a per-key dynamic-world lifespan HMM over page claims, F1-D1: P80 0.8334 / P10 0.7712 points per row, selection 0.8023 (v9 arena 0.809 / 0.674; F2 early HMM 0.814 / 0.736).
- Classic truth discovery (Accu, CRH, TruthFinder, Dawid-Skene, LTM, Sums) lands between 0.72 and 0.76 selection, all below the HMM and below the bar on P80.
- Exact-duplicate dedup (F1-D2) costs almost nothing on practice (P10 0.7702) and is the only setting that survives a copied-lie attack (P10 hlie 0.7693 vs 0.6454 for D1).
- Five plugins, 2 to 16 columns, label-safe (out-of-fold for labelled facts), checked by `F1/check_oof.py`.
- Practice is sparse (about 291 pages, about 4 observations per key), the suite dense (about 40). Every choice made on practice only.

## 1. Method and protocol

- Observations: each fact is a claim by its row's page; other-page claims of the same typed key (`world.obs_typed`) are evidence, weighted by `exp(-|dt|/tau)` with optional future factor `beta` and window `win`. Consistency `cons` = interval overlap, `cont` = containment, `same` = equal canonical value.
- Labelled rows: a true row is a hard anchor (clamped to 1); a single-fact false row clamped to 0 (negative evidence); a multi-fact false row spreads blame by noisy-OR. Unlabelled rows latent. Row score = product of fact posteriors (or min with `row=min`).
- Wrapper `F1/f1var.py:Variant`: OOF row scores from inner GroupKFold(5) by labelled page (the scored fold's labels hidden); isotonic calibration on true and false OOF rows; (threshold, unsure band) chosen on OOF rows with the exact arena rule (`select='arena'`), thresholds 0.30 to 0.70 step 0.05, bands {0, 0.02, 0.05, 0.10, 0.15}. Confidence `max(p, 0.5)` for true, `max(1-p, 0.5)` for false; unsure NaN. One-class or fewer than 10 training labels fall back to the raw posterior with t = 0.5 and no band (Sprac-*r, Spilot-*r).
- Leakage check: `F1/check_oof.py` flips one labelled page's labels and asserts the OOF scores and plugin columns of that page are bit-identical: "oof self-check ok: page 1 rows 9". The world view carries no gold.

## 2. Variants and parameter sets tried

Stage 1 remote: 1938 jobs, 1752 ok (186 failures: vote `anchors='hard'`, a since-fixed shadowing bug, rerun in stage 2). Stage 1 thresholds used the older inner rule (`select='points'`); harness metrics were always the true scorer. Stage 2 (392 jobs, remote) and all local runs use `select='arena'`.

| Family | Grid |
|---|---|
| vote | anchors soft/hard/off; wu {0,1}; wa {1,3}; wneg {0,1,2}; wmf; tau {none,7,15,30,60}; win {none,7,30,90}; beta {0,0.5,1}; sup overlap/contain; prior; dedup |
| truthfinder | t0 {0.8,0.9}; gamma {0.3,1}; rho {0.3,1}; rho_partial; sup; tau {none,15,30,60}; beta; ta {0.99,0.9999}; wneg {0.5,2}; selfw 0; dedup; beta 0.5; row min |
| crh | tau {7,15,30,60}; wa {1,2,5}; agg mean/median; numeric {F,T}; iters; dedup; beta 0.5; row min; iters 30 |
| ds (Dawid-Skene) | sources = pages or k-means page clusters k {6,12,24}; items = (key, segment) bound fixed / anchor; seg_w {7,15,30}; a1/a0 Beta priors; pi0; anchor_acc {0.9,0.99,0.995}; dedup; row min; pi0 0.8 |
| ltm | as ds with two-sided quality, collapsed Gibbs; burn/samples {20/40, 50/100} |
| accu / AccuCopy | A0; Aa; nfalse {5,10,30}; alpha {1,3,10}; tau {15,30,60}; beta {0.5,1}; selfw {0,1}; copy=True (c {0.5,0.8} x calpha {0.05,0.2}, wcopy 30); liar mixture; DynaTD-style dyna [k {3,10} x h {15,45}]; dedup; sup contain + rho_partial 0.5; softmax off; row min; platt; inner 10 |
| slimfast | best accu + page-feature logistic prior; C {0.1,0.5} x lam_u {0.1,0.3,1.0} |
| sums / avglog | tau; wa; wneg; iters; dedup |
| dynworld (HMM) | lam {30,60,90,120,180}; F0 {0.01,0.03,0.08}; back {0.001,0.005,0.02}; E0 {0.85,0.95}; Ea {0.995,0.999}; selfx {T,F}; iters {4,8}; alpha {1,3,10}; order median/min; precise; lam_em; slimE 0.5; dedup; row min; calib platt; select bayes; inner 10 |
| blend | dynworld + accu, logit and mean |

## 3. Results on practice (selection, arena rule)

Columns: points / acc / ECE10 / false precision / false recall.

| Config | P80 | P10 | sel |
|---|---|---|---|
| **D1 dynworld** lam 120, F0 0.03, back 0.005 | 0.8334 / 0.917 / 0.028 / 0.903 / 0.635 | 0.7712 / 0.886 / 0.048 / 0.855 / 0.467 (seed std 0.0093) | **0.8023** |
| **D2** = D1 + dedup | 0.8334 / 0.917 / 0.028 / 0.903 / 0.635 | 0.7702 / 0.885 / 0.047 / 0.853 / 0.462 (std 0.0083) | 0.8018 |
| dynworld F0 0.01, back 0.001 | | | 0.8022 |
| dynworld back 0.001 | | | 0.8021 |
| **C3 crh** row min | 0.7902 / 0.895 / 0.025 / 0.854 / 0.505 | 0.7265 / 0.863 / 0.060 / 0.770 / 0.360 (std 0.0156) | 0.7584 |
| slimfast C 0.1, lam_u 1.0 | 0.7733 | 0.7390 | 0.7561 |
| accu (alpha 10, nfalse 30, tau 30) | 0.7775 | 0.7337 | 0.7556 |
| truthfinder ta 0.99 | | | 0.7463 |
| vote dedup (soft, tau 15, beta 0.5, wa 3) | | | 0.7449 |
| ds row min | | | 0.7382 |
| ltm pi0 0.8 | | | 0.7370 |
| sums | | | 0.7245 |
| avglog | | | 0.7235 |
| unweighted vote (stage 1) | | | about 0.66 (always-true level) |

Dynworld extensions on the lam 90 base, all worse: row min 0.8006, select bayes 0.8004, alpha 1 or 10 and inner 10 (0.8000 to 0.8010); lam_em 0.7984, slimE 0.5 0.7979, dedup 0.7972, platt 0.7970; iters 8 0.7944, selfx False 0.7916, E0 0.95 0.7912, precise 0.7799, order min 0.7793. Blends of dynworld and accu: logit 0.7887, mean 0.7629.

## 4. Suite tests (test only)

| Track | D1 | D2 | C3 crh |
|---|---|---|---|
| Sdev-jt | **0.9396** (ECE 0.014) | 0.9302 (0.014) | 0.8595 (0.065) |
| Sdev-jr | **0.9310** (ECE 0.024) | 0.9260 (0.021) | 0.8706 (0.036) |
| Sdev-nt / nr | 0.9350 / 0.9365 | 0.9260 / 0.9108 | 0.8320 / 0.8505 |
| Ssealed-jt | **0.9407** (ECE 0.015) | 0.9327 (0.014) | 0.8404 (0.062) |
| Ssealed-jr | **0.9430** (ECE 0.020) | 0.9341 (0.024) | 0.8431 (0.042) |
| Ssealed-nt / nr | 0.9407 / 0.9388 | 0.9287 / 0.9276 | 0.8268 / 0.8384 |
| Scal-jt / jr | 0.9409 / 0.9414 | 0.9370 / 0.9344 | 0.8556 / 0.8689 |
| Ssyn-jt / jr | 0.9360 / 0.9367 | 0.9275 / 0.9279 | 0.9265 / 0.9265 |
| Sprac-jt / jr | 0.7660 / 0.6016 | 0.7628 / 0.5794 | 0.7170 / 0.6980 |
| Sdiag-jt / jr | -0.0461 / -0.3337 | -0.0500 / -0.3337 | -0.0719 / -0.3337 |
| Spilot-jt / jr | -0.2515 / -0.1916 | -0.2575 / -0.1916 | -0.2874 / -0.2754 |
| Sextdev-jt / jr | -0.1916 / -0.2515 | -0.1916 / -0.2575 | -0.2455 / -0.3054 |
| Sextcal-jt / jr | -0.1078 / -0.1078 | -0.1138 / -0.1257 | -0.0958 / -0.1916 |
| Sextsealed-jt / jr | -0.2036 / -0.0838 | -0.2036 / -0.1916 | -0.2455 / -0.3293 |
| Xdev-jt / jr | 0.9384 / 0.9297 | 0.9292 / 0.9250 | 0.8583 / 0.8700 |
| Xsealed-jt / jr | 0.9346 / 0.9370 | 0.9253 / 0.9267 | 0.8335 / 0.8384 |
| Xcal-jt / jr | 0.9392 / 0.9398 | 0.9347 / 0.9314 | not run |
| Xsyn-jt / jr | 0.9311 / 0.9312 | 0.9219 / 0.9228 | not run |
| Xprac-jt / jr | 0.7676 / 0.6063 | 0.7613 / 0.5826 | not run |
| Xdiag-jt | -0.0475 | -0.0509 | not run |

D1 and D2 ran all 80 S/X tracks (`results/F1.jsonl`). X within about 0.01 of S everywhere. References: v9 transfer Sdev-jt 0.664, v9 refit Sdev-jr 0.876, best v9/v12 transfer 0.829; on balanced-target worlds always-true scores about -0.33; the A interval engine scores 0.344 on Sdiag-jt.

## 5. Copied-lie stress test (P10, `F1/stress.py`, `results/F1-stress.jsonl`)

hlie: every hidden false row gets 3 unlabelled verbatim copies on new pages dated +1, +7, +30 days. hctrl: as many hidden true rows copied the same way (seed 12345 + seed).

| Config | clean | hlie | hctrl |
|---|---|---|---|
| D1 | 0.7712 | **0.6454** (false recall 0.012) | 0.7841 |
| D2 (dedup) | 0.7702 | **0.7693** | 0.7700 |
| accu | 0.7140 | 0.6535 | |
| accu copy=True | | 0.6613 (false recall 0.007) | |
| accu dedup, vote dedup | | equal to clean | |

AccuCopy gives no protection: it detects copying only on values it already believes false, and a single-row copy page shares exactly one value with its source. Exact-text dedup (a copy never supports its original; duplicates dropped from the lifespan medians) is the working defence.

## 6. What worked, what did not, and why

- Worked: modelling the world as changing. The HMM orders a key's distinct values by the median date of their claims, uses `exp(-gap/lam)` to stay on the current value, and separates an outdated value (freshness lapse F) from a plainly false one (1 - E). Near-hard anchors (Ea 0.999) and dividing out each claim's own emission (selfx; off costs about 0.009) both matter.
- Worked: long lifespan (lam 120), rare backward moves (0.005), small staleness (F0 0.03). EM on per-page E and F with a Beta prior beats a SLiMFast-style feature prior (slimE) and learned lam (lam_em).
- Worked: time kernels for static methods (TruthFinder 0.656 without time, 0.745 with tau 15). Unweighted vote at the always-true level.
- Did not work: page-reliability machinery on sparse data (Accu and SLiMFast page accuracies mostly the prior; liar, dyna, softmax-off, contain, platt at or below plain Accu; Dawid-Skene and LTM plateau at 0.737; Sums and AverageLog uncalibrated and worst).
- Did not work: blending the HMM with Accu (logit 0.7887 vs 0.8023): errors not complementary.
- Did not work: `precise=True` and `order=min` (0.78); order by median is robust to stray early claims.
- Negative everywhere for every TD method: balanced-target worlds (diag, pilot, ext*), about a third unsure targets; truth discovery has no answerability model.
- Skipped with reasons: Investment / PooledInvestment (Sums family, already worst); 2-Estimates, 3-Estimates, GLAD (difficulty parameters unidentifiable at about 4 observations per key); GTM, KDEm, CATD (continuous noise models); MACE (covered by the liar mixture); Pal et al. (heavy, unjustified at this density); Snorkel-style label models (supervised calibration wins); Yin and Tan semi-supervised TD (anchors already clamped); full KBT (no extractor confidence; HMM's E covers page trust).

## 7. Top 3 (exact)

1. **F1-D1** `F1/f1var.py:Variant` `{"method":"dynworld","select":"arena","lam":120.0,"F0":0.03,"back":0.005,"E0":0.85,"Ea":0.999}`: P80 0.8334 (ECE 0.028), P10 0.7712 (ECE 0.048, std 0.0093); Sdev-jt 0.9396, Sdev-jr 0.9310, Ssealed-jt 0.9407, Ssealed-jr 0.9430.
2. **F1-D2** (copy-robust) same + `"dedup":true`: P80 0.8334, P10 0.7702 (std 0.0083); Sdev-jt 0.9302, Sdev-jr 0.9260, Ssealed-jt 0.9327, Ssealed-jr 0.9341; hlie 0.7693 vs 0.6454.
3. **F1-C3** (best non-HMM) `{"method":"crh","select":"arena","tau":15.0,"wa":2.0,"agg":"mean","numeric":false,"row":"min"}`: P80 0.7902, P10 0.7265 (std 0.0156); Sdev-jt 0.8595, Sdev-jr 0.8706, Ssealed-jt 0.8404, Ssealed-jr 0.8431.

F1's recommendation: D1 and D2 are 0.001 apart on P10 (seed std 0.009); D2 removes a 0.125-point failure mode under copying, so take D2 (or `td_post` with dedup inside the HMM) for the combination phase.

## 8. Plugins (`F1/plugins.py`, verified through `api.feature_block`)

Labelled facts take values from the inner hidden-fold run; results cached per (world, labelled mask).

| Name | k | Columns |
|---|---|---|
| td_post | 2 | dynworld HMM posterior (D1 settings), Accu-copy temporal posterior |
| page_rel | 3 | Accu page accuracy without the row, dynworld page exactness E, log1p page size |
| indep_support | 4 | log1p distinct supporting pages, distinct contradicting pages (30 d), copy-adjusted support, copy-adjusted contradiction |
| copy_margin | 3 | copy-adjusted kernel vote margin (tau 30), unadjusted margin, mean independence of supporters |
| td_all | 16 | all 12 above plus TruthFinder confidence, CRH score, Dawid-Skene posterior, LTM posterior |

Plugins use D1 settings without dedup (adding dedup is a one-line change to the `DYN` dict; not changed after the 02:30 freeze).

## 9. Runtime per 20,000-row world (Mac, one process)

Graph build (3.9M edges, cached) 0.1 s; vote 0.1 s; truthfinder 0.7 s; crh 0.6 s; ds / ltm 0.1 s; dynworld 0.8 s; accu 1.6 s; accu-copy 7.1 s; slimfast 7.0 s. D1 refit (5 inner + 1 full HMM run) about 6.4 s at about 410 MB RSS; transfer predict about 2 s. `td_all` computes every method 6 times, about 1 min; peak RSS about 1.2 GB. Fits the box.

## 10. Harness requests and suspicious items

- Include imported helpers in `src_hash` (only `f1var.py` is hashed; logic lives in `td.py`).
- A `td.py` edit landed during local s2a (dynworld single-state shortcut, affects keys with negative claims and a single value); all finals ran after the edit.
- Stage 1 used the older inner unsure rule; stage 2 and all finals use `arena`.
- TD methods ignore `world.interval`, so -n and -j differ only through the facts.
- One-class refits fall back to the raw posterior with t = 0.5, hence Sprac-jr 0.6016 below Sprac-jt 0.7660.
- Practice about 4 observations per key, suite about 40, so the suite runs about 0.17 higher; dense-favoured methods (Ssyn CRH 0.9265) lost on practice and practice decided.
- No leakage path found in the harness.

## Files

`F1/td.py`, `F1/f1var.py`, `F1/plugins.py`, `F1/stress.py`, `F1/check_oof.py`; results `results/F1.jsonl`, `results/F1-remote.jsonl`, `results/F1-stress.jsonl`.
