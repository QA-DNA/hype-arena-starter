# Worker A: scorer, truth engine, reasoning ceiling (evaluation suite)

All numbers are hidden targets only (rows with an empty public label). Tools and usage:
`/tmp/veridyct-evalsuite/A/USAGE.md`. Raw lines: `/tmp/veridyct-evalsuite/results/e2e.jsonl`
(tag, engine, world, metrics incl. slices). Python 3.12 venv, stdlib only for the engine.

## 1. Scorer sanity gate (always-true)

| world | accuracy | macro-F1 | balanced acc | points/row |
|---|---:|---:|---:|---:|
| dev | 0.8335 | 0.3031 | 0.3333 | 0.6669 |
| cal | 0.8335 | 0.3031 | 0.3333 | 0.6669 |
| sealed | 0.8335 | 0.3031 | 0.3333 | 0.6669 |

Matches HISTORICAL-RESULTS.md (83.35%, 0.3031, 0.3333). Balanced targets (diag, pilot,
ext*) give 0.333-0.335 accuracy and negative points (-0.33/row).

## 2. Gold adapter

`forms/gold/<world>.jsonl` = `gold/labeled.csv` forms + `rows.jsonl` validity_qualifier;
`forms/gold-nointerval/` = same with interval null. How validity_qualifier is populated
(checked on every world): it is set exactly on the visible "From X through Y, ..." anchors
(dev 1,432; cal 1,439; sealed 1,460; diag 1,442; synth 1,398; prac 632; pilot 166;
ext 62-72), all labelled true, row date == interval start in 100% of them, and it equals
the gold interval of every atom in the row. It is null on every target and on every
point anchor. 3 targets (cal 2, diag 1) contain a "from ... through" phrase but no
qualifier: an incidental phrase, not a validity interval. clean = dev gold (ablation.json),
same ids. The half-open convention needs no conversion (end = day after "through").

## 3. Ceiling: gold forms + interval engine

| world | n | accuracy | macro-F1 | false P / R | unsure P / R | points/row | ECE |
|---|---:|---:|---:|---|---|---:|---:|
| dev | 18,103 | 1.0000 | 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 | 0.0060 |
| cal | 18,103 | 1.0000 | 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 | 0.0061 |
| sealed | 18,103 | 1.0000 | 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 | 0.0060 |
| diag | 4,103 | 1.0000 | 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 | 0.0072 |
| synth | 18,103 | 1.0000 | 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 | 0.0061 |
| clean | 18,103 | 1.0000 | 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 | 0.0060 |
| extdev / extcal / extsealed | 334 each | 1.0000 | 1.0000 | 1.0000 / 1.0000 | 1.0000 / 1.0000 | 1.0000 | 0.007 |
| pilot | 334 | 0.3922 | 0.2838 | 1.0000 / 0.0991 | 0.3535 / 1.0000 | 0.3922 | 0.0057 |
| prac | 1,265 | 0.3866 | 0.3999 | 1.0000 / 0.4324 | 0.0324 / 1.0000 | 0.3866 | 0.0054 |

Zero errors on dev, cal, sealed, diag (all comparison operators), synth, clean and ext*.
Residual error class (pilot and prac only, all of them): `answerability = oracle_only`
targets, i.e. the world gives no visible anchor for that slot at that date (the GUIDE says
small pilots have an intentionally incomplete evidence budget). The engine says unsure.
- pilot: 203 = 103 gold true + 100 gold false. Examples: `r-ae3b37be8a68dbc42c8482`
  "The soc2 audit start for Hooly is before 1 March 2025." (true, no evidence ids);
  `r-afbdcb62ad79ee566045f4` "Chrome's stable version is no newer than 22.23.3." (false).
- prac: 776 = 671 gold true + 105 gold false. Examples: `r-10b811fc6df839e6c936db`
  "The price of Hooly Pixel 9 is €429." (true); `r-f76ce9238df901e30e9da5`
  "Hooly Chrome's stable version is v26.6.0." (false).
On their answerable targets (pilot 131, prac 489) accuracy is 1.0000.

## 4. Point-engine gap (the competition-like ablation)

| world | interval engine acc / pts | point engine acc / pts | point-jitter acc / pts | gold-nointerval + interval engine acc |
|---|---|---|---|---:|
| dev | 1.0000 / 1.0000 | 0.9795 / 0.9589 | 0.7395 / 0.4790 | 0.0371 |
| cal | 1.0000 / 1.0000 | 0.9795 / 0.9589 | 0.7246 / 0.4492 | 0.0317 |
| sealed | 1.0000 / 1.0000 | 0.9795 / 0.9589 | 0.7571 / 0.5141 | 0.0355 |
| diag | 1.0000 / 1.0000 | 0.6666 / 0.3332 | 0.5788 / 0.1577 | 0.3497 |
| synth | 1.0000 / 1.0000 | 0.9795 / 0.9589 | 0.7767 / 0.5534 | 0.0271 |

- point (spec engine; macro-F1 0.653 on dev/cal/sealed, false P/R 0.93/1.00, unsure R 0):
  the only errors are the 372 explicit-unknown targets per main world (2.05%; diag 1,368).
  It never says unsure because every slot has a true anchor. Every true/false target is
  right because each interval anchor is dated exactly on its interval start (100%), so
  "latest true anchor at or before d" reconstructs the timeline perfectly. Error classes on
  dev: unsure->false 149+41, unsure->true 139+43 (e.g. `r-a6ae1451592594040532eb`
  "Hooly Q3 2026 Results' guidance is €18,941,033." on 2025-12-25: unknown before
  publication, the engine borrows the later value).
- point-jitter (extra ablation, my addition): same engine, but each interval anchor is
  dated on a fixed pseudo-random day inside its interval, like a real point statement.
  dev 0.7395 acc, 0.479 pts/row, false precision 0.36: 4,167 true targets become false
  (the stale previous-period value is used before the period's anchor date). This is the
  more honest estimate of how much the suite's change-point-aligned anchors help.
- gold-nointerval + interval engine: collapses to unsure (coverage 1.7%), as expected:
  without intervals only same-day evidence exists. gold-nointerval + point = point.

## 5. Engine robustness (extra)

`perturb.py` rewrites gold forms (both anchors and targets, independently) into equivalent
variants an extractor might emit: lexicon aliases or upper-case subjects, spaced
attributes, GB->MB, TB->GB, h->min, week->day, year->month, plural counted nouns, currency
symbols, `per: monthly`, `v`-prefixed and zero-extended versions, lower-case names, string
percents. Ceiling unchanged: 1.0000 on dev, cal, sealed, diag, extdev (`gold-perturbed`).

## 6. Confidence

Raw confidence = evidence strength (interval cover 0.995, same-day point 0.97; point engine
0.6 + 0.39 exp(-gap/120 days); x0.7 on conflicting anchors) x assertion conf x row conf;
false rows take the strongest false atom, true rows the product. ECE (10 bins): interval
engine 0.005-0.007 on every world. `calibrate.py` fits isotonic on dev targets and applies the same
fit elsewhere: point engine ECE cal/sealed 0.146/0.144 -> 0.0010/0.0005; point-jitter
0.128/0.099 -> 0.027/0.028. The dev fit does not transfer to the balanced ext worlds
(point engine ECE 0.20-0.22 -> 0.30-0.31).

## 7. V9 comparison (gold forms, trained on each world's anchors)

`v9/run_v9.py` runs a copy of `labs/kb-experiments/v9.py` + `exp.py` (only DATA patched):
anchors are the labelled pages, targets the hidden ones, model `lr` (LR + isotonic,
inner GroupKFold), forms from `forms/gold` (V9 uses dates only, never intervals).

| world | accuracy | macro-F1 | bal. acc | false P / R | unsure P / R | points/row | ECE | s |
|---|---:|---:|---:|---|---|---:|---:|---:|
| dev | 0.8410 | 0.3411 | 0.3521 | 0.9533 / 0.0541 | 0.0065 / 0.0027 | 0.6904 | 0.149 | 8.3 |
| cal | 0.8391 | 0.3353 | 0.3492 | 0.8397 / 0.0496 | 0.0000 / 0.0000 | 0.6796 | 0.149 | 8.8 |
| sealed | 0.8385 | 0.3263 | 0.3449 | 0.9892 / 0.0348 | 0.0000 / 0.0000 | 0.6770 | 0.156 | 5.4 |

Barely above always-true (0.6669 pts/row). Training facts are change-point anchors (true
although the previous/next anchor disagrees) plus only 127-146 one-atom false anchors, so the
bracket features learned on anchors do not transfer to mid-interval targets. Not runnable on
prac/pilot (no false anchors: LR sees one class).
Side finding in the original code: `decide()` (`labs/kb-experiments/v9.py:128`, same
pattern at `v12.py:356`) assigns `'unsure'` into a `<U5` numpy array, which stores
`'unsur'`. Every band-based unsure prediction is therefore wrong in its own metrics, which
biases the threshold search to band 0 (all published V9 runs chose band 0.0; unsure column
0). My wrapper maps `'unsur'` back to `unsure` (173 / 27 / 0 rows on dev/cal/sealed).

## 8. Runtime

Truth engine (pure Python, single thread; OMP/MKL/OPENBLAS = 2, unused), Apple M5 Pro:
0.14-0.16 s engine time per 20k-row world inside e2e; 0.17-0.20 s wall for `truth.py`
alone incl. interpreter start, peak RSS 63 MiB; scoring 0.22 s wall. V9: 5-9 s per world.

## 9. Not done / limits

- The interval engine uses negative evidence only from one-atom false point anchors on the
  exact date; false/unsure interval anchors and multi-atom false anchors are not used (none
  exist in these worlds).
- The ceiling uses gold forms for targets too: it measures reasoning, not extraction.
- point-jitter, perturbation and isotonic runs are additions beyond the brief.
- `clean` is scored with dev gold metadata, so its `has_distractor` slice describes the dev
  text (asides were removed from clean).
