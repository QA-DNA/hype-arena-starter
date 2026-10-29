# Five-split boosted verifier validation

This development-only harness compares the original checked-in MVP Random Forest,
the advanced root Random Forest and a separate portable GBT for each Mihai split.
It uses pure Rust extraction throughout. Read the [handoff](../../docs/handoffs/verifier-folds.md)
for measured results and limits. It never opens synthetic development or sealed worlds.

All snapshots, caches, requests, models and results go under ignored
`artifacts/verifier-folds/`. Root implementation files are only read, copied and
hashed; the tool never edits them. The core-only copied Cargo manifests change
only workspace membership, and retain their original manifest/lockfile bytes.
An optional Cargo registry seed is copied, giving this worker its own writable cache.

## Reproduce

Run in this isolated checkout with Docker `veridyct:dev` (Rust 1.90), host Python
3.14 and the lab's NumPy/sklearn requirements installed. The default `--integration`
and `--lab` point to the sibling `evidence-graph-runtime`. The lab scripts are copied
to the ignored snapshot and hashed before their export/parity APIs are reused.

```powershell
py -3.14 tools/verifier_folds/run.py all --seed-cargo ../evidence-verifier-lab/artifacts/verifier-lab/cargo-home
```

To resume one completed phase at a time, use `build`, `features`, `train`, `predict`,
`guards`, `report` as the positional phase instead of `all`. `stage` refuses to
overwrite an existing protocol; choose a new `--output artifacts/verifier-folds-...`
to evaluate another source snapshot. `report` is the first phase that reads heldout
targets after predictions; it never modifies training configuration or models.

```powershell
py -3.14 tools/verifier_folds/test_protocol.py
py -3.14 tools/verifier_folds/check.py
py -3.14 tools/verifier_folds/analyze_errors.py
```

The exact Docker command arrays, exit codes, durations and stderr (including Rust
peak RSS) are in `commands.jsonl` and `logs/`. Release binaries and all computation
run with `--user 0 --network none --cpus 2 --memory 6g`. These are development
containers and do not claim the official competition contract passed.

`check.py` constructs a separate foundation copy from the frozen core plus the
checked-in adapters/tooling and runs `cargo xtask test`, `cargo xtask check`,
`cargo xtask docs`, Clippy, evaluator tests and owned Rust formatting. Its outcome
is in `verification.json`; it preserves formatting failures in root-owned source.
It exits nonzero if any required foundation check fails, even when other checks pass.
`analyze_errors.py` uses already completed predictions and gold to separate empty
or inexact parsing, correct-parse verifier errors, graph routing and paired changes.
It writes `error-audit.json` and never changes a model. Run `report` again after
these commands to include their hashes in the artifact manifest.

## Partition and parsing contract

`split_assignments.csv` must assign every practice ID exactly once to train/test
for each of `random`, `bundle_group`, `template_group`, `forward_time`, `every_fifth`.
The harness keeps source order, removes every train ID and Unicode NFKC/casefold/
whitespace-normalized text shared with test, then writes separate gold-free
requests and evaluator-only targets. Model signatures cover ID/date/label/text;
provenance also includes normalized-text SHA256 lists and source/data hashes.

Fit parsing uses five fixed crossfit blocks grouped by normalized text, using
SHA256 modulo five. An Engine fitted on the other four blocks parses each hidden
fit query. Its own label/form, and every normalized duplicate, are unavailable to
that parser. For evidence features, the full cleaned training partition's proper
forms are available except the query ID and all normalized copies of its text.
This physical exclusion also covers graph features, independent of the feature
module's built-in case-insensitive checks. Empty inferred parses remain empty.

Outer tests use the full cleaned training partition. All test labels and forms are
blank, and every reported pipeline prediction comes from `Engine::predict`.
The GBT attaches through `Engine::with_boosted` and the Value-first
`BoostedVerifier::from_json` loader, preserving production graph/confidence routing.
The harness verifies identical currentRF/GBT parses, frozen export features,
sklearn/Python-portable/Rust logits and scores, and train-only evidence IDs.

The original model choice was made using only inner307 validation in the previous
paired390 diagnostic. These runs fix 120 boosting iterations, depth 2, minimum
leaf 20, learning rate 0.045, subsample 1 and seed 417. `lex.*` and `cue.*` features
are omitted; there is no class balancing, calibration fit or new search.

## Outputs and interpretation

Each split has `models/<split>.json`, `training/<split>.json`,
`predictions/<split>-originalRF.jsonl`, `-currentRF.jsonl`, `-newGBT.jsonl`.
`results.json` retains all outcomes, per-class precision/recall/F1, confusion,
accuracy, macro-F1, non-unsure coverage, log loss and multiclass Brier score.
The majority class is chosen from cleaned train counts; its probability baseline
uses empirical train frequencies. Brier is the row mean of the sum across three
classes, and log loss clips the gold probability to `[1e-15,1]`. Macro-F1 always
includes all three labels with undefined F1 zero. Confusion rows are gold.

`guards/results.json` proves that a different partition's model and a labelled
query are rejected before output creation. The GBT raw fallback is reported only
as a component diagnostic beside full Engine predictions, so graph overrides and
the confidence threshold remain visible. No result is an independent final score:
practice facts overlap and the original model selection used practice examples.
