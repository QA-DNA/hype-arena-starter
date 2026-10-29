# F2 (temporal resolution): final report

Saved by the orchestrator from F2's final message (02:12). Plugins final in `F2/plugins.py`.

A per-key temporal chain clearly beats v9. Top config: selection 0.8085 (mean of P80 and P10) vs 0.7416 for v9 `select=arena`. Parameters chosen on P80 and P10 only; suite and X numbers are tests.

## Top 3 (exact)

All use defaults eps_f=0.2, wm=0, lam_by="kind", lam_scale=1, fmap="iso", rcal="iso", agg="prod" and the arena rule.

| # | Config | Sel | P80 | P10 | Sdev-jt / jr | Ssealed-jt / jr |
|---|---|---|---|---|---|---|
| 1 | `F2/f2var.py:Chain` `{"engine":"viterbi","d0":0.03,"eps_a":0.0005,"mono":"fit","mono_a":10,"pi_o":1,"vote_lr":48}` | 0.8085 | 0.8492 | 0.7678 | 0.9419 / 0.9148 | 0.9406 / 0.9226 |
| 2 | `F2/f2var.py:Chain` `{"engine":"hmm","d0":0.1,"eps_a":0.0001,"mono":"fit","mono_a":3,"pi_o":1,"vote_lr":48}` | 0.8069 | 0.8482 | 0.7656 | 0.9422 / 0.9158 | 0.9401 / 0.9302 |
| 3 | `F2/f2var.py:Chain` `{"engine":"viterbi","eps_a":0.0005,"lam_scale":1,"mono":0.1,"pi_o":2,"vote_lr":48}` | 0.7976 | 0.8318 | 0.7634 | 0.9418 / 0.9210 | 0.9414 / 0.9379 |

- #1 learned downward-switch weights on practice: quantity 0.027, version 0.01, date 0.012, percent 0.167, money 0.518, duration 0.978 (boolean, name unordered, unused).
- #2 is a true forward-backward posterior; best Ssealed-jr ECE (0.0023).
- #3 fixed monotone weight, no learned prior; most robust on refit tracks.
- Plateau: places 3 to 12 on pure selection are mono-fit neighbours of #1 and #2 (0.8055 to 0.8084), not run on the suite; gaps under the P10 seed std of 0.012. #3 is the best distinct config with suite numbers. Best of other engines: TeCoRe `{"engine":"tecore","C":2,"C_o":0.5,"mono_pen":2,"w_v":4}` 0.7720; BracketHMM `{"alpha":4,"backoff":"hmm","nb":20}` 0.7748.

## 1. Variants and parameter sets tried

1305 configs scored on P80 and P10, grids g1, g2, g34, g5, g6 plus X test grid g6x (`F2/grids.py`; results `results/F2-remote.jsonl`). Shared pipeline (`Std`): fact score, FactMap (isotonic on labelled facts; no other-page evidence gets a smoothed rate), product per row, RowCal (row isotonic), exact arena rule (u = labelled unsure rate; P(true)=(1-u)pc, P(false)=(1-u)(1-pc), P(unsure)=u; argmax of {2P(true)-1, 2P(false)-1, P(unsure)}; conf = max(0.5, ...)). One-class refit falls back to the all-practice fit.

1. Point resolvers (`Point`): latest, nearest, bracket, kernel; kernels exp, tri, box; tau 7/30/90/365; beta 0.25/0.5/1; wu 0.05 to 1; wf; wa. 124 configs.
2. Bracket lookup tables (`Bracket`): before/same/after cells (Y/N anchor agrees/disagrees, y/n votes only, - nothing), Beta-smoothed, inner 5-fold OOF; vote_fallback T/F, gapb 0/14/60/180, alpha 1/4/16. 27 configs.
3. TeCoRe (`Chain engine=tecore`): max-product timeline (anchor disagreement -H=50, agreeing with a false anchor -H, agreeing vote +w_v, switch -C, move to "other" -C_o, downward switch mono_pen); score = margin of best agreeing over best disagreeing timeline. w_v 0.25 to 8, C 0.5 to 8, C_o 0.5/2/5, mono_pen 0 to 4. 148 configs.
4. Change-point segmentation (`Chain engine=seg`): exact DP, penalty c log n, HMM emissions; c 0.1 to 4, vote_lr 2/4/8, plus a penalty sweep {0.25..4} posterior. 18 configs.
5. Per-key HMM and Viterbi (`Chain engine=hmm|viterbi`): states = distinct canonical values plus "other"; T(g) = e^(-lg) I + (1 - e^(-lg)) W, l by MLE per kind on consecutive true-anchor pairs. Emissions: true anchor log(eps_a + (1-eps_a)A); single-fact false row log(1 - (1-eps_f)A); multi-fact false row weight wm; vote likelihood ratio vote_lr. Exact leave-own-page-out from one forward-backward (or max-product) pass, brute-force checked in `test_f2.py` ("619 leave-page-out posteriors, 1020 max-marginals checked"). Knobs: g1 vote_lr 1.5 to 12, eps_a 0.002 to 0.1, lam_scale 0.5 to 2, pi_o 0.1 to 2, eps_f, wm, lam_by global/kind/token/attr, fixed l, platt, agg min; g2/g4 vote_lr 12 to 200, eps_a 0.0001 to 0.002, mono 1 to 0.01; g5 mono=fit (per-kind downward-switch weight, Beta prior strength mono_a 3/10/30, prior mean d0 0.03/0.1/0.3), mono_all fixed. About 950 configs.
6. Staleness hazard and premature analysis: `analysis.py` -> `analysis.txt`; exported as `f2_stale`.
7. In-family combinations: `Combo` (LR over F2 blocks, GroupKFold OOF; C 0.1/0.3/1; 16 configs), `BracketHMM` (bracket table with HMM-bin or cell backoff; nb 5/10/20, alpha 1/4; 19 configs), v9 with F2 `extra_features` (9 configs).

## 2. Results

### Selection tracks (P10 mean +- std over 10 seeds; P80 pooled)

| Config | Sel | P80 pts | P80 acc | P80 ECE | P80 fP/fR | P10 pts | P10 acc | P10 ECE | P10 fP/fR |
|---|---|---|---|---|---|---|---|---|---|
| A viterbi mono-fit | **0.8085** | 0.8492 | 0.9241 | 0.0106 | 0.87/0.73 | 0.7678+-.012 | 0.8794 | 0.0365 | 0.81/0.48 |
| B hmm mono-fit | 0.8069 | 0.8482 | 0.9215 | 0.0105 | 0.87/0.72 | 0.7656+-.012 | 0.8781 | 0.0348 | 0.81/0.48 |
| D viterbi mono 0.1 | 0.7976 | 0.8318 | 0.9151 | 0.0129 | 0.83/0.70 | 0.7634+-.012 | 0.8710 | 0.0386 | 0.79/0.47 |
| BracketHMM a4 nb20 | 0.7748 | 0.8440 | 0.9220 | 0.0061 | 0.84/0.74 | 0.7057+-.038 | 0.8491 | 0.0514 | 0.48/0.34 |
| E hmm no-mono (g1 best) | 0.7736 | 0.8134 | 0.9056 | 0.0133 | 0.84/0.61 | 0.7338 | 0.8628 | 0.0390 | 0.80/0.37 |
| C tecore | 0.7720 | 0.7976 | 0.8988 | 0.0091 | 0.80/0.59 | 0.7464+-.009 | 0.8705 | 0.0394 | 0.69/0.50 |
| Combo hmm+viterbi C1 | 0.7679 | 0.8266 | 0.9104 | 0.0118 | 0.82/0.70 | 0.7091+-.021 | 0.8482 | 0.0432 | 0.70/0.28 |
| v9 + f2_all | 0.7441 | 0.8060 | 0.9014 | 0.0237 | 0.79/0.64 | 0.6821 | 0.8410 | 0.0560 | 0.57/0.24 |
| v9 select=arena (bar) | 0.7416 | 0.8092 | | | | 0.6739 | | | |
| v9 + f2_core | 0.7397 | 0.8060 | 0.9030 | 0.0292 | 0.81/0.62 | 0.6733 | 0.8253 | 0.0607 | 0.58/0.26 |
| F Point box tau7 | 0.7162 | 0.7596 | 0.8798 | 0.0145 | 0.81/0.41 | 0.6728 | 0.8344 | 0.0397 | 0.44/0.12 |
| H seg c1 | 0.7158 | 0.7296 | 0.8524 | 0.0186 | 0.68/0.38 | 0.7020 | 0.8387 | 0.0435 | 0.77/0.21 |
| G Bracket gapb14 | 0.7142 | 0.7654 | 0.8809 | 0.0090 | 0.88/0.39 | 0.6631 | 0.8315 | 0.0518 | 0.08/0.00 |

Other best-of-grid: g2 tecore C1 w_v2 0.7709; seg sweep P80 0.648; anchors only (vote_lr 1) about 0.737; v9 + f2_all with old f2feat defaults 0.7500.

### Suite tracks (TEST only, points per row)

| Config, mode | dev | cal | sealed | diag | syn | pilot | prac | extdev | extcal | extsealed |
|---|---|---|---|---|---|---|---|---|---|---|
| A jt | .942 | .944 | .941 | .086 | .938 | -.165 | .717 | -.254 | -.078 | -.204 |
| A jr | .915 | .940 | .923 | -.062 | .937 | -.165 | .717 | -.204 | -.093 | -.198 |
| A nt | .942 | .944 | .944 | .080 | .940 | -.180 | .691 | -.231 | -.072 | -.225 |
| A nr | .915 | .927 | .930 | -.060 | .923 | -.180 | .691 | -.228 | -.084 | -.237 |
| B jt | .942 | .943 | .940 | .044 | .938 | -.329 | .723 | -.228 | -.102 | -.192 |
| B jr | .916 | .938 | .930 | -.120 | .935 | -.329 | .723 | -.228 | -.114 | -.180 |
| B nt | .942 | .944 | .944 | .044 | .939 | -.341 | .692 | -.216 | -.078 | -.204 |
| B nr | .917 | .932 | .929 | -.207 | .925 | -.341 | .692 | -.228 | -.105 | -.198 |
| D jt | .942 | .944 | .941 | .078 | .937 | -.132 | .760 | -.246 | -.096 | -.207 |
| D jr | .921 | .943 | .938 | -.007 | .927 | -.132 | .760 | -.138 | -.024 | -.174 |
| D nt | .941 | .946 | .945 | .075 | .940 | -.138 | .724 | -.216 | -.090 | -.213 |
| D nr | .918 | .935 | .930 | -.028 | .934 | -.138 | .724 | -.269 | -.021 | -.275 |
| C jt | .906 | .908 | .903 | .045 | .897 | -.177 | .650 | -.251 | -.147 | -.249 |
| C jr | .906 | .917 | .903 | -.082 | .897 | -.177 | .650 | -.251 | -.114 | -.036 |
| E jt / jr | .944/.932 | .945/.945 | .942/.926 | .026/-.063 | .939/.940 | -.323 | .779 | -.240/-.246 | -.084/-.042 | -.210/-.135 |
| H seg jt / jr | .942/.940 | .943/.944 | .940/.939 | .059/-.334 | .937/.938 | -.180 | .709 | -.246/-.195 | -.090/-.096 | -.216/-.237 |
| K BracketHMM jt / jr | .936/.936 | .938/.938 | .936/.936 | .006/.002 | .936/.937 | -.281 | .778 | -.201/-.210 | -.078/-.090 | -.198/-.165 |
| I Combo jt / jr | .711/.916 | .711/.936 | .704/.931 | -.150/-.006 | .699/.936 | -.177 | .730 | -.317/-.213 | -.320/-.084 | -.296/-.111 |
| F Point jt / jr | .824/.798 | .825/.797 | .812/.798 | -.136/-.334 | .803/.808 | -.275 | .711 | -.251/-.222 | -.078/-.123 | -.213/-.186 |
| G Bracket jt / jr | .827/.682 | .849/.689 | .828/.702 | -.013/-.309 | .838/.729 | -.329 | .647 | -.251/-.299 | -.132/-.141 | -.210/-.263 |
| v9+all jt / jr | .605/.928 | .631/.744 | .655/.856 | -.265/-.228 | .697/.788 | -.216/FAIL | .657/FAIL | -.353/-.287 | -.347/-.341 | -.257/-.198 |
| v9+core jt / jr | .667/.924 | .665/.814 | .668/.779 | -.315/-.217 | .667/.872 | -.246/FAIL | .692/FAIL | -.335/-.275 | -.335/-.311 | -.329/-.210 |

Pilot and prac: jt = jr because those refit worlds are one-class and fall back to the practice fit.

| | Sdev-jt | Sdev-jr | Ssealed-jt | Ssealed-jr |
|---|---|---|---|---|
| A acc / ECE | .9707 / .0163 | .9571 / .0132 | .9699 / .0157 | .9612 / .0135 |
| A false P/R | .95/.95 | .97/.85 | .95/.95 | .97/.88 |
| B acc / ECE | .9711 / .0145 | .9579 / .0237 | .9701 / .0143 | .9617 / .0023 |
| D acc / ECE | .9707 / .0156 | .9602 / .0182 | .9704 / .0145 | .9689 / .0090 |

X tracks (extractor B, TEST, A, B, C over 40 tracks): every world within about 0.01 of its S counterpart (A: Xsealed-jt 0.933 vs 0.941, Xdev-jt 0.941 vs 0.942). The chains are not sensitive to the extractor.

## 4. What worked, what did not, and why

Worked:
- A consistent per-key timeline with exact leave-own-page-out: +0.067 selection over v9, +0.094 on P10.
- Strong votes (vote_lr 48) and near-hard anchors (eps_a 0.0001 to 0.0005): base rate about 0.89 true, so an unlabelled fact on another page at a nearby date is strong evidence; vote_lr 12 -> 48 is most of the step from g1 (0.775) to g2 (0.798).
- Learned monotone prior: +0.011 selection over fixed mono 0.1 (P80 0.8318 -> 0.8492). On practice anchors quantity goes up 148 times and down 4; version 28 up, 0 down; date 14 up, 0 down; money (14 up, 12 down) and duration (9 up, 18 down) are not monotone.
- Hazard l per kind by MLE (beat global, per-token, per-attribute and fixed l): version 0.0131/day, percent 0.0081, quantity 0.0074, duration 0.0050, money and boolean 0.0044, date 0.0038, name 0.0026. Empirical P(same | gap): 0.969 at 1 to 7 days, 0.840 at 8 to 30, 0.718 at 31 to 90, 0.470 at 91 to 180.
- An "other" state (pi_o 1) absorbs lone outlier values.
- Premature-value analysis (full labels, own page excluded): true rate NY 0.930, YN 0.890, NN 0.324, YY 1.000; NY last third 0.987 vs first third 0.739; YN with gap_after <= 14 days 0.536. HMM posterior AUC within pattern on P80 hidden facts: NY 0.884, YN 0.832, NN 0.914, all 0.948, so explicit stale and premature flags add little to the chain.

Did not work:
- Point resolvers (0.716) and bracket tables (0.714): no global consistency; Bracket P10 false recall 0.00.
- seg (0.716): hard penalty discards uncertainty; sweep posterior too coarse (P80 0.648).
- TeCoRe (0.772): additive hard weights; about 0.035 below Viterbi on the dense suite too.
- Learned combinations (Combo 0.764 to 0.768, BracketHMM 0.765 to 0.775, v9 + F2 features 0.740 to 0.750): overfit P10 (BracketHMM P10 std 0.038) and collapse on transfer (weights learned on sparse practice, about 4 observations per key, do not hold on dense suites, about 40). The standalone chains transfer because only a monotone isotonic map sits on top of a posterior.
- Small ablations: wm > 0 hurt; Platt worse than isotonic; agg=min worse than product; mono_all neutral; eps_f other than 0.2 worse.
- Anchors only (vote_lr 1): about 0.737; P10 drops to the always-true level.

## 5. Exported plugins (`F2/plugins.py`, refs `F2/f2feat.py:<func>`)

Each returns an (n_facts x k) finite array, always excludes the own page, reads labels only from labelled rows. Defaults = selected config (eps_a 0.0005, vote_lr 48, pi_o 1, mono fit). All eight checked for shape and finite values on P10 fold 0.

- `f2_hmm` (3): HMM posterior that the state at the fact's date agrees; P("other"); no-other-page-evidence flag.
- `f2_viterbi` (12): max-marginal margin; segment age and time remaining (log days); gap to previous and next change point; segment support (agreeing anchors, agreeing votes, votes against); stale flag; premature flag; agrees with MAP value; distance to nearest change point.
- `f2_tecore` (1): TeCoRe consistent-timeline margin.
- `f2_seg` (1): share of the penalty sweep agreeing at the date.
- `f2_stale` (6): hazard survival exp(-l_kind g) to latest agreeing observation before, earliest agreeing after, latest agreeing anchor before, latest disagreeing anchor before; anchor stale and premature flags.
- `f2_bracket` (15): one-hot before/same/after cell.
- `f2_core` (10): HMM post and P(other), Viterbi margin, change-point distance, segment support from anchors and votes, stale, premature, staleness back and forward.
- `f2_all` (23): hmm + viterbi + tecore + seg + stale.

Cost: f2_all about 2.5 s on a 20k-row world (Mac), about 0.3 s on a P10 fold. Caveat: absolute-scale features did not transfer from practice to dense suites inside v9; prefer refit tracks or relative use.

## 6. Runtime per 20,000-row world (box, OMP_NUM_THREADS=1, dev/cal/sealed/syn, 8 to 16 runs per config)

| Config | transfer | refit | Peak RSS |
|---|---|---|---|
| A viterbi | max 4.0 s | max 5.6 s | <= 197 MB |
| B hmm | max 3.2 s | max 4.8 s | <= 196 MB |
| C tecore | max 4.1 s | max 5.9 s | <= 196 MB |
| Combo | max 6.6 s | | <= 197 MB |
| v9 + f2_all | 27.4 s | | 242 MB |

Loading <= 1 s, not included. Sdev: 24,434 facts, 514 keys, at most 1045 observations per key, at most 17 values. Fits 2 CPU / 6 GiB / 30 min with more than 300x margin on time and about 30x on memory.

## 7. Suspicious items

1. Hard worlds are a label-prior shift, not a temporal failure. Target gold: diag 1367 true, 1368 false, 1368 unsure; pilot 278 / 111 / 111 of 500; extdev 240 / 139 / 121. Practice has 1.4% unsure; diag's labelled rows are 1715 true, 139 false, 43 unsure. On Sdiag-jt the chain predicts unsure on 30 of 4103 targets. Nothing selected on practice can learn this; every family is negative there.
2. seg on Sdiag-jr collapses to all-true (-0.334): the refit calibrator on diag's labelled rows (90% true) maps seg's coarse score above threshold everywhere. Finer chain scores avoid it (A -0.062).
3. Transfer collapse of learned layers: Combo Sdev-jt 0.711 vs jr 0.916; v9 + F2 features jt 0.605 to 0.667; standalone chains about 0.94 on both.
4. Selection optimism: 1305 configs, 104 at >= 0.80. #1 and #2 differ by 0.0016, far under the P10 seed std of 0.012. Treat the mono-fit chain family as one choice.
5. Refit can be worse than transfer for the chains (A: Sdev-jr 0.915 vs jt 0.942): practice fits a better FactMap and RowCal than a suite world's labelled rows.
6. Pilot and prac refit are one-class; F2 falls back, v9 crashes (8 failed jobs in g6, all v9).
7. Limitation: in -n worlds interval anchors are treated as points at their public date (all 1432 inside their interval); n and t within about 0.003 of j on dense worlds.
8. No leakage path found: gold never read by variants; LOPO exactness brute-force tested.

## 8. Harness requests

1. `src_hash` should cover imported modules, not only the variant file (worked around with an `F2_VERSION` constant).
2. Handle one-class refit worlds in the harness (fallback or N/A).
3. Store per-fold points in P80 records (today pooled, `metrics_std` 0).
4. Tag suite tracks whose target label mix differs from practice (diag, pilot, ext*).
5. Optionally expose per-anchor intervals for leave-page-out interval emissions.

## Files (`F2/`)

`f2core.py`, `f2var.py` (F2_VERSION 5, hash c512b3), `f2feat.py`, `plugins.py`, `test_f2.py`, `analysis.py`, `analysis.txt`, `grids.py`, `table.py`; dev helpers not used for reported numbers: `quick.py`, `_suite.py`, `_sum.py`. Results: `results/F2-remote.jsonl` (g1 to g6, g6x).
