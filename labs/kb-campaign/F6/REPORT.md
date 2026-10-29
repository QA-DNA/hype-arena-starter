# F6 report: stress and robustness battery

Saved by the orchestrator from F6's final message (02:20). `stress.py` final; 3,794 baseline jobs, 0 errors. Headline: with extracted practice forms every baseline lands near or below always-true (0.662 to 0.667 points).

## 1. How to run it

Code in `F6/`: `stress.py`, `rlaunch.sh` (remote launcher, a copy of remote.sh `launch_once`: same lock, caps, snapshot, logs), `selfcheck.py`, `data/forms_cv*.jsonl` (worker D's extracted practice forms, copied from the evaluation-suite lab). Results go to `results/<worker>.jsonl` with the `run.py` fields plus `stress`, `level`, `base_track`, `n_reps`, `subsets`, `conf_below_half`, `stress_hash`, `stress_info`. Track name `F6/<stress>/<level>/<base>`.

```bash
cd $KBC; PY="$KBC/.venv/bin/python -I"
# whole battery (407 cells) on the remote box, 20 jobs, frozen code snapshot:
$PY F6/stress.py run --variant 'F3/x.py:Cls=[{"a": 1, "extra_features": ["F5/p.py:f"]}]' --jobs 20 --worker P3-remote --remote P3-st1
remote/remote.sh wait P3-st1
# local subset:
$PY F6/stress.py run --variant v9='[{"model": "lr", "select": "arena"}]' --stress copies,xforms --base P80,P10 --jobs 2 --worker P3
# filters: --stress a,b  --base <tracks, P = label-ratio curve>  --level REGEX  --only REGEX  --dry
$PY F6/stress.py list [filters]
$PY F6/stress.py summary --worker F6-remote,F6,P3-remote [--metric points_per_row|accuracy|ece10|false_recall|false_precision] [--variants ...] [--out path]
$PY F6/selfcheck.py   # builder invariants, about 20 s
```

- Grid syntax as `run.py` (dict = cartesian product; list-valued params need the list-of-dicts form).
- Failed cells (for example refit on a single-class world) are written with `metrics: null` and an `error` field; the battery continues.
- Summary: one table per stress (value and delta vs the same variant's clean track), noise digest, robustness profile (mean / worst delta), transfer-minus-refit gap, confidence check, failed cells, subset tables.
- Cost per finalist: V9-LR-like about 400 jobs, 5 to 10 min at 20 remote jobs; HGB about 15 min; V12 MMR features about 1 hour (restrict to `--base P80,P10,P,Sdev-jr,Sdev-jt`).

## 2. The battery (407 cells per variant)

Default bases: P80, P10, Sdev-jr/jt, Ssealed-jr/jt, Sdev-nr/nt.

| Stress | Levels | Design |
|---|---|---|
| clean | - | identity; reference for every delta |
| density | 0.1 / 0.25 / 0.5 / 1.0, 3 seeds (6 suite bases) | unlabelled rows split into K = 1/level groups, each run with all labelled rows; every target scored once per level |
| labels | 5 / 10 / 20 / 50 / 80% of pages, seeds 0..9 (practice) | exp.py sampler; scored = the rest |
| copies | hlie, hctrl (tell-free, all bases); lie, control, mixed (confounded; P80, P10) | copies.py ported: 3 copies at +1/+7/+30 days, own page each, unlabelled, never scored; subsets `copied` / `not_copied` |
| order | bundles, rows (3 seeds); single, hid20 | page order shuffled; rows shuffled and pages recomputed; one row per page; hidden rows re-paged into blocks of 20 |
| xforms | B/all, B/hidden (suite); cv/*, cvpc/* (practice) | B/all = harness X track; hidden = gold on labelled rows, extracted on hidden; practice uses worker D's CV extraction (61% rows exact); subsets `own_exact` / `own_wrong` |
| noise | drop, subj, attr, value, op, mix x 0.05 / 0.1 / 0.2 / 0.4 x hidden / all (P80, P10, 4 dev) | errors applied to stated facts; subsets `own_noisy` / `own_clean` |
| unseen | 20% of keys, 3 seeds | labelled rows stating a held-out key lose their label but stay as evidence; subsets `heldout` / `seen` |

## 3. Gates

- clean: V9-LR P80 0.7770, P10 0.6391, Sdev-jr 0.8760; always-true 0.6668 / 0.6621 (match `W0.jsonl`).
- density 1.0 = clean; labels 0.1 = P10 (identical masks, asserted in `selfcheck.py`).
- copies hlie P10, V9-LR legacy: false recall 0.120, false precision 0.247, accuracy 0.766 (REPORT_v12 exactly).
- xforms cv/all P80, V9-LR: 0.6468 vs worker D's 0.6463 (row-exact 0.610 in both).
- `selfcheck.py` passes (gold aligned with scored rows, no label on an unlabelled row, copies never scored, each target scored once per replicate, noise at rate 0 = identity).
- Remote clean numbers equal Mac numbers.

## 4. Results (points per row; delta vs the same variant's clean track)

Clean:

| Variant | P80 | P10 | Sdev-jr | Sdev-jt | Ssealed-jr | Ssealed-jt | Sdev-nr | Sdev-nt |
|---|---|---|---|---|---|---|---|---|
| always_true | 0.667 | 0.662 | 0.667 | 0.667 | 0.667 | 0.667 | 0.667 | 0.667 |
| V5 | 0.532 | 0.428 | 0.654 | 0.654 | 0.667 | 0.667 | 0.674 | 0.674 |
| V9-LR (mf1) | 0.777 | 0.639 | 0.876 | 0.664 | 0.673 | 0.668 | 0.695 | 0.664 |
| V9-HGB (mf1) | 0.724 | 0.597 | 0.890 | 0.777 | 0.890 | 0.773 | 0.808 | 0.772 |
| V9-LR-arena | 0.809 | 0.674 | 0.876 | 0.664 | 0.669 | 0.668 | 0.688 | 0.664 |
| V9-HGB-arena | 0.763 | 0.661 | 0.890 | 0.770 | 0.877 | 0.769 | 0.872 | 0.753 |
| F2-chain viterbi (early config) | 0.814 | 0.736 | 0.930 | 0.945 | 0.932 | 0.944 | 0.934 | 0.945 |
| interval engine | 0.059 | 0.030 | 0.034 | 0.034 | 0.034 | 0.034 | 1.000 | 1.000 |
| point engine | 0.399 | 0.038 | 0.479 | 0.479 | 0.514 | 0.514 | 0.959 | 0.959 |
| V12mmr-replace (practice only) | 0.807 | 0.642 | | | | | | |

Key stress cells:

| Variant | labels 5% / 20% / 50% / 80% | density 0.1 (Sdev-jr / jt) | hlie P10 / Sdev-jr | hlie copied-lie subset P10 / Sdev-jr | cv/all P80 / P10 | cv/hidden P80 / P10 | unseen Sdev-jr |
|---|---|---|---|---|---|---|---|
| V5 | 0.423 / 0.442 / 0.482 / 0.544 | -0.068 / -0.073 | -0.247 / -0.263 | -0.186 / 0.877 | -0.304 / -0.269 | -0.183 / -0.254 | -0.001 |
| V9-LR | 0.609 / 0.643 / 0.706 / 0.783 | -0.074 / +0.062 | -0.113 / -0.113 | -0.753 / -0.220 | -0.130 / -0.043 | -0.165 / -0.114 | -0.029 |
| V9-HGB | 0.602 / 0.609 / 0.689 / 0.721 | -0.073 / -0.053 | -0.046 / -0.110 | -0.671 / -0.014 | -0.074 / -0.012 | -0.121 / -0.066 | -0.011 |
| V9-LR-arena | 0.635 / 0.704 / 0.764 / 0.805 | -0.082 / +0.058 | -0.020 / -0.144 | -0.964 / -0.512 | -0.129 / -0.013 | -0.115 / -0.034 | -0.030 |
| V9-HGB-arena | 0.661 / 0.686 / 0.732 / 0.771 | -0.079 / -0.030 | -0.016 / -0.125 | -0.937 / -0.192 | -0.086 / -0.005 | -0.067 / -0.013 | -0.011 |
| F2-chain | 0.712 / 0.749 / 0.785 / 0.817 | -0.089 / -0.071 | -0.100 / -0.191 | -0.957 / -0.410 | -0.159 / -0.104 | -0.150 / -0.100 | +0.004 |
| V12mmr-replace | 0.556 / 0.702 / 0.733 / 0.792 | n/a | -0.132 / n/a | -0.611 / n/a | -0.153 / -0.027 | -0.169 / -0.116 | n/a |
| interval / point | flat / 0.010 to 0.362 | 0 / 0 | 0 / 0 | n/a | -0.018 / -0.261 (point) | | -0.003 / -0.110 |

Noise digest (mean delta over the 4 rates and all noise bases, hidden / all scope):

| Variant | value | subj | attr | drop | mix |
|---|---|---|---|---|---|
| V5 | -0.385 / -0.447 | -0.25 / -0.28 | -0.18 / -0.20 | -0.10 / -0.12 | -0.25 / -0.29 |
| V9-LR | -0.077 / -0.060 | -0.050 / -0.054 | -0.044 / -0.055 | -0.013 / -0.019 | -0.061 / -0.053 |
| V9-HGB | -0.206 / -0.168 | -0.09 | -0.06 | -0.01 / -0.02 | -0.108 / -0.105 |
| V9-LR-arena | -0.064 / -0.059 | -0.04 / -0.05 | -0.03 / -0.05 | -0.01 / -0.02 | -0.05 |
| F2-chain | -0.283 / -0.227 | -0.138 | -0.10 | -0.148 / -0.149 | -0.184 / -0.177 |
| point | -0.257 / -0.403 | -0.19 / -0.31 | -0.15 / -0.24 | -0.08 / -0.19 | -0.18 / -0.32 |

`op` errors have no effect (|delta| <= 0.008; only 38 practice facts carry a comparison op).

Transfer minus refit (clean): V9-LR -0.212 on Sdev-j; V9-HGB -0.113 (dev-j), -0.116 (sealed-j); V9-HGB-arena -0.12 everywhere; F2-chain transfer is better, +0.012 to +0.025 everywhere.

## 5. What it shows

1. Extracted forms cut points on real prose the most. With worker D's CV forms on P80 every baseline drops near or below always-true: V9-LR 0.647, HGB 0.649, F2-chain 0.655, V12 0.654 vs always-true 0.667. Gold on labelled rows plus extracted on hidden is worst for V9-LR and V12. Rows whose own form is exact also lose points (V9-LR P80 own_exact 0.694 vs about 0.78 clean): extraction errors spoil other rows' evidence. Suite B forms are 99.8% exact, so X tracks are not a robustness test.
2. Copied lies hit every evidence-pooling variant; the engines (labelled anchors only) are immune. On the copied-lie subset F2-chain and both arena V9s score -0.96 on P10 (almost every copied lie called true). F2-chain does not exploit the confounded `lie` tell (P80 -0.144) where V9 gains +0.11. hctrl changes about 0, so the damage is from the lies. Fix to test: source-level dedup.
3. Density: refit variants lose 0.07 to 0.13 at 10% unlabelled rows; F2 loses most on -n worlds (-0.128). Transfer V9-LR gains as density falls (0.664 -> 0.722 on Sdev-jt): its practice-trained vote features are out of distribution at suite density.
4. Label ratio: V9-LR and HGB beat always-true only from 20% (arena) or 50% (mf1) of pages labelled; F2-chain beats it at every ratio including 5% (0.712).
5. Unseen keys: engines lose up to 0.26 (rows with held-out keys lose every anchor); V9 loses 0.01 to 0.03; F2-chain flat (-0.011 to +0.004).
6. Noise: value errors hurt most, then subject errors. F2-chain is the most noise-sensitive strong variant (value -0.28, dropped facts -0.15; V9 about -0.02 on dropped facts).
7. Confidence below 0.5: V9 mf1 in about 330 cells (LR 94k predictions, HGB 301k); V9-arena about 135 cells (about 2k predictions); V12mmr-replace 68k; point engine too. F2-chain none (minimum 0.51).

## 6. Suspicious (test-world diagnostics, not used for selection)

- V9-LR refit is unstable on suite worlds: Sdev-jr 0.876 but Ssealed-jr 0.673 and Sdev-nr 0.695 (false recall 0.011 / 0.055); single-row pages restore 0.884 / 0.863. Tested cause: base columns 16 and 17 (page-other negative share and count): anchors sit on pages of at most 2 rows (6 on -n), targets on pages up to 20, and the LR extrapolates. `drop_features [16, 17]`: Ssealed-jr 0.876, Sdev-nr 0.839, P80 0.770; plus `stage2: false`: 0.885 / 0.864, P80 0.7955. HGB immune. A lead to evaluate on P80/P10 only; `order/hid20` probes the same shift on practice.
- The t and r cells of one world use independent random draws in the stochastic stresses (density, rows/bundles, noise, unseen); the t-minus-r gap is paired only for clean, copies, xforms, single and hid20.
- Provenance: arena V9 and F2 lines from a separate run (src_hash recorded); V12mmr-replace ran on practice cells only (131 cells), locally, `results/F6.jsonl`.

## 7. Runtime per 20,000-row world (Mac, one thread)

V9-LR 2.0 s, V9-HGB 3.6 s, F2-chain 0.8 s, V5 0.6 s, engines 0.1 s, V12mmr 27 s. Remote under nice 19: 2 to 6 times higher.

## 8. Harness requests

1. `remote.sh run` should accept a script other than `harness/run.py` (`F6/rlaunch.sh` can then be deleted).
2. Document in API.md that `World.static_key` must change for derived worlds (the battery appends `|F6:<tag>`).

## 9. Ranking of baselines (F6 builds no labellers)

- F2-chain: best clean, best label-ratio curve, best transfer; weakest to copied lies and noise.
- V9-HGB-arena: most stable on the suite.
- V9-LR-arena: best on noise, unstable suite refit.

Results: `results/F6-remote.jsonl` (3,663 lines), `results/F6.jsonl` (131 lines).
