# Reproduction gates (W0, 2026-10-29)

All numbers come from `results/W0.jsonl` (worker W0), produced by `harness/run.py`; nothing was adjusted.
Hardware: Apple Mac (15 logical cores, 8 used), one BLAS/OpenMP thread per job, 8 jobs in parallel.
P80 rows show exp.py's mean over the 5 folds (`fold_mean`, how the published numbers were computed); the harness
`metrics` for P80 are pooled over the folds (for example V9-LR fixed: pooled 0.8677, fold mean 0.8672).
"published decide()" = `legacy_unsur: true` (the `<U5` bug kept in the threshold search, output mapped back to
`unsure` as A/v9/run_v9.py did); "dtype fixed" = the default.

**Verdict: every gate reproduces** (to the printed precision of the source; V12mmr P80 0.9040 vs published 0.905
is the only off-by-one in the third decimal, explained below).

| Baseline | Track | Metric | Expected | Got | Runtime s |
|---|---|---|---:|---:|---:|
| always_true | Sdev-nr | accuracy | 0.8335 | 0.8335 | 0.001 |
| always_true | Sdev-nr | macro_f1 | 0.3031 | 0.3031 | 0.001 |
| always_true | Scal-nr | accuracy | 0.8335 | 0.8335 | 0.001 |
| always_true | Scal-nr | macro_f1 | 0.3031 | 0.3031 | 0.001 |
| always_true | Ssealed-nr | accuracy | 0.8335 | 0.8335 | 0.001 |
| always_true | Ssealed-nr | macro_f1 | 0.3031 | 0.3031 | 0.001 |
| always_true | P80 | accuracy (fold mean) | 0.833 | 0.8332 | 0.001 |
| V5 | P80 | accuracy (fold mean) | 0.746 | 0.7455 | 0.091 |
| V5 | P10 | accuracy | 0.699 | 0.699 | 0.184 |
| V9-LR published decide() | P80 | accuracy (fold mean) | 0.902 | 0.9024 | 0.478 |
| V9-LR published decide() | P10 | accuracy | 0.816 | 0.8155 | 0.748 |
| V9-LR dtype fixed | P80 | accuracy (fold mean) | 0.867 | 0.8672 | 0.475 |
| V9-LR dtype fixed | P10 | accuracy | 0.817 | 0.8173 | 0.735 |
| V9-LR dtype fixed | P80 | points_per_row | 0.777 | 0.777 | 0.475 |
| V9-LR dtype fixed | P10 | points_per_row | 0.639 | 0.6391 | 0.735 |
| V9-HGB published | P80 | accuracy (fold mean) | 0.876 | 0.8763 | 5.009 |
| V9-HGB published | P10 | accuracy | 0.807 | 0.8072 | 4.612 |
| interval engine | Sdev-nr | accuracy | 1.0000 | 1.0 | 0.078 |
| point engine | Sdev-nr | accuracy | 0.9795 | 0.9795 | 0.088 |
| interval engine | Scal-nr | accuracy | 1.0000 | 1.0 | 0.077 |
| point engine | Scal-nr | accuracy | 0.9795 | 0.9795 | 0.087 |
| interval engine | Ssealed-nr | accuracy | 1.0000 | 1.0 | 0.091 |
| point engine | Ssealed-nr | accuracy | 0.9795 | 0.9795 | 0.092 |
| point engine on -j (= point-jitter) | Sdev-jr | accuracy | 0.7395 | 0.7395 | 0.091 |
| point engine on -j (= point-jitter) | Scal-jr | accuracy | 0.7246 | 0.7246 | 0.089 |
| point engine on -j (= point-jitter) | Ssealed-jr | accuracy | 0.7571 | 0.7571 | 0.085 |
| point-jitter engine on -n | Sdev-nr | accuracy | 0.7395 | 0.7395 | 0.086 |
| point-jitter engine on -n | Scal-nr | accuracy | 0.7246 | 0.7246 | 0.091 |
| point-jitter engine on -n | Ssealed-nr | accuracy | 0.7571 | 0.7571 | 0.092 |
| V9-LR published decide() on gold | Sdev-nr | accuracy | 0.8410 | 0.841 | 2.306 |
| V9-LR dtype fixed on gold | Sdev-nr | accuracy | - | 0.8412 | 2.235 |
| V9-LR published decide() on gold | Scal-nr | accuracy | 0.8391 | 0.8391 | 2.45 |
| V9-LR dtype fixed on gold | Scal-nr | accuracy | - | 0.847 | 2.441 |
| V9-LR published decide() on gold | Ssealed-nr | accuracy | 0.8385 | 0.8385 | 1.978 |
| V9-LR dtype fixed on gold | Ssealed-nr | accuracy | - | 0.8388 | 1.949 |
| V11 (selftrain 1) published | P80 | accuracy (fold mean) | 0.907 | 0.9067 | 0.966 |
| V11 (selftrain 1) published | P10 | accuracy | 0.809 | 0.8092 | 1.544 |
| V12mmr-replace published | P80 | accuracy (fold mean) | 0.902 | 0.9028 | 2.133 |
| V12mmr-replace published | P10 | accuracy | 0.822 | 0.8224 | 3.91 |
| V12mmr published | P80 | accuracy (fold mean) | 0.905 | 0.904 | 2.168 |
| V12mmr published | P10 | accuracy | 0.803 | 0.8029 | 3.864 |

Published sources: `labs/kb-experiments/results_v0_v8.txt`, `results_v9.txt`, `results_v12.txt`,
`docs/research/evaluation-suite-results.md` (always-true, interval/point/point-jitter engines, V9 on gold,
worker D's dtype-fixed row: P80 0.867, points 0.777, P10 0.817, points 0.639). Suite gates ran on cal and sealed too;
under the new protocol every suite world is a test track anyway.

## Leakage checks (`harness/check_leak.py`, evaluator side)

- Practice P80/P10: in every fold, scored rows carry `label = None` and `labelled = False`; labelled masks are whole pages.
- Suite (dev, diag, cal, sealed, syn; `-j` and `-n`): `World` holds only the listed public attributes; hidden rows
  carry no label; labelled rows' labels equal the public `universe.csv` labels; target dates are unchanged; every
  target's facts are exactly the STATED form of `gold/labeled.csv`.
- Stated vs expected: for every false target atom with op `eq`, the world's fact never equals the gold
  `expected_value` (0 of 2,643 on dev/cal/sealed/syn, 0 of 470 on diag). Diag's other 898 false atoms carry a
  comparison op ("less than four hours", expected 4 h): their number equals the expected one by construction.
- `-j`: all 1,398 to 1,460 interval anchors per world are re-dated; all intervals dropped; the leading interval
  phrase is stripped from their text (one cal row keeps a natural "from 78 respondents ... through a sandwich").
- Only labelled rows have intervals in the suite (`validity_qualifier` is null on every hidden row) and every interval
  anchor is a true row, so re-dating an anchor inside its interval keeps its label valid and leaves target gold untouched.

## Runtime per baseline and track (variant time in seconds, summed over folds; one thread)

| Variant | P80 | P10 | Sdev-jr | Sdev-jt | Sdev-nr | Sdiag-jr | Ssyn-jr | Xdev-jr | max peak RSS MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| always_true | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 139 |
| v5 | 0.09 | 0.18 | 0.15 | 0.16 | 0.15 | 0.04 | 0.12 | 0.14 | 203 |
| v9 lr | 0.47 | 0.73 | 2.25 | 2.27 | 2.23 | 0.34 | 0.98 | 2.29 | 299 |
| v9 hgb | 4.94 | 4.56 | 3.31 | 3.53 | 3.31 | 1.31 | 1.96 | 3.33 | 310 |
| engines interval / point / point-jitter | 0.04 | 0.05 | 0.09 | 0.06 | 0.09 | 0.02 | 0.09 | 0.10 | 117 |
| v9 lr selftrain 1 (V11) | 0.99 | 1.57 | 5.2 | 5.23 | - | - | - | - | 301 |
| v9 V12mmr-replace | 2.1 | 3.9 | 27.5 | 28.5 | - | - | - | - | 371 |

World load from the pickle cache: 0.1 s (20,000 rows), 0.4 s practice (5 or 10 fold worlds); about 1.5 s cold.
The full 234-job baseline matrix (9 configurations x 26 tracks) took 47 s wall on 8 processes.
V12's MMR plugin first took 166 to 175 s per 20,000-row run; vectorised (self-checked against the original loop,
identical metrics), it takes about 27 s. V9 itself never needed vectorising.

## Deviations and findings

- Tracks follow the 01:40 protocol change: selection = P80 + P10; every suite world is a test track in four modes
  (`jr jt nr nt`); no `--final` gate.
- Pages for suite worlds: runs of consecutive rows (file order) with equal public date AND equal labelled status
  (A's run_v9 rule, which reproduces V9 0.8410 exactly); for `-j` worlds computed after re-dating.
- Facts are keyed (subject, attribute) through A's alias map; V5/V9 group by exp.py's typed key (+ kind, dim).
  Facts whose value exp.py cannot parse would be dropped and counted (`world_stats`); none on the gold or B forms of dev, diag, cal, sealed, syn.
  A row whose form is empty: V5 says unsure (exp.py crashed), V9 says true (empty product), the engines unsure.
  B forms have 0 to 2 such rows per world.
- V12 port: ties in MMR relevance are broken by date-sorted position (exp.py: row order). V12mmr P80 0.9040 vs
  published 0.905; V12mmr-replace and every other gate match.
- V9 confidences for 'true' can fall below 0.5 when the chosen threshold is 0.3 or 0.4; the harness accepts [0, 1].
- V9 refit fails on `Spilot-*r` and `Sprac-*r` (their public labels are all `true`, one class); transfer works.
- Suspicious, worth the families' attention: V9-LR scores 0.929 accuracy on `Sdev-jr` but 0.841 on `Sdev-nr` and
  0.832 on `Sdev-jt`. With intervals kept, every anchor sits on a change point, so anchors' bracket features look
  unlike targets'; jitter makes anchors resemble targets. Transfer from practice drops it to about always-true
  (points 0.664 vs 0.667). V12mmr-replace transfers better (`Sdev-jt` points 0.829).
- The point engine on `Sdev-jr` (0.7395) is far below V9 refit (0.929): on dense synthetic anchors a learned
  bracket model beats the latest-anchor rule.
