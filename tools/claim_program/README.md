# Bounded claim-program parser harness

This isolated Cargo workspace includes the staged production
[claim_program.rs](../../crates/core/src/claim_program.rs) by path. It uses the
existing schema binder for atomic leaves without editing core exports or engine
integration. No neural training, runtime network, evidence lookup, or runtime LLM
is involved. The implementation is safe Rust and uses CPU only.

```text
cargo test --locked --offline --manifest-path tools/claim_program/Cargo.toml
cargo clippy --locked --offline --manifest-path tools/claim_program/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path tools/claim_program/Cargo.toml -- --check
cargo build --locked --offline --release --manifest-path tools/claim_program/Cargo.toml
```

On the Windows worker these commands run inside `veridyct:dev` as root, with
`--network none`, the shared `veridyct-mvp-registry` Cargo registry volume, and
the dedicated `veridyct-parser-v3-program-target` volume at `/workspace/target`.
Set `CARGO_TARGET_DIR=/workspace/target` and bind this checkout to `/workspace`.
The image supplies Rust 1.90; host Cargo is unavailable. Root is needed only for
the new target volume's ownership.

```text
veridyct-claim-program-tools LEXICON.json ROWS.json OUTPUT.json [METRICS.json]
```

Input rows contain `id`, `text`, optional `candidates` (also accepted as
`_extractor_candidates`), and optional `neural` (also accepted as `form`). Candidate
offsets are half-open Unicode scalar spans. Row labels, observation dates, gold,
world pointers, and other metadata are not deserialized into the parser boundary.
Outputs retain IDs and contain `program` and `legacy_facts`; metrics report parsing
seconds, one parser thread, and process peak RSS on Linux. Generated inputs,
outputs, logs, and binaries belong in ignored `artifacts/` or the target volume.

`smoke.py` prepares 2,000 assistant-authored syntax examples, then verifies the
adapter output after parsing. It checks 1,000 pairs that differ only in irrelevant
metadata and validates expected AST/completeness/projection shapes. It generates
no training material and estimates no independent truth accuracy:

```text
py -3.14 -X utf8 tools/claim_program/smoke.py prepare
```

Mount `artifacts/parser-v3-program/smoke` to `/io`, and the target volume read-only
to `/binaries`. Run with `--network none --read-only --cpus 2 --memory 6g`:

```text
/binaries/release/veridyct-claim-program-tools /io/lexicon.json /io/input.json /io/output.json /io/metrics.json
py -3.14 -X utf8 tools/claim_program/smoke.py validate
```

Preparation and validation run on the host; the adapter command runs in Docker.
The validator writes an ignored `receipt.json` with fingerprints and measurements.

`ProgramParser::compile(&Value)` consumes only subject names, aliases, and
attribute identifiers. `parse(text, candidates, neural)` returns a `ClaimProgram`
with `expression`, `complete`, `notes`, and `structured`. Only `structured=true`
requires logical routing; ordinary prose keeps the existing legacy route.
`legacy_facts()` projects only a complete positive conjunction. It returns `None`
for any NOT, OR, comparison, unknown, unsupported, or incomplete program.

`ClaimProgram::evaluate` and `ClaimExpr::evaluate` use caller-supplied atom and
slot-comparison callbacks returning `TruthValue::{True,False,Unknown}`. Evaluation
is Strong Kleene logic: false dominates ALL; true dominates ANY; negation
preserves unknown; empty groups are unknown. Comparison callbacks own actual
recorded-value resolution and must return unknown for missing or incomparable
values, including currency/billing-period differences. Parsing never resolves
values from evidence. An absent slot date means the caller supplies query time;
explicit ISO dates retain written year/month/day precision.

Supported syntax includes AND before OR precedence, parentheses, prefix NOT,
neither/nor, both/either, `all(...)` and `any(...)` lists, natural `not all of the
following: A and B`, atomic `not`/`never`/`without`/`n't` negation, and explicit
slot comparisons such as `Atlas price on 2026-03 >= Boreal price on 2025-12-31`.
`not less than` stays a GE comparator. Names and quoted nominal values protect
lexical conjunctions. Quoted values are restored to their original spelling
after leaf binding. Currency, period, unit, date, version and candidate offsets
are scoped and rebased per leaf. Structured leaves disable whole-row neural
fallback because it has no reliable leaf alignment.

Limits are 65,536 input scalars, 4,096 candidates/neural proposals, depth 32,
512 expression nodes, and 2,048 tokens or schema mentions. Limit violations,
conditionals, malformed scope and unresolved comparison references remain
explicit unknown/unsupported results. Pronoun/document-context resolution,
ordinary fact validity scopes, and exact evidence integration belong to the
coordinator. ISO is the supported explicit slot-date grammar; cross-clause
ellipsis, quantification over implicit schema subjects, and conditionals are
not inferred.

See the [task handoff](../../docs/handoffs/parser-v3-program.md) for verification,
ownership, integration requirements and measured limitations. Semantic fixtures
are development-time assistant-authored tests, not independent accuracy estimates.
