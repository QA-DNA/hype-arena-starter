# KB experiments on practice

Python lab that measures knowledge-base variants on `data/practice.csv`, using the `form`
column as the KB input. It backs the numbers in
[the knowledge base research](../../docs/research/knowledge-base.md). It is not solver code
and is not part of the competition image.

- `exp.py`: data facts, the as-of test, variants V0 to V8 and the metrics.
- `v9.py`: per-fact bracket-feature models V9 to V11 (imports `exp.py`).
- `v12.py`, `copies.py`: independent-evidence features (V12pages, V12mmr, V12mmr-replace) and the copied-lie stress
  test; `copies.py` is loaded only through the default-off `KB_COPY` env hook in `exp.py`. Report: `REPORT_v12.md`.
- `results_v0_v8.txt`, `results_v9.txt`, `results_v12.txt`: the recorded outputs, with confusion matrices.
- `diagnostics/`: the scripts behind the error analysis in the report.
  - `cat.py`: label counts by before, same-day and after anchor match.
  - `ana.py`: the same table split by whether a match exists at all, plus the count of false
    rows on pages with two or more false rows (186 of 277).
  - `asof2.py`: as-of carry-forward accuracy after the 2026-09-03 cut, by stable and volatile key
    and by value kind.
  - `fail.py`, `fail2.py`, `fail3.py`: V9 error examples, per-row feature dumps and per-feature
    label counts.
  - `dbg.py`, `dbg2.py`: early debugging of V2 misses (`dbg2.py` evals its first argument as the
    parameter dict, so pass only your own input).
  - `run2.txt`: an early partial run of V3sel to V5, superseded by `results_v0_v8.txt`.

Pages are inferred as runs of consecutive ids that share a date. Hidden pages lose their labels
but keep their facts as unlabelled votes; a row's own page never counts as evidence for it.
R80 is 5-fold GroupKFold by page; R10 is 10 seeded splits with 10% of pages labelled.

```sh
uv venv --python 3.12 .venv-kb
uv pip install --python .venv-kb/bin/python -r labs/kb-experiments/requirements.txt
cd labs/kb-experiments
../../.venv-kb/bin/python exp.py            # everything, about 1 to 2 minutes
../../.venv-kb/bin/python exp.py V0 V5      # a subset
../../.venv-kb/bin/python v9.py             # V9 to V11, about 80 seconds
../../.venv-kb/bin/python v12.py            # V12 + stress test, about 40 seconds; v12.py base|lie|control|mixed for one scenario
PYTHONPATH=. ../../.venv-kb/bin/python diagnostics/cat.py   # diagnostics import exp.py and v9.py
```

Verified 2026-10-28 with Python 3.12, numpy, scipy and scikit-learn 1.9.1: `exp.py V0 V5`
reproduced the recorded rows exactly. V9 and V11 features were designed after reading R80
error examples, so their numbers are optimistic until a holdout the features never saw
confirms them.
