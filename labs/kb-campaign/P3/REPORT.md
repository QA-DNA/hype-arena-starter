# P3 report: combinations and final selection

Saved by the orchestrator from P3's final message (02:53). Winner: the single-family F2 #1 chain. No combination beat it beyond noise on fresh practice splits; the best stack looked like a win on the harness splits (+0.006), the gain disappears on fresh splits, and it costs about 0.018 on every transfer track.

## Combination families tried

About 190 configs scored on P80 + P10 on the remote box, plus 8 Mac P80-only smoke runs. Code `P3/p3.py`, class `Stack`.

1. Stacked fact decider on top of the F2 #1 chain. Inputs: logit of the chain's fact probability, a no-evidence flag, any plugin; trained out of fold by page on labelled facts only; the chain's isotonic fact map optionally fitted out of fold (`oofmap`). Settings: LR with C in {0.03, 0.1, 0.3, 1, 3, 10}; LR with the chain logit as a fixed offset; HGB. Plugins: F1 td_post (#0 dynworld, #1 Accu, both), page_rel, indep_support, copy_margin; F4 prop_p, prop_feats, page_lie, blame_feats; F5 w_nds, lie_stale, lie_swap, lie_date, restate2, src_pagelie, uns_tl; F2 hmm#0, stale; P3 hmm2 (F2 #2's HMM posterior); F7 deepsets, gnn; null controls nulls#0 and nulls#0,1,2. Excluded: src_idblock (reads the id layout), txt_tuned (designed on all practice rows), page_lie_lab (sees neighbours' labels), F5 generator-specific blocks, lex_* (hurt in F4).
2. Chain modulation: a per-fact reliability q scales each vote's log emission by q^vg; q from w_nds, lie_stale, F4 page_lie or F1 page_rel; vg in {0.5, 1, 2}.
3. Dedup inside the chain: an exact-text copy casts no vote (F1's rule).
4. Posterior ensembles: LR on chain + F1 dynworld + F2 HMM logits (a weighted product of odds).
5. Calibrators and abstention: F2's row calibrator (isotonic or Platt, expected-points rule) vs F3's Decider with iso, platt, beta, hist or temp under arena3 or points.

## Search log (selection score, remote results)

- Step 1, singles (chain alone 0.8085): td_post#0 0.8094 (offset 0.8089), hmm2 0.8067, w_nds 0.8036, null1 0.8018, null3 0.8019; HGB 0.7951; Platt/arena3 0.7977; beta/arena3 0.7958; vote modulation 0.8020 to 0.8081; F7 deepsets alone P10 0.7407.
- Step 2, base td_post#0 (LR C=1): +w_nds **0.8144**, +restate2 0.8094, +lie_date 0.8089, +f2 hmm 0.8079, +F4 page_lie 0.8078, +null1 0.8033, +null3 0.8031, ..., +page_rel 0.7903. The whole lie_stale block (contains W_nds) 0.7986.
- Step 3, base td_post#0 + w_nds: +f2 hmm 0.8126, +hmm2 0.8110, +page_lie 0.8101, +restate2 0.8096, +null1 0.8088, +null3 0.8057, ..., +blame_feats 0.7785. Nothing improves; search stops.
- Backward elimination: dropping td_post#0 gives 0.8036 / 0.8063; dropping w_nds 0.8094. Both kept.
- Crossed with the decision layer (same two features): C 0.1 to 10 gives 0.8112 to 0.8144; iso/arena3 0.8144; offset 0.8126; dedup 0.8126; out-of-fold map off 0.8115; Platt 0.8080; beta/arena3 0.8012; HGB 0.7988.

## Selection-track results

| config | P80 pts | P10 pts | sel | ECE P80 / P10 | macro-F1 P80 / P10 | false P / R (P80) |
|---|---|---|---|---|---|---|
| a: F2 #1 chain | 0.8492 | 0.7678 | 0.8085 | 0.0106 / 0.0365 | 0.5840 / 0.5109 | 0.871 / 0.733 |
| b: a + dynworld | 0.8498 | 0.7691 | 0.8094 | 0.0126 / 0.0370 | 0.5844 / 0.5034 | 0.868 / 0.737 |
| c: a + dynworld + w_nds | 0.8508 | 0.7780 | 0.8144 | 0.0113 / 0.0363 | 0.5836 / 0.5228 | 0.871 / 0.729 |
| c with iso/arena3 | 0.8508 | 0.7779 | 0.8144 | 0.0082 / 0.0366 | 0.5836 / 0.5228 | 0.871 / 0.729 |
| d: c + dedup | 0.8519 | 0.7733 | 0.8126 | 0.0111 / 0.0384 | 0.5852 / 0.5213 | 0.872 / 0.737 |
| e: a + dedup | 0.8492 | 0.7600 | 0.8046 | 0.0113 / 0.0392 | 0.5840 / 0.5025 | 0.871 / 0.733 |
| f: a + w_nds | 0.8450 | 0.7676 | 0.8063 | 0.0097 / 0.0390 | 0.5810 / 0.5132 | 0.853 / 0.733 |
| F1 D1 (dynworld) | 0.8334 | 0.7712 | 0.8023 | 0.0284 / 0.0479 | | |
| F1 D2 (D1 + dedup) | 0.8334 | 0.7702 | 0.8018 | | | |
| v9 arena | 0.8092 | 0.6739 | 0.7416 | | | |
| always_true | 0.6668 | 0.6621 | 0.6645 | | | |

Paired differences vs a (Mac runs):

| vs a | harness splits, fold-paired | fresh splits, page-cluster bootstrap |
|---|---|---|
| b | +0.0012 +- 0.0028 | -0.0008 +- 0.0028 |
| c | +0.0062 +- 0.0032 (P80 +0.0016, P10 +0.0108 +- 0.0047) | **-0.0004 +- 0.0044** |
| d | +0.0043 +- 0.0045 | -0.0003 +- 0.0045 |
| e (dedup) | -0.0036 +- 0.0014 | **-0.0020 +- 0.0009**, CI [-0.0037, -0.0002] |
| f | -0.0019 +- 0.0033 | +0.0019 +- 0.0024 (P80 +0.0004 +- 0.0026) |

Fresh splits: 15 permuted P80 folds plus P10 seeds 10 to 29, 291 pages, B = 2000; a scores 0.8051 there. The reviewer's page bootstrap on the harness splits gives c minus a = +0.0062, SE 0.0042.

## Test tracks (points per row, mean over dev, cal, sealed, syn)

| config | S jt | S jr | S nt | S nr | X jt | X jr |
|---|---|---|---|---|---|---|
| a: chain | **0.9409** | 0.9286 | 0.9425 | 0.9239 | 0.9372 | 0.9243 |
| b | 0.9407 | 0.9361 | 0.9424 | 0.9232 | 0.9371 | 0.9295 |
| c | 0.9246 | 0.9330 | 0.9397 | 0.9249 | 0.9209 | 0.9272 |
| c with iso/arena3 | 0.9246 | 0.9422 | 0.9397 | 0.9356 | 0.9209 | 0.9384 |
| c with C=3 | 0.9248 | 0.9333 | 0.9397 | 0.9290 | 0.9211 | 0.9267 |
| c with offset | 0.9333 | 0.9291 | 0.9432 | 0.9207 | 0.9295 | 0.9236 |
| d | 0.9231 | 0.9334 | 0.9370 | 0.9260 | 0.9189 | 0.9316 |
| e | 0.9376 | 0.9267 | 0.9375 | 0.9182 | 0.9333 | 0.9245 |
| f | 0.9218 | 0.9274 | 0.9390 | 0.9231 | 0.9178 | 0.9238 |
| F1 D1 | 0.9393 | 0.9380 | 0.9374 | 0.9380 | 0.9358 | 0.9344 |
| v9 arena | 0.6654 | 0.7790 | 0.6652 | 0.6895 | 0.6653 | 0.7607 |
| always_true | 0.6669 | 0.6669 | 0.6669 | 0.6669 | 0.6669 | 0.6669 |

- Per world jt / jr: a dev 0.9419 / 0.9148, cal 0.9437 / 0.9402, sealed 0.9406 / 0.9226, syn 0.9375 / 0.9370; c dev 0.9240 / 0.9211, cal 0.9270 / 0.9424, sealed 0.9214 / 0.9296, syn 0.9260 / 0.9388.
- Why w_nds hurts on transfer: on jt tracks false precision falls from 0.948 to 0.887.
- Unsure-heavy worlds (diag, pilot, prac, ext*), S jt / jr: a 0.017 / -0.001, c 0.024 / 0.012, F1 D1 -0.006 / -0.061, always_true -0.164.

## F6 battery

Copied lies (hlie):

| | P80 | P10 | Sdev-jt | Ssealed-jt |
|---|---|---|---|---|
| a | 0.646 | 0.640 | 0.715 | 0.691 |
| e (a + dedup) | 0.847 | 0.763 | 0.940 | 0.940 |
| c | 0.650 | 0.638 | | |
| d (c + dedup) | 0.821 | 0.740 | 0.907 | |

- Copied true rows (hctrl): a 0.853 / 0.767, e 0.849 / 0.761.
- Extracted practice forms (cv/all): a 0.643 / 0.642, c 0.654 / 0.648, e 0.643 / 0.639; every config below always_true.
- Full battery means a / e: clean 0.899 / 0.896, copies 0.776 / 0.873, density 0.893 / 0.889, noise 0.748 / 0.745, order 0.900 / 0.897, xforms 0.814 / 0.812. Worst cell: value noise at 0.4 on Sdev, about 0.21.

## The winner

- Spec: `F2/f2var.py:Chain {"d0":0.03,"engine":"viterbi","eps_a":0.0005,"mono":"fit","mono_a":10,"pi_o":1,"vote_lr":48}`; reads no plugins. `P3/p3.py:Stack {"oofmap": false}` gives identical output on every track.
- Selection 0.8085 (P80 0.8492, P10 0.7678, seed std 0.0121), ECE 0.0235, macro-F1 0.5475.
- Reproduce: `cd $KBC_ROOT && .venv/bin/python -I harness/run.py --variant 'F2/f2var.py:Chain={"d0":0.03,"engine":"viterbi","eps_a":0.0005,"mono":"fit","mono_a":10,"pi_o":1,"vote_lr":48}' --tracks P80,P10 --worker P3`
- Rule applied: on the harness splits c leads by +0.0062, more than its fold-paired SE (0.0032) and the reviewer's bootstrap SE (0.0042). Under the finish rule (fresh splits, page bootstrap) c, b, d and f all tie with a, so the simplest config, a, wins. W_nds was itself picked by F5 on the same practice data, consistent with a winner's-curse gain.
- Runners-up in fresh-split order: f (+0.0019 +- 0.0024), d, c, b.
- Dedup left to the orchestrator: a + dedup (`P3/p3.py:Stack {"oofmap": false, "dedup": true}`) costs -0.0020 +- 0.0009 on clean fresh splits and gains about +0.20 under copied lies.

## Checks

- Leakage: td_post labelled facts take values from 5 inner page-fold runs with that fold's labels hidden; w_nds excludes the own page and labelled-false rows and reads labels of other pages only; Stack decider and fact map fitted out of fold by page on labelled facts only; scored rows carry no label in the harness world; the stack collapses to always_true under shuffled labels.
- Runtime, 20,000-row world, 2 threads, Mac (`/usr/bin/time -l`, not a results line): chain Ssyn-jt 1.2 s / 181 MB, Ssyn-jr 1.5 s / 175 MB; chain + dedup 1.5 s / 191 MB, 1.8 s / 187 MB; c Ssyn-jr 21 s / 538 MB. Remote (1 thread, nice 19, loaded): chain at most 3.7 s / 202 MB; c up to 470 s / 1.2 GB on Scal.
- Confidence: (1 - u) p >= (1 + u) / 2 > 0.5 by construction; on Ssyn the minimum decided confidence is 0.514 (bound 0.510); unsure rows NaN. The F3 Decider path can clip silently at 0.5; the winner does not use it.
- Single-class refit (Spilot, Sprac, Xpilot, Xprac with r): no crash; fallback to the practice fit (`chosen ['fallback','practice']`), so jr = jt. v9 crashes (8 lines in the errors file).

## Suspicious

- The same chain scores P10 0.7673 on the Mac and 0.7678 remotely, so every paired SE above comes from Mac runs only.
- `F1/plugins.py` puts `F1/` first on `sys.path`, so `F1/timeit.py` shadows the standard library and breaks sklearn imports; `p3.py` imports the real timeit first (F1 should rename the file).
- Suite j-tracks are easier than the competition (reviewer's caveat confirmed).

Results: `results/P3-remote.jsonl` (grids, tests, F6), `P3.jsonl` (Mac smoke), `P3-paired.jsonl`, `P3-denoise.jsonl`, `P3-denoise2.jsonl` (fresh splits, per-row points), `P3-remote.errors.jsonl`. Code `P3/`: `p3.py`, `paired.py`, `boot.py`, `bench20k.py`, `table.py`, `sel.py`, `lb.sh`, grids `g/*.json`.
