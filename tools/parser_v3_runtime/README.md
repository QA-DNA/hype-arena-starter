# Parser v3 runtime evaluation adapter

Standalone Rust workspace bridging public JSONL `id,document_id,text,context`
to the independent evaluator's AST, status, NNF assertion leaves and notes.
The default `program` backend calls the production `ClaimParser`, which calls
`ClaimContext`, `SchemaParser` and `ProgramParser` with the production owner guard.
`schema` runs the current binder with the same context preprocessing.

Value proposals come from the existing selected-v2 Rust `Grammar`, compiled
with only the public lexicon and no extra names. No proposal is supplied by
gold, case family, opaque ID, private world or expected AST. Optional `--model`
loads the actual frozen selected-v2 ONNX model with hash validation and one CPU
thread. It supplies neural owner/attribute proposals; it does not supply truth.
No practice-form reuse, runtime LLM or network is used.

Build with Rust 1.90, using `veridyct:dev`, the shared registry volume
`veridyct-mvp-registry` and dedicated target `veridyct-parser-v3-runtime-target`:

```text
cargo build --locked --offline --release --manifest-path tools/parser_v3_runtime/Cargo.toml
cargo test --locked --offline --manifest-path tools/parser_v3_runtime/Cargo.toml
cargo clippy --locked --offline --manifest-path tools/parser_v3_runtime/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path tools/parser_v3_runtime/Cargo.toml -- --check
```

The binary accepts `--lexicon FILE --input JSONL --output NEW_FILE`, optional
`--metrics NEW_FILE`, `--backend program|schema`, `--model DIRECTORY`, and
`--variant none|reverse_candidates|shuffle_candidates|replace_candidate_ids|inject_untrusted_gold_fields|reverse_document_order`.
Model inference needs `ORT_DYLIB_PATH` pointing to the frozen ONNX Runtime library.
The baseline image stores both under `/opt/veridyct-extractor/`.

Each independent input starts with fresh context. Prior texts are replayed only
when enabled and the two document IDs match. IDs and dates never become grammar
features; context receives fixed correlation IDs and a constant unused date.
The limits are 65,536 current-text scalars, 64 prior texts, 262,144 prior-text
scalars, 4,096 candidates, 2 MiB per JSONL line and 100,000 rows per invocation.
The parser supplies its additional depth/node bounds. Output files refuse overwrite.
`proposal_sha256` hashes prepared text, candidates and native proposals, excluding
IDs; it enables a real paired comparison without exposing private scoring inputs.

Run the development bundle from the repository root:

```powershell
py -3.14 -X utf8 tools/parser_v3_runtime/evaluate.py --bundle PATH_TO_DEVELOPMENT_BUNDLE --output artifacts/parser-v3-runtime/new-run
# Actual frozen neural inference, copied from the image:
py -3.14 -X utf8 tools/parser_v3_runtime/evaluate.py --bundle PATH_TO_DEVELOPMENT_BUNDLE --output artifacts/parser-v3-runtime/new-native-run --native-image veridyct:merged-million-baseline
```

The wrapper runs six nuisance variants, records source/model/binary hashes,
mounts only public inputs plus its own output and the frozen model into a
network-disabled, read-only, 2 CPU / 6 GiB container, and scores only after all
predictions exist. Decimal spellings are preserved as exact numeric strings.
It retains every failed development row, expected result and actual prediction.
It refuses final bundles; the coordinator owns the separate freeze/final gate.

An optional `frozen-baseline` build feature compiles an actual preserved
`structured.rs` source snapshot named by `RUNTIME_BASELINE_SOURCE`; set
`RUNTIME_BASELINE_COMMIT` to its real Git commit. It adds backend `frozen-schema`.
The baseline source must be preserved under ignored artifacts, obtained using
`git show COMMIT:crates/core/src/structured.rs` without text transcoding.
Pass `--baseline-source FILE` to the wrapper so its source snapshot includes it.
The measured baseline is the pre-v3 binder at `22fa97b`, with the same public
grammar, native proposals and common explicit-context frontend as the candidate;
it is a parser comparison, not the historical complete solver.

The `proposals` diagnostic binary accepts `LEXICON INPUT_JSONL NEW_OUTPUT_JSONL`
and dumps independent raw grammar candidates plus actual schema/program/shared
results. It is for small bounded public diagnostic inputs; it does not score.

See the [measured handoff](../../docs/handoffs/parser-v3-runtime-evaluation.md).
