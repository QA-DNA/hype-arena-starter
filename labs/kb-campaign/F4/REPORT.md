# F4 report: knowledge graph, semi-supervised learning, lexicon

Saved by the orchestrator from F4's final message (02:11). Plugins final in `F4/plugins.py`.

## Top 3 (class `F4/f4models.py:Variant`, a V9 subclass; selected on P80 and P10 only)

| | params JSON | P80 pts | P10 pts | mean | ECE P80 / P10 | Sdev-jr | Sdev-jt plain / match | Ssealed-jr | Ssealed-jt plain / match |
|---|---|---|---|---|---|---|---|---|---|
| **T2 (recommended, F4 only)** | `{"mil":2,"lap":0.03,"lap_page":0.0,"lap_tau":10.0,"extra_features":["F4/f4graph.py:prop_feats"]}` | 0.8376 | 0.7065 | 0.7721 | 0.022 / 0.064 | 0.881 | 0.599 / **0.883** | 0.894 | 0.649 / **0.886** |
| T1 (uses an F2 plugin) | `{"mil":2,"lap":0.02,"lap_page":0.0,"lap_tau":10.0,"extra_features":["F4/f4graph.py:prop_feats","F2/f2feat.py:core"]}` | 0.8440 | 0.7128 | 0.7784 | 0.023 / 0.059 | 0.875 | 0.652 / 0.723 | 0.897 | 0.653 / 0.739 |
| T3 (no plugins) | `{"mil":2,"lap":0.03,"lap_page":0.0,"lap_tau":10.0}` | 0.8366 | 0.6972 | 0.7669 | 0.022 / 0.064 | 0.881 | 0.588 / 0.723 | 0.890 | 0.638 / 0.702 |
| reference: v9 `{"select":"arena"}` | | 0.8092 | 0.6739 | 0.7416 | 0.029 / 0.061 | 0.876 | 0.664 | 0.669 | 0.668 |

- "match" = same params plus `"transfer":"match"` (see suspicious item 2).
- T2 recommended over T1 because T1 depends on F2's code, which changed during the run.

Paired check against v9 arena (local, same folds and seeds):

| | P80: mean difference, folds won | P10: mean difference, seeds won |
|---|---|---|
| T2 | +0.029, 4/5 with 1 tie | +0.033, 9/10 with 1 tie |
| T3 | +0.028, 4/5 | +0.023, 8/10 |
| T1 | +0.035, 4/5 with 1 tie | +0.039, 9/10 |
| MIL only | +0.013, 4/5 | +0.006, 5/10 |

Runtime on a 20,000-row world: Mac, 1 core, unloaded, T2 refit on Sdev-jr 5.9 s, 482 MB peak RSS; T1 7.1 s. Remote box (nice 19, load about 130): 10 to 28 s per world, at most 385 MB. Fits 2 CPU / 6 GiB / 30 min with a large margin.

## Methods (code in `F4/`)

- **Graph (`f4graph.py`).** Links facts that share an observation key and come from different pages: same-claim edge when values are consistent (interval overlap), contradicts edge when not. Edge weight `exp(-|dt|/tau)`, factor `beta` when the other fact is dated later. Same-page and same-row membership kept separately. Subjects, attributes, events and relation links enter as lexicon features, not propagation nodes. Edge building is label-free; labels enter only as anchors (true row +1; single-fact false row -1; multi-fact false row -1/k or minus its blame). Every plugin gives anchor facts leave-fold-out values (5 page folds).
- **Labeller `f4graph.py:Prop`.** Modes `prop` (clamped label propagation), `spread` (label spreading), `ppr` (personalized PageRank on a doubled +/- graph). Options `pagelie` (page EM prior), `em` (noisy-OR blame rounds). Row P(true) = product of fact P(true), then isotonic calibration and an arena-optimal threshold and unsure band.
- **`f4models.py:Variant` (V9 subclass, `select='points'` = A/score.py arena points).** `mil`: MIL / noisy-OR EM (facts of labelled multi-fact false rows trained as false with weight = blame, as true with 1 - blame). `pseudo`, `selftrain`. `lap`, `lap_page`, `lap_tau`: graph-regularized LR (Laplacian over same-claim edges, optional same-page edges), own L-BFGS solver, matches sklearn LR at lap=0 (self-check). `transfer="match"`, `match_seeds`.
- **`f4models.py:CoTrain`:** co-training of a temporal view and a source/page view.
- **`f4lex.py`:** label-free lexicon features.
- Contract: confidence floored at 0.5; arena-rule thresholds; a one-class refit world falls back to fitting on practice.

## Results by item (mean of P80 and P10 points; v9 arena = 0.7416)

1. **Propagation as a labeller.** Prop mode tau 10, beta 1, gamma 0.2: 0.7250 (P80 0.7839, P10 0.6661). Spread 0.698 to 0.738. PPR 0.664 (about always-true). Shorter kernels win: tau 10 > 30 > 90 > infinite (0.65 to 0.66). As the `prop_feats` plugin it helps only on top of the Laplacian: +0.5 points on average over 4 settings (range -0.4 to +1.2).
2. **Self-training and co-training.** V11 with the fixed harness (v9 arena, selftrain 1): 0.7489 (+0.7). Pseudo-labels: -1.0 to +1.4 depending on irrelevant parameters, treated as noise. Co-training 0.720 to 0.734 (-0.8 to -2.2), negative.
3. **EM over pages and facts.** MIL / noisy-OR blame: consistent +1.0 (mil 1, 2, 3 similar). Page latent-lie EM finds structure on full practice (8.6% of pages lie, false rate 0.50 vs 0.12) but the leave-row-out posterior has AUC 0.48 on scored facts; as a plugin -0.3 to +0.4, as a labeller prior -1.2. Matches the generator analysis: false rows are not clustered beyond chance. `page_lie_lab` worse than the soft version (-0.4 to -1.4). Blame plugin neutral (-0.4 to +0.3).
4. **Laplacian-regularized LR.** lap 0.01 to 0.03 without page edges: +1.0 to +1.5 on top of MIL. Same-page edges hurt (-0.7 at weight 1, -6 at lap 0.3). Main source of the refit suite gains.
5. **Lexicon features.** `lex_features`, `lex_small`: -0.4 to -1.8 (practice has only 40 link facts and 234 event-tied facts; overfit). HGB with all plugins 0.752, about LR, 60 times slower.

Grids: stage A 171 configs, B 73, C 50, D 21 (P80 and P10 each), final suite run of 7 configs on 80 tracks plus 4 matched-transfer configs on 40 transfer tracks. Lines in `results/F4-remote.jsonl`; leaderboards `F4/grids/stage{A,B,C,D}.lb`; Mac smoke tests `results/F4-dev.jsonl`.

## Suite tests (points; X forms within about 0.02 of the S forms)

| track | T1 | T2 | T3 | v9 arena | Prop t10 |
|---|---|---|---|---|---|
| Sdev-jr / nr | 0.875 / 0.870 | 0.881 / 0.856 | 0.881 / 0.840 | 0.876 / 0.688 | 0.724 / 0.603 |
| Scal-jr / nr | 0.919 / 0.916 | 0.909 / 0.891 | 0.901 / 0.864 | 0.756 / 0.687 | 0.711 / 0.578 |
| Ssealed-jr / nr | 0.897 / 0.890 | 0.894 / 0.865 | 0.890 / 0.847 | 0.669 / 0.677 | 0.725 / 0.630 |
| Ssyn-jr / nr | 0.939 / 0.935 | 0.937 / 0.917 | 0.935 / 0.898 | 0.815 / 0.706 | 0.764 / 0.659 |
| Sdiag-jr | -0.059 | -0.045 | 0.008 | -0.332 | -0.248 |
| Sdev-jt, plain | 0.652 | 0.599 | 0.588 | 0.664 | 0.719 |
| Sdev-jt, match | 0.723 | 0.883 | 0.723 | n/a | n/a |
| Scal / Ssealed / Ssyn -jt, match | 0.721 / 0.739 / 0.702 | 0.884 / 0.886 / 0.889 | 0.762 / 0.702 / 0.917 | 0.662 / 0.668 / 0.668 | 0.723 / 0.721 / 0.755 |

Pilot, prac and the ext worlds are negative or near always-true for every config. Under matched transfer, MIL alone gets 0.84 on Sdev-jt and 0.92 on Ssyn-jt.

## Plugins (`F4/plugins.py`)

| name | k | what |
|---|---|---|
| `prop_p` | 1 | propagated P(fact true) |
| `prop_feats` | 7 | spread score, clamped propagation score, PPR log-ratio and log-mass, log support and contradiction degree, P(true) |
| `prop_feats_t10` | 7 | `prop_feats` with a 10-day kernel |
| `page_lie` | 3 | page latent-lie posterior from the other rows of the page (soft), expected page false rate, log lift |
| `page_lie_lab` | 3 | comparison only: observes page neighbours' labels |
| `blame_feats` | 4 | P(fact false), blame share in the row, noisy-OR P(fact false given row false), max P(false) of the other facts |
| `all_feats` | 14 | `prop_feats` + `page_lie` + `blame_feats` |
| `lex_features` | 27 | value kind, aliases, subject type, event-date and subject-birth offsets, relation links, key volatility |
| `lex_small` | 19 | `lex_features` without the value-kind one-hot |

## Suspicious items

1. v9 and MIL-only refit collapse to about always-true on several worlds (Ssealed-jr 0.669, Scal-nr 0.687, Ssyn-nr 0.706) while the Laplacian solver reaches 0.89 to 0.93 there. Root cause not found (maybe sklearn LR scale or convergence on those worlds).
2. Plain transfer is at or below always-true for every V9-family config. `transfer:"match"` (density-matched transfer fit) fixes T2 (0.88 to 0.89) but not T1 and T3 (0.70 to 0.76): unstable. Built after seeing the suite transfer failures, so matched-transfer numbers are test-informed.
3. T1 depends on F2's live code: Sdev-jr 0.8754 on the box vs 0.8773 on a later Mac re-run; T2 stable at 0.881.
4. Noise floor: configs differing only in an irrelevant parameter swing by up to 0.015, so the order within the top 20 is mostly noise. MIL, Laplacian without page edges and tau 10 are the robust effects.
5. No leakage path found: plugins read only labelled rows and give anchors leave-fold-out values; the Laplacian uses unlabelled facts' features, never their labels.

## Harness requests

- Store per-fold and per-seed metrics in each result line, for paired tests from the results file.
- Harness v9 crashes on one-class refit worlds (Spilot-r, Sprac-r and their X versions, 8 failed jobs).
- `remote.sh` prints `line 161: o: command not found` on every run.
