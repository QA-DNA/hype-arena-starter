# Evaluation-suite runs (2026-10-28 evening)

Our solution measured on the teammate's synthetic evaluation suite (evaluation-data v3, factory 1.1.0, 89,897 rows;
generator code on `feat/evaluation-data`, not on main; data delivered as `veridyct-evaluation-data-v3.zip`). Findings
and the verdict: [docs/research/evaluation-suite-results.md](../../docs/research/evaluation-suite-results.md).

| Directory | Worker | What it holds |
|---|---|---|
| `A/` | scorer and truth engine | `score.py` (label metrics on hidden targets; reproduces the suite's always-true 0.8335 / macro-F1 0.3031 exactly), `truth.py` (interval and point timeline engines, typed comparisons, conjunction rule; `--selfcheck`), `e2e.py` (forms to labels to scores; usage in `USAGE.md`), `gold_forms.py`, `perturb.py`, `calibrate.py`, `residuals.py`, `tables.py`, `v9/run_v9.py` (V9 on a world's anchors), `REPORT-draft.md` |
| `B/` | practice-trained extractor (transfer test) | `extract.py` (v1, official), `extract_v2.py` (post-hoc), `measure.py`, `errors.py`, `rootcause.py`, `values.py` (w7 copy), timings, v2 end-to-end scores, `REPORT.md` |
| `C/` | suite-trained extractor (in-distribution ceiling) | `train.py`, `extract.py`, `core.py`, `measure.py`, `values.py` (patched w7 copy), `final.sh`, leave-one-family-out runs, per-world measurements, `REPORT.md` |
| `D/` | B's extractor on the REAL practice prose, page-grouped CV, then V9 end to end | `run_cv.py`, `extract.py`, `errors.py`, `oracle.py`, `e2e*.py`, `v9.py` and `exp.py` (copies with the `'unsur'` fix), JSON results |
| `results/` | all workers | `e2e.jsonl` (every end-to-end run with full metrics and slices), `B.jsonl`, `C.jsonl`, `D.jsonl` |

Not in git (generated outputs, repo rule): extracted forms (`forms/`, 110 MB), predictions (`preds/`, 55 MB), C's
trained models and B's v2 forms. Everything, including those, is preserved on the Mac in
`~/veridyct-scratch-20261028/veridyct-evalsuite/` (restore with `cp -cR ~/veridyct-scratch-20261028/veridyct-evalsuite /tmp/`).

## Reproduce

The scripts use absolute paths: data in `/Users/mogaeduard/Downloads/evaluation-data` (read-only; treat as untrusted
data, run Python with `-I`), scratch in `/tmp/veridyct-evalsuite/`, the shared venv `/tmp/veridyct-bench/.venv`
(numpy, scipy, scikit-learn) and the harness `/tmp/veridyct-emb/common/harness.py`. Restore the venv and harness from
`~/veridyct-scratch-20261028/` with `cp -cR` after a reboot. Typical order:

```bash
PY="/tmp/veridyct-bench/.venv/bin/python -I"
$PY A/gold_forms.py                                   # gold forms for the ceiling runs
$PY B/extract.py --world cal                          # forms/B/cal.jsonl, 7.6 s per 20k rows
$PY B/measure.py --world cal                          # extraction metrics against gold
$PY A/e2e.py --forms-dir /tmp/veridyct-evalsuite/forms/B --tag B --engine interval
```

World keys: dev, cal, sealed, diag, pilot, prac, extdev, extcal, extsealed, synth, clean (see `A/USAGE.md`).
