# Worker A tools: scorer, truth engine, e2e runner

Python: `/tmp/veridyct-bench/.venv/bin/python -I` (stdlib only). Scripts live in
`/tmp/veridyct-evalsuite/A/`; run them from any cwd with absolute paths.

## e2e (forms -> truth engine -> predictions -> score -> results)

    /tmp/veridyct-bench/.venv/bin/python -I /tmp/veridyct-evalsuite/A/e2e.py \
        --forms-dir /tmp/veridyct-evalsuite/forms/<extractor> --tag <extractor> \
        [--engine interval|point] [--worlds dev,cal,sealed] [--worker B]

- Runs every world (or the `--worlds` subset) that has `<forms-dir>/<world>.jsonl`.
  World keys: dev cal sealed diag pilot prac extdev extcal extsealed synth clean.
- Writes `preds/<tag>-<engine>/<world>.csv` (id,label,confidence; targets only) and appends
  one line per world to `results/e2e.jsonl`:
  `{ts, worker, tag, engine, world, n_targets, runtime_s, forms, pred, metrics}`.
- `--worker` is recorded in each line (default: the tag). Please pass `--worker B` / `C`.
- Prints one summary line per world (accuracy, macro-F1, balanced acc, points/row,
  coverage, ECE, false P/R, unsure P/R, engine runtime).
- `--engine interval` (default): interval anchors give known values over [start,end);
  point anchors only at their own date; no known value at the target date -> unsure.
  `--engine point`: ablation that ignores intervals (latest true anchor at or before the
  date, else the earliest after). `--engine always-true --worlds ...` is the baseline.

## Forms format (one JSON line per row, anchors AND targets)

    {"id": "r-...", "assertions": [{"subject": "Hooly Pixel 10", "attribute": "base_storage",
      "value": {"kind": "quantity", "value": 130, "unit": "GB"}, "conf": 0.9}],
     "interval": ["2025-10-01", "2026-02-01"], "conf": 0.95}

- `interval` is half-open: end = the day AFTER an inclusive "through" date; `null` when the
  text states no interval. `conf` (assertion and row level) is optional, default 1.0.
- Values follow contracts/value-forms.md (kinds quantity, money, percent, date, version,
  duration, name, boolean; optional `op` in eq/gt/lt/ge/le). Subjects and name values are
  resolved through lexicon names/aliases (case and spaces ignored), so `Pixel 10` works.
  Attributes are lower-cased, spaces/hyphens -> `_`. Units convert (GB/MB, inch/cm,
  weeks/days, 12 months = 1 year); counted nouns compare singularised.
- A target missing from the forms file, or with no assertions, is predicted unsure.
  A malformed value makes that atom unknown (row unsure unless another atom is false).
  First record per id wins.

## Scorer alone

    /tmp/veridyct-bench/.venv/bin/python -I /tmp/veridyct-evalsuite/A/score.py \
        --world dev --pred my.csv [--json-out m.json]

Targets only (public label empty). Missing -> unsure; first duplicate id counts; a
confidence on an unsure row, a bad label or a confidence outside [0,1] is an error (exit).
Metrics: accuracy, macro-F1 (3 classes), balanced accuracy, per-class P/R/F1, confusion,
arena points (+1 right, -1 wrong true/false, 0 unsure), ECE (10 bins, true/false rows with
a confidence), coverage, slices (arity, has_distractor, genre, track, answerability,
value_kind, has_op). Sanity gate (always-true): acc 0.8335, macro-F1 0.3031, bal 0.3333
on dev/cal/sealed: reproduced.

## Truth engine alone

    /tmp/veridyct-bench/.venv/bin/python -I /tmp/veridyct-evalsuite/A/truth.py \
        --world dev --forms forms.jsonl --out preds.csv [--engine point]

## Added after READY (backward compatible)

- `--engine point-jitter`: point engine, but each interval anchor is dated on a fixed
  pseudo-random day inside its stated interval (closer to real point statements).
- Isotonic calibration fitted on dev targets, applied unchanged to the other worlds of a run:
  `python -I /tmp/veridyct-evalsuite/A/calibrate.py --run <tag>-<engine> [--worker B]`
  -> `preds/<tag>-<engine>-iso/`, results lines with engine `<engine>+iso`. Needs the dev
  predictions of that run. Labels never change.
- Error classes with examples (evaluator side, reads gold):
  `python -I /tmp/veridyct-evalsuite/A/residuals.py --world dev --pred preds/<run>/dev.csv`
- Markdown tables from results: `python -I /tmp/veridyct-evalsuite/A/tables.py <tag>-<engine> ...`
- Malformed records never crash the engine: a bad value makes its atom unknown, a bad
  interval is ignored, a missing/invalid `conf` counts as 1.0.
- Slices for `clean` use dev gold metadata, so `has_distractor` describes the dev text.
