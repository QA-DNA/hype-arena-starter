# Evaluation-suite runs: our solution on the teammate's synthetic suite

- Status: active (worker D still running at 23:00 EET, 2026-10-28; everything else done)
- Human owner: Edi (mogaeduard)
- Agent role, if used: orchestrator plus four analysis workers (A scorer and engine, B practice-trained extractor,
  C suite-trained extractor, D real-practice transfer)
- Branch and checkout: `main` in the primary checkout; workers wrote only to `/tmp/veridyct-evalsuite/`
- Base commit: `3212291`
- Authorized scope and paths: measurement only; `labs/evaluation-suite-runs/`, `docs/research/evaluation-suite-results.md`,
  this handoff. No Rust, organizer files or other labs changed.
- Acceptance criteria: label accuracy of our best pipeline on every suite world, with held-out discipline, plus the
  real-practice transfer check.

## Delivered change

Results and verdict in [the results document](../research/evaluation-suite-results.md); scripts, logs and worker
reports in [labs/evaluation-suite-runs](../../labs/evaluation-suite-runs/README.md).

## Verification

- `A/score.py` reproduces the suite's always-true baseline (0.8335 / 0.3031 / 0.3333) on dev, cal and sealed.
- Gold forms + interval engine: 1.0000 on every main world, also under alias, unit and version-format perturbations.
- B (practice-trained, cal and sealed never inspected before the final run): 0.9962 cal, 0.9945 sealed.
- C (suite-trained, cal and sealed never in training): 1.0000.
- Not run: `cargo xtask check` (no Rust toolchain on this Mac; no Rust changed); the suite's own `bench.py` (not available).

## Where everything is

- Committed: scripts, result logs (`results/*.jsonl`), reports.
- Not committed (generated outputs): forms, predictions, C's models. Preserved with every other scratch directory of
  the night (embedding lab, reverse-engineering, competitor recon notes, venvs, model caches) in
  `~/veridyct-scratch-20261028/` as APFS clones of `/tmp`. Restore after a reboot with
  `bash ~/veridyct-scratch-20261028/RESTORE.sh` (clones everything back to `/tmp` so absolute paths work again).
- Data: `/Users/mogaeduard/Downloads/evaluation-data` (and the zip `veridyct-evaluation-data-v3.zip`), outside the repo.

## Open questions and next step

1. Worker D: B's extractor on the real `data/practice.csv` under page-grouped 5-fold CV (every practice-derived table
   restricted to training folds), top error classes, then V9 end to end with extracted versus gold forms under R80 and
   R10. Its partial outputs are in `/tmp/veridyct-evalsuite/D/` and `results/D.jsonl`. If it was interrupted, rerun
   from `labs/evaluation-suite-runs/D/run_cv.py` and the `e2e*.py` scripts, then fill the "Real practice" section of the
   results document.
2. Fix the V9 `decide()` dtype bug (`labs/kb-experiments/v9.py:128`, `v12.py:356`: `'unsure'` stored as `'unsur'`) and
   rerun the published V9/V12 commands to confirm their numbers are unchanged.
3. Team decision: port B's extractor (Python, about 600 lines of rules plus a TF-IDF scorer) to Rust, or ship it some
   other way, before the 11:00 freeze.
