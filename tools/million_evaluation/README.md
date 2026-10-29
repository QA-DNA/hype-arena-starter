# Million-pool evaluation

This is a development benchmark harness, separate from the competition CLI.
It never trains a model. The Rust bridge calls the committed parser, schema binder,
production GBT and exact value kernel. The Python adapters add explicit supplied-note
queries with three-valued `all`/`any`/`not` logic. Neither adapter is an LLM.

The supplied pools contain synthetic combinations of public practice observations,
not a million independent facts. V2 also changes the surface grammar and moves two
pilot families to the supplied-note protocol. Report cohorts separately.

## Data boundary

`prepare` streams the archive pool. Only `input.text`, `input.date`, explicit
`input.context` and `input.evidence_policy` become inference features. Annotation
targets and metadata are written to a separate `scoring/` directory. The Docker
runner mounts **only** `features/`, its output directory and the frozen binary.
It has no network, generator, oracle, source bank, answer key or scoring mount.

Public development inputs are the organizer lexicon/practice CSV and published
field vocabulary. Matching original practice text/date pairs may reuse their public
typed annotations (NFKC, case and whitespace normalization for this source lookup).
This is disclosed development exposure, not unseen extraction.
Cached extraction never establishes that a note is available: each individual
query can use only its supplied evidence notes, with matching date and descriptor.
Missing evidence remains unknown, including when the note was parsed for another
query. Explicit ordinal bindings identify references; they do not supply facts.

`check_kernel.py` is a **test-only** differential checker. It imports the supplied
oracle to test the Rust kernel and is never imported by inference. `score` and
`compare_runs.py` may read gold after inference, solely to calculate metrics.
`diagnose.py` examines all supplied-note errors after scoring; it never changes
predictions. V2's observed errors all include an `api_version`/`version` mismatch:
some revised natural clauses omit the API qualification that the target retains.

The V2 language vocabulary contains only literal language tables extracted with
`ast.literal_eval` from the supplied renderer. Its source hash and scope are in
`v2-language.json`. Neither generator execution nor labels/recipes produce
inference rules. This renderer-aware development adaptation does **not** measure
blind generalization to new human language. The old V1 adapter remains intact so
its strict transfer failure is observable.

## Interfaces and semantics

- `protocol.py`: frozen V1 surface syntax, explicit source/date references and
  bounded recursive logic; conservative rejection of unsupported language.
- `protocol_v2.py`: opt-in V2 surface syntax. V1 inputs delegate to the original
  parser. More specific attribute phrases take precedence over generic phrases;
  an ordinary version phrase denotes `version` where that attribute exists.
- `bridge/`: isolated safe Rust workspace; `parse` and `compare` JSONL interfaces.
  `recorded` requires the literal typed value, including its metadata. Arithmetic
  comparison may convert compatible units through the committed typed kernel.
  Partial date **values** use a research-specific range comparison matching the
  note protocol; this is distinct from the production interval-predicate API.
  V1 can compare raw magnitudes from different metrics with matching value
  metadata; this follows the dataset contract, not an economic like-for-like
  interpretation. V2 replaces some such questions with separate assertions.
- `reuse_parses.py`: memoizes extraction by mode, full text, date and full explicit
  prior text. It reuses no evidence availability, labels or target structures.
- `bench.py`: streaming preparation, per-row evidence planning and scoring.
  `bench_v2.py` opts into the compatibility grammar without editing frozen V1 code.

Truth accuracy excludes `label: null` parsing-only cases and reports their count.
`unsure` is a genuine third truth class, not a null label. Macro-F1 includes all
three truth classes. `coverage` means a definitive true/false prediction; it is
**not** the fraction of rows processed. All rows are processed and scored where
their truth target exists. The strict projected AST metric includes source IDs;
it does not measure character offsets/reference spans or all pilot structures.
Source IDs can be absent from available input when a named note is withheld.

## Reproduce

Use a separate checkout based on the recorded main commit. Put extracted archives
under ignored `artifacts/`. Keep organizer files and original dataset checkers
unchanged. Validate each archive using its own full delivery checker in Linux.
V2 requires `labs/million-review/check_delivery.py`, not the older checker.

Python 3.14 and the standard library are sufficient for the host scripts. Docker
provides Linux ONNX/Rust execution; the frozen model bundle and image must already
be available as described in the [candidate handoff](../../docs/handoffs/evidence-graph-runtime.md).
The runner defaults to `veridyct:merged-million-baseline`; hashes in the measured
report identify the actual model, verifier, binary and image.

```text
py -3.14 -m unittest discover -s tools/million_evaluation -p "test_protocol*.py" -v

py -3.14 tools/million_evaluation/bench.py prepare --dataset artifacts/million-input/dataset --out artifacts/million-v1-final
py -3.14 tools/million_evaluation/run_bridge.py parse --run artifacts/million-v1-final
py -3.14 tools/million_evaluation/bench.py pairs --out artifacts/million-v1-final
py -3.14 tools/million_evaluation/run_bridge.py compare --run artifacts/million-v1-final --binary artifacts/million-runtime/bin/bridge-compare
py -3.14 tools/million_evaluation/bench.py score --out artifacts/million-v1-final

py -3.14 tools/million_evaluation/bench.py prepare --dataset artifacts/million-input-v2/dataset --out artifacts/million-v2-frozen
py -3.14 tools/million_evaluation/bench_v2.py prepare --dataset artifacts/million-input-v2/dataset --out artifacts/million-v2-final
```

For either V2 run, use the same `parse` / `pairs` / `compare` / `score` sequence as
V1. To avoid repeating identical frozen extraction, replace the parse step with:

```text
py -3.14 tools/million_evaluation/reuse_parses.py prepare --from-run artifacts/million-v1-final --to-run artifacts/million-v2-final
py -3.14 tools/million_evaluation/run_bridge.py parse --run artifacts/million-v2-final --input-name pending-requests.jsonl --output-name pending-parsed.jsonl
py -3.14 tools/million_evaluation/reuse_parses.py merge --from-run artifacts/million-v1-final --to-run artifacts/million-v2-final
```

If the pending request file is empty, create an empty
`parsed/pending-parsed.jsonl` and merge; no model invocation is required.
Do not overwrite previous runs. The scripts reject replacement of key outputs.
Preserve checksums/freeze receipts before scoring and do not tune from subsequent
errors while reporting a result as frozen.

Build the bridge in its own workspace, with the native extractor's documented
Linux prerequisites installed (the local `veridyct:dev` image contains them):

```text
cargo build --release --locked --offline --manifest-path tools/million_evaluation/bridge/Cargo.toml
cargo clippy --locked --all-targets --offline --manifest-path tools/million_evaluation/bridge/Cargo.toml -- -D warnings
cargo test --locked --offline --manifest-path tools/million_evaluation/bridge/Cargo.toml
```

Export the Linux executable under ignored `artifacts/million-runtime/bin/` and
record its hash. The measurement preserved separate parse and comparison binaries;
the only added Rust behavior between them concerns date-value comparison.
The final source supports both commands. Root competition dependencies are unchanged.

Paired scoring uses stable IDs only to align related rewrites. Exact unchanged-input
overlap is additionally checked by SHA-256 of the entire canonical public input:

```text
py -3.14 tools/million_evaluation/compare_runs.py --v1-dataset artifacts/million-input/dataset --v2-dataset artifacts/million-input-v2/dataset --v1-run artifacts/million-v1-final --v2-run artifacts/million-v2-final --out artifacts/million-comparison
```

Archives, raw pools, model weights, caches, binaries, per-row predictions and logs
stay ignored. Only curated conclusions, reproducible tooling and provenance belong
in version control. Do not submit this Python research harness as the Rust-only
competition application.
