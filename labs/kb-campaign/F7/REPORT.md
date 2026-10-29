# F7 report: small neural models on CPU

Saved by the orchestrator from F7's final message (02:24).

Short answer: none of the three neural designs beats V9-LR on its own. DeepSets, GNN and the plain MLP on V9 features tie V9-LR or lose to it on practice. What beats V9-LR is an MLP over the V9 features plus F1's truth-discovery columns, trained as a correction on top of F1's dynworld posterior (`offset_col`): P80 0.836 / P10 0.747, selection 0.791 vs 0.742 for V9-LR. It still does not beat F1's dynworld variant alone. The offset option was a late addition: only the two configurations in the top 3 were run, on four test tracks.

## Top 3 (exact)

| # | module:Class + params | P80 pts / ECE | P10 pts / ECE | Sel | Sdev-jr | Sdev-jt | Ssealed-jr | Ssealed-jt | 20k-row refit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `F7/mlp.py:Variant` `{"extra_features": ["F1/plugins.py:td_all"], "offset_col": 45}` | 0.8355 / 0.023 | 0.7472 / 0.055 | **0.791** | 0.878 | 0.667 | 0.766 | 0.667 | 69 s, 1.44 GB |
| 2 | `F7/mlp.py:Variant` `{"extra_features": ["F1/plugins.py:td_post"], "offset_col": 45}` | 0.8303 / 0.024 | 0.7503 / 0.050 | 0.790 | 0.774 | 0.667 | 0.794 | 0.667 | 56 s, 1.50 GB |
| 3 | `F7/mlp.py:Variant` `{"blend": 0.5}` (no other families' plugins) | 0.8134 / 0.025 | 0.6755 / 0.061 | 0.744 | 0.882 | 0.664 | 0.668 | 0.668 | 7 s, 0.58 GB |

- Reference V9-LR (`v9 {"model":"lr","select":"arena"}`): P80 0.809, P10 0.674, sel 0.742; Sdev-jr 0.876, Sdev-jt 0.664, Ssealed-jr 0.669, Ssealed-jt 0.668.
- Runner-up to #3: `{"extra_features": ["F1/plugins.py:td_all","F2/f2feat.py:core"]}` sel 0.758, Sdev-jr 0.861, Ssealed-jr 0.701.
- `offset_col: 45` = first plugin column, F1's dynworld posterior (valid only with no `drop_features`). Logit = `a*logit(td) + MLP(x)`, `a` starts at 1 and the last MLP layer at 0, so the model starts at F1's posterior; weight decay pulls the correction back toward it.
- Runtime = harness `run_s` on the Mac with 1 thread, plugin included. Selection numbers for #1 and #2 from `results/F7-mac.jsonl`; others from the remote files.

## What was tried (P80 / P10 points, arena selection unless noted)

- MLP on V9 features (harness V9 pipeline with a torch MLP; signed-log inputs, one-hot kind, standardized; dropout, AdamW, early stopping on an inner page-grouped split, 5-seed ensemble). Default 0.808/0.662; h16 0.811/0.654; h64 0.813/0.665; layers1 0.813/0.659; wd 0.01 0.806/0.660; drop 0.4 0.805/0.656; no stage 2 0.810/0.668; balanced loss 0.809/0.660; seeds 10 + layers1 0.816/0.661; h64 + layers1 0.812/0.662; mf1 selection 0.798/0.645. Blend with LR: 0.25 gives 0.819/0.672, 0.5 gives 0.813/0.676 (the only plugin-free config above V9-LR, 0.744 vs 0.742, within noise).
- MLP on V9 plus other families' plugins: +td_all 0.819/0.698; +td_all+f2core 0.821/0.696; +td_all+f2all 0.813/0.695; +td_all+f2core+round_up 0.823/0.691; +td_post+f2core 0.822/0.679; +f2core 0.824/0.673; +td_all blend 0.5 0.824/0.688; +td_all seeds 10 0.822/0.692; +td_all no stage 2 0.820/0.685; +deepsets plugin P10 0.669; with the offset: #1 and #2.
- Same inputs through LR: LR+td_all 0.791/0.678; LR+td_all+f2core 0.798/0.684; LR+f2core 0.806/0.678. On identical inputs the MLP is +0.024 on the selection mean, +0.057 with the offset.
- DeepSets (per fact, up to K observations of its key: half nearest labelled, half nearest unlabelled; features: signed log gap, same day, same value, consistent value, same page, page size, op, fact count, numeric log ratio, label one-hot for visible rows on other pages, nearest-anchor and nearest-observation flags; mean, max and attention pooling). Default 0.744/0.662; K32 0.751/0.662; mean-only 0.734/0.662; attention-only 0.746/0.661; mil 0.788/0.654; with_v9 0.817/0.652; mil with_v9 0.812/0.671; mil with_v9+td_all 0.813/0.683. Pure DeepSets learns nothing on P10 (about 25 false facts; predicts everything true). Fact-level held-out AUC on two P80 folds: DeepSets 0.946 vs V9-LR 0.967.
- GNN (hand-written torch, 2 rounds; nodes facts, rows, pages, (okey, value) claims; time-aware fact-fact edges; page-level label trick). Full config (seeds 3, k 4) did not finish on the loaded remote box; reduced (seeds 1, k 2, 150 epochs) 0.672 / 0.656, near always-true.
- V9-LR with the DeepSets plugin 0.807/0.679 vs 0.809/0.674 (neutral); deepsets_mil plugin 0.806/0.677.
- Throughout: calibration on OOF row probabilities (isotonic default, Platt option), exact arena rule, confidence clipped to [0.5, 1], one-class refit fallback to the practice fit (works on Sprac-jr where V9-LR crashed).
- Why: practice has 277 false rows; neural set and graph models cannot learn the bracket logic from scratch at that size, and the handcrafted V9 features already encode it. The neural gain comes from combining strong signals nonlinearly, anchored on a good prior.

## Suite tests (never used for selection)

| Track | MLP+td_all | MLP blend 0.5 | V9-LR |
|---|---|---|---|
| Sdev-nr | 0.757 | 0.712 | 0.688 |
| Ssealed-nr | 0.759 | 0.693 | 0.677 |
| Scal-jr | 0.672 | 0.692 | 0.756 |
| Ssyn-jr | 0.668 | 0.670 | 0.815 |
| Sprac-jr (fallback) | 0.691 | 0.682 | crashed |
| Sdiag-jr | -0.33 | -0.33 | -0.33 |
| Spilot-jr | -0.28 | not run | not run |

Every transfer track collapses to always-true (0.663 to 0.667) for every F7 model, as for V9-LR.

## Runtime per 20,000-row world (Mac, Apple silicon; an x86 2-core box is probably 1.5 to 2 times slower)

| Model | Refit on the world | Fit on practice + predict | Peak RSS | Threads |
|---|---|---|---|---|
| MLP | 6.6 s | 3.9 s + 1.8 s | 0.59 GB | 2 |
| MLP + F1 plugin | 56 to 73 s | not measured | 1.44 GB | 1 |
| DeepSets | 69 s | 59 s + 0.3 s | 1.03 GB | 2 |
| GNN | killed after 14 min | 162 s + 0.9 s | 1.08 GB | 2 |

Everything fits 2 CPU / 6 GiB / 30 min except the GNN refit. Raw timing lines in `F7/timing.jsonl`. Torch at inference: not needed (2 x 32 hidden-layer ensemble = plain matmuls); training on the 20k world needs the torch CPU wheel or a hand port (MLP + AdamW + early stopping, about 150 lines of Rust).

## Plugins (`F7/plugins.py`)

- `f7_deepsets` (`F7/deepsets.py:features`, k=1): DeepSets fact logit, OOF on labelled rows; neutral in V9-LR.
- `f7_deepsets_mil` (`F7/deepsets.py:features_mil`, k=1): row-trained version; P10 0.677, P80 0.806, neutral.
- `f7_gnn` (`F7/gnn.py:features`, k=1): not measured, too slow.

All three refit on the world they are called on (on transfer tracks they use that world's public labels).

## Things that look wrong

1. On Ssyn-jr and Scal-jr the MLP refit collapses to always-true, where V9-LR reaches 0.815 and 0.756. Not diagnosed; the main robustness warning against the MLP.
2. Every transfer track lands at always-true.
3. #1 and #2 inherit any leak F1's `td_post` OOF scoring might have (not audited by F7).
4. Leakage controls: own row excluded, same-page labels masked, hidden fold pages' labels masked, page-level label trick in the GNN. The MLP inherits V9's design (features computed once with all labelled anchors). No harness leakage path found.
5. Mac and remote torch CPU numerics may differ slightly.

## Harness requests

- `v9.Variant` should expose its OOF fact probabilities so V9-based models can serve as plugins.
- The remote CPU venv lacked torch at the start (fixed by the orchestrator).

Remote runs `F7-gnn1` and the last `F7-g2` jobs were stopped by the orchestrator at 02:24 (no results needed from them).

Files: `F7/common.py`, `mlp.py`, `deepsets.py`, `gnn.py`, `plugins.py`, `timing.py`, `summ.py`, `suite.py`; results `results/F7.jsonl`, `results/F7-remote.jsonl`, `results/F7-mac.jsonl`.
