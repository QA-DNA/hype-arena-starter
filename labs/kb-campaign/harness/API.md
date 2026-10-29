# KB campaign harness: API

Python: `$KBC/.venv/bin/python -I` (3.12, numpy, scipy, scikit-learn; no other packages). Everything lives in
`$KBC/harness/`; it imports relative to its own directory, so the folder can be copied anywhere.

## Paths (environment variables, Mac defaults)

| Variable | Default | Used for |
|---|---|---|
| `KBC_ROOT` | the parent of `harness/` | `cache/` (pickled parsed worlds) |
| `KBC_PRACTICE_DIR` | `<practice data dir>` | `practice.csv`, `lexicon.json` |
| `KBC_SUITE_DIR` | `~/Downloads/evaluation-data` | suite worlds (public + gold for scoring) |
| `KBC_EVALSUITE_DIR` | `/tmp/veridyct-evalsuite` | `forms/gold`, `forms/B` |
| `KBC_RESULTS_DIR` | `$KBC_ROOT/results` | `<worker>.jsonl`, `<worker>.errors.jsonl` |

Parsed worlds are pickled to `$KBC_ROOT/cache/<world>-<forms>-<mode>-<hash>.pkl`; the hash covers the input files,
`world.py` and the vendored `truth.py`, so a data or parser change rebuilds it. Writes are atomic (`os.replace`).
A 20,000-row world loads in about 0.1 s from cache, about 1.5 s cold.

## Tracks

| Track | World | Labelled (evidence + training) | Scored | Role |
|---|---|---|---|---|
| `P80` | practice, gold `form` | 4 of 5 page folds (GroupKFold(5) over pages) | 5th fold, pooled over folds | **selection** |
| `P10` | practice | 10% of pages, seeds 0..9 (exp.py) | the rest; metrics = mean over seeds (+ `metrics_std`) | **selection** |
| `S<w>-<m><f>` | suite world `w`, gold STATED forms | the world's public labels | its targets | test |
| `X<w>-<m><f>` | same, extractor-B forms | same | same | test (robustness) |

- `w`: `dev diag cal sealed syn pilot prac extdev extcal extsealed` (`syn` = realistic-synthetic-20000).
- `m`: `j` = anchors as point statements: every labelled row with an interval is re-dated to A's fixed
  pseudo-random day `start + sha1(id) % (end - start)` inside its half-open interval, its interval phrase is
  stripped from the text, and all intervals are dropped (A/truth.py `point-jitter`, verified identical).
  `n` = intervals kept (`world.interval[i]`), public dates unchanged.
- `f`: `r` = refit: the harness calls `run(world)` (fit on the world's own labelled rows, predict).
  `t` = transfer: `fit(practice world, every row labelled)` once, then `predict(world)`; the suite world's
  labelled rows are still visible as evidence anchors, but nothing is refitted on them.
- Selection score (leaderboard): mean arena points per row over P80 and P10; tie-break lower ECE, then higher
  macro-F1 (means over the two). Suite tracks are reported as separate test columns.

**Pages** (public information only): a page is a maximal run of consecutive rows (practice: numeric id order;
suite: file order) with the same date and the same labelled status. Practice: identical to exp.py (291 pages).
Suite: identical to A/v9/run_v9.py; for `-j` worlds pages are computed on the re-dated dates, so the original
interval start leaves no trace.

**No gold in a World.** `world.label[i]` is `None` for every unlabelled row. Gold labels of the scored rows live in
the `Track` object that `run.py` keeps; facts are the STATED forms (gold/labeled.csv `form` via
`forms/gold/<w>.jsonl`), never the expected values (`check_leak.py` verifies both). Unlabelled rows keep their facts.

## World (`world.py`)

Rows `i = 0..n-1`, facts flat `n = 0..n_facts-1`.

| Attribute | Type | Meaning |
|---|---|---|
| `name`, `static_key` | str | e.g. `practice`, `Sdev-j`, `Xcal-n`; `static_key` identifies the label-free content (use it as a cache key for label-free plugin data such as TF-IDF) |
| `ids`, `text` | list[str] | |
| `date` | int64[n] | ordinal day (`datetime.date.toordinal`) |
| `page` | int64[n] | page id, `0..n_pages-1` |
| `interval` | list | `(start, end)` half-open ordinals or `None` (only `-n` worlds have intervals) |
| `facts` | list[list[Fact]] | stated atoms per row (an unreadable value is dropped and counted in `stats`) |
| `labelled` | bool[n] | rows whose label the variant may use |
| `label` | object[n] | `'true'/'false'/'unsure'` where labelled, else `None` |
| `lexicon` | dict | the world's public lexicon |
| `fidx` | int64[n_facts, 2] | (row, position) of each flat fact; `frow = fidx[:, 0]`; `flat[n]` is the Fact |
| `fstart` | int64[n] | flat index of row i's first fact: fact (i, j) is `fstart[i] + j` |
| `obs` | dict | `(subject, attribute)` -> `[(row, pos)]` sorted by date (stable) |
| `obs_typed` | dict | `okey` -> same; exp.py's observation key (same kind and unit dimension) |
| `stats` | dict | jitter counts, dropped facts, rows without facts |

`World.with_labels(labelled, label)` returns a copy with another mask (labels outside it are discarded).

`Fact`: `key` (subject, attribute) resolved through lexicon names and aliases, `okey` = key + (kind, dim), `kind`,
`op` (`eq gt lt ge le`), `value` (stated raw value), `raw` (the value dict), `dim`, `canon`/`lo`/`hi`
(exp.py semantics; `lo`/`hi` inclusive range, `None` for non-ordered kinds), `acanon` (A/truth.py exact canonical
value, `None` if unreadable). Methods `same(o)`, `consistent(o)` (exp.py V5 interval overlap).
A/truth.py is importable as `import truth` (vendored, unchanged) for `canon`, `compare`, `Evidence`.

## Variant

A module (in `harness/variants/`, or any dotted module or `path/file.py`) exposing a class (default `Variant`,
or `module:Class`) built from keyword params:

- `predict(world) -> (labels, conf[, fact_scores])` or `api.Prediction(labels, conf, fact_scores=None)`:
  `labels` object array of `'true'/'false'/'unsure'` for all `world.n` rows, `conf` float array: confidence of the
  returned label in [0, 1] (normally 0.5..1), NaN on unsure (the harness enforces this), `fact_scores` optional
  float array aligned with `world.fidx`.
- optional `fit(train_world)`: learn from `train_world.labelled` / `train_world.label`.
- optional `run(world)`: refit-and-predict on one world. `api.Base` gives `run = fit + predict`.
- Harness calls (`api.run_variant`): P80, P10, `..r`: `run(world)` if defined, else `fit(world)` + `predict(world)`.
  `..t`: `fit(practice)` then `predict(suite_world)`; a class without `predict` fails on `..t` tracks.
- A fresh instance is built for every fold. Instances may record `self.chosen` (list), saved with the result.

Example (`harness/variants/example_majority.py`, runnable):

```python
"""Example: a fact is true iff the latest labelled-true observation of its key at or before the row date
(other page) states a consistent value; no evidence -> fall back to the training true rate."""
import numpy as np
from api import Base, Prediction


class Variant(Base):
    def __init__(self, fallback="true"):
        self.fallback = fallback

    def predict(self, world):
        lab = np.full(world.n, self.fallback, dtype=object); conf = np.full(world.n, 0.6)
        ps = np.full(world.n_facts, np.nan)
        for n, (i, j) in enumerate(world.fidx):
            f = world.flat[n]
            prev = [(r, q) for r, q in world.obs_typed[f.okey] if world.label[r] == "true"
                    and world.page[r] != world.page[i] and world.date[r] <= world.date[i]]
            if prev:
                ps[n] = float(f.consistent(world.facts[prev[-1][0]][prev[-1][1]]))
                if ps[n] == 0: lab[i], conf[i] = "false", 0.7
        return Prediction(lab, np.where(lab == "unsure", np.nan, conf), ps)
```

## Feature plugins (for learned models such as V9)

`func(world[, role=None]) -> float array (world.n_facts x k)` (1-D is one column). `role` (object[n],
`'true'/'false'/''`, labelled rows hold their label) is passed only during self-training rounds, and only if the
function has a `role` parameter. A plugin must use only `world` (labels only of labelled rows). Reference it as
`"module:func"` (`harness/variants/<module>.py`, a dotted module, or `path/file.py:func`); default name `features`.
`api.feature_block(world, spec, role)` calls and shape-checks one. The plugin must return the same `k` columns on
every world (transfer tracks call it on practice and on the suite world).

V9 (`variants/v9.py`) params: `model` (`lr`, `hgb`, `lrC<float>`), `stage2` (True), `calib` (True),
`legacy_unsur` (False; True = the published `<U5` decide()), `select` (`mf1` published, `points`),
`selftrain` (0; 1 = V11), `hi`/`lo` (0.95/0.2), `extra_features` (list of plugin specs, appended after the 45 base
columns, before the stage-2 page-suspicion columns), `drop_features` (base column indices; with `hgb` keep
column 21, the categorical kind index, or the categorical index shifts). Helpers to reuse: `v9.fact_feats(world,
role)`, `v5.fact_scores(world, params)`, `v5.groups(world)` (per okey: flat indices, consistency matrix).

## Running

```bash
H=$KBC/harness; PY="$KBC/.venv/bin/python -I"
$PY $H/run.py --variant v9 --variant v9='{"model": ["lr", "hgb"], "selftrain": [0, 1]}' \
    --variant my_module='[{"a": 1}, {"a": 2, "extra_features": ["my_feats:features"]}]' \
    --tracks P80,P10 --jobs 4 --worker F3
$PY $H/run.py --variant v9 --tracks Sdev-jt,Sdev-jr,Scal-jt,Ssealed-jt,Ssyn-jt,Sdev-nt --jobs 8 --worker F3
$PY $H/leaderboard.py [--sort selection|P80|P10|<track>] [--tracks Sdev-jt,...] [--worker F3]
$PY $H/run.py --variant v9 --tracks P80 --dry      # list jobs only
```

- `--variant NAME[=GRID]`, repeatable. GRID JSON: a dict `param -> list of values` (cartesian product; a scalar
  is one value, so a list-valued param such as `extra_features` needs a list of lists) or a list of param dicts.
- `--jobs N` (default 2): a spawn process pool, one fresh process per job (`maxtasksperchild=1`) so peak RSS is per
  job; safe to 40+ per invocation; each job sets `OMP/OPENBLAS/MKL/VECLIB_NUM_THREADS=1` unless already set. Worlds
  load from the pickle cache, so N processes do not re-parse.
- Output: one JSON line per (variant, params, track) appended to `$KBC_RESULTS_DIR/<worker>.jsonl` (one O_APPEND
  write per line, safe across concurrent invocations): `ts worker variant params track n_scored metrics`
  (`metrics_std` for P10, `fold_mean` for P80) `runtime_s` (variant time, summed over folds) `load_s peak_rss_mb
  src_hash` (sha256 of the variant source plus plugin sources, 12 hex) `host n_folds world_stats chosen`.
  Failed jobs go to `<worker>.errors.jsonl` with the traceback and exit status 1.
- `metrics` (`metrics.compute(gold, pred, conf)`, the one function for every track): `n accuracy macro_f1 points
  points_per_row ece10 brier false_precision false_recall unsure_precision unsure_recall coverage confusion`.
  Points +1 right, -1 wrong true/false, 0 unsure; ECE 10 bins over decided rows (A/score.py); Brier over decided rows.

## Known behaviour and caveats

- `Spilot-*r` and `Sprac-*r`: the public labels of these small worlds are all `true` (they hide evidence on
  purpose, `oracle_only`), so a learned variant that needs two classes (V9) fails there in refit mode; use `..t`.
- Transfer tracks fit on practice (its own lexicon) and predict on a suite world (the suite's public lexicon).
  Fact keys are resolved per world, so a variant must not carry key-specific state from practice to the suite.
- `-j` text: the leading "From X through Y," phrase of every re-dated anchor is removed (`world.stats`
  counts rows where a from/through pattern remains; the only hit, in cal, is natural prose after the stripped
  phrase). Variants must not recover anchor intervals from anything else.
- V12 `mmr` features cost about 25 s per 20,000-row run (vectorised MMR, identical results); V9 itself takes about 2 s.
- P80 `metrics` are pooled over the 5 folds; `fold_mean` holds exp.py's mean over folds (the published numbers).
