# Schema assertion binder development tools

The staged [core module](../../crates/core/src/structured.rs) binds literal lexicon
fields to explicit subject aliases and frozen typed value proposals. This separate
Cargo workspace compiles and tests it without editing core integration files.
It uses `serde_json/arbitrary_precision`, as does the coordinator's integration.
No model training, truth lookup, network call or runtime LLM is involved.

## Build and test

```text
cargo test --locked --manifest-path tools/structured_parser/Cargo.toml
cargo clippy --locked --manifest-path tools/structured_parser/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path tools/structured_parser/Cargo.toml -- --check
py -3.14 -X utf8 -m unittest discover -s tools/structured_parser -p test_evaluate.py
cargo build --locked --release --manifest-path tools/structured_parser/Cargo.toml
```

The Rust tests cover semantics and public practice regressions. Python tests
verify the evaluator's independent decimal/operator/unit normalization.

## Parser adapter

```text
veridyct-structured-parser-tools LEXICON.json ROWS.json OUTPUT.json [METRICS.json]
```

Each input row has `id`, `text`, `candidates` and `neural`. It also accepts the
native adapter's `_extractor_candidates` and `form` field names. Labels, dates,
gold-named fields and unrelated metadata are not deserialized into the parser.
Offsets are Unicode code-point, half-open character spans. Output retains every
ID as `[{"id":...,"parsed":{"facts":[],"complete":false,"notes":[]}},...]`.
The optional metrics file records single-thread parsing time and Linux peak RSS;
these measurements exclude neural inference and value-candidate preparation.

## Released development A/B

Use only an explicitly released development directory. `prepare` reads the
public CSV; `score` opens development gold only after parser output exists.
Do not mount gold, world, context or seed files into the parser container.

```text
py -3.14 -X utf8 tools/structured_parser/evaluate.py prepare --public DEVELOPMENT/public --output artifacts/structured-parser-v3/input.json
```

Run the coordinator's native helper on that input with `--export-candidates true`
and `--output /io/native-binding.json`. The measured image was
`veridyct-native-extractor:structured-v2`. Ordinary `structured-v1` proposals
remain a separately measured baseline; they have no candidate for literal `in`.
Run the built parser on the public lexicon and native output, then evaluate:

```text
py -3.14 -X utf8 tools/structured_parser/evaluate.py score --development DEVELOPMENT --native artifacts/structured-parser-v3/native-binding.json --structured artifacts/structured-parser-v3/structured-binding.json --out artifacts/structured-parser-v3/evaluation-binding
```

`scores.json` reports exact assertion sets with exact rational physical-unit
equivalence, plus `literal_unit_exact_rows` without unit conversion. Currency
and billing channels stay separate; month/day conversion is forbidden; dates
keep precision and versions keep their written components. Gold top-level `op`
and decimal strings normalize only inside this evaluator. `errors.json` retains
every remaining extraction error. These are development extraction metrics,
not independent truth-accuracy estimates.

## Official practice paired390

Reuse the existing selected-v2 predictions rather than rerunning a padding-
sensitive network. Candidate generation uses the pinned, text-only Python
grammar and its frozen public lexicon/extra names. Gold forms and labels are
discarded before constructing parser input.

```text
py -3.14 -X utf8 tools/structured_parser/evaluate.py prepare-practice --practice data/practice.csv --ids TEST-IDS.json --frozen-predictions CPU-DEV-PREDICTIONS.jsonl --grammar FROZEN/grammar.py --bundle SELECTED-V2 --output artifacts/structured-parser-practice390/input.json
```

Run the same Rust adapter on that input and the official public lexicon, then:

```text
py -3.14 -X utf8 tools/structured_parser/evaluate.py score-practice --practice data/practice.csv --lexicon data/lexicon.json --input artifacts/structured-parser-practice390/input.json --structured artifacts/structured-parser-practice390/structured.json --output artifacts/structured-parser-practice390/evaluation.json
```

The report includes every changed example, exact-row regressions/improvements,
strict JSON results and a check that pure neural fallbacks remain unchanged.
All 390 parsed rows, including completeness and notes, remain in `structured.json`
for the coordinator's paired end-to-end evaluation.

See [the handoff](../../docs/handoffs/structured-parser.md) and
[validation receipt](validation.json) for measured results and fingerprints.
