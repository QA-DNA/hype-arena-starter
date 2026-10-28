# Task ID: assertion-pipeline

- Status: done; baseline ready for review.
- Human owner: unassigned. Implementation: Codex; no delegated agents.
- Branch and checkout: `feat/assertion-pipeline`, `/tmp/veridyct-assertion-pipeline`.
- Base commit: `e79e83c4388f9c451138404e0386d33ff67ba298`.
- Authorized scope: reusable normalization and assertion-text splitting; CSV tools;
  practice output and evaluation. No frontend, typed-value interpretation, solver,
  claim generation or deployment.
- Paths: `crates/core`, `crates/cli`, workspace Cargo files,
  `labs/assertion-extraction`, related scope/development/architecture documentation.
- Acceptance: structured fields, shared core, independent stages, source preservation,
  explicit unresolved results, meaningful regression tests, practice CSV artifact.

## Delivered change

See the [decision](../../labs/assertion-extraction/DECISION.md) and
[usage/schema](../../labs/assertion-extraction/README.md). The core exports
`LexiconIndex`, `Normalizer`, `Splitter`, `NormalizedRow`, `ParsedRow`, and
`AssertionText`. Assertion wording is separate from subject and attribute.
Combined execution passes objects without an intermediate serialization. CSV adapters
retain parent labels but labels/forms never enter the extraction API.

`lexicon compile` validates the index, `normalize` writes canonical mentions and
alignment, `split` verifies normalized CSV and emits fragments, and `parse` combines
the stages. Outputs preserve row order and repeated pairs. Unknown fragments remain
explicit and include reasons. A versioned index supports optional reviewed aliases.

Generated practice files live under ignored `labs/assertion-extraction/outputs/`.
`practice.assertions.csv` contains one fragment per record; `practice.rows.csv` gives
one summary per input row; `practice.normalized.csv` shows the normalization stage.
`practice.report.json` reports pair agreement against practice annotations. It is a
development diagnostic, not held-out generalization or value/text/truth accuracy.

The earlier uncommitted extraction plan and its index link were preserved. This task
implements the user's narrower assertion-text milestone, not that plan's full typed
value design. Updated core/CLI/root scope descriptions reflect preprocessing only.

## Verification

Targeted core/CLI tests cover aliases, UTF-8 alignment, collisions, tampered metadata,
scope, named subject lists, repeated pairs, object coordination, CSV quoting/newlines,
staged/combined equivalence, form/label independence, input protection and failures.
Verification completed:

- `cargo xtask check`: passed (formatting, Clippy with warnings denied, documentation,
  project graph, organizer snapshot hashes).
- `cargo xtask test`: passed all 26 tests, including 20 new extraction/CLI tests.
- `cargo build --locked --release -p veridyct-cli`: passed.
- Full practice normalize + split is byte-identical to the combined parse command.
- All 1,897 parent IDs are retained; all output byte spans decode as UTF-8 and
  paired subject/attribute keys belong to the canonical lexicon.
- `unshare -Urn target/release/veridyct parse ...`: passed with no network namespace
  connectivity; output byte-identical to the ordinary run.
- `git diff --check`: passed.

Final full-practice diagnostic: 2,639 fragment records, of which 593 are paired and
2,046 unresolved. Rows: 345 `split`, 176 `partial`, 1,376 `unresolved`. Of 593 predicted
pair occurrences, 573 match the 2,402 reference occurrences: pair precision 96.63%,
recall 23.86%, F1 38.26%. There are 363 exact pair-multiset rows (19.14%), and 53 rows
marked `split` still disagree with the reference pair multiset. These are development
pair diagnostics, not complete semantic extraction accuracy; inspect the mismatches.

One measured release run took 0.500 seconds, with child-process peak RSS 27,424 KiB,
on AMD Ryzen 7 6800HS, Linux x86_64, one processing thread, Rust 1.90.0 portable default
target. No speedup claim. `outputs/run-resources.json` records the exact command,
input/binary/source fingerprints and base commit plus uncommitted-source status.

Temporary Rust 1.90.0, rustfmt and Clippy were installed under `/tmp/veridyct-rustup`
and `/tmp/veridyct-cargo` because the machine had no Rust installation. No shell
configuration was modified. Reproduction on a normal Rust installation uses the
documented Cargo commands; the temporary toolchain is not a project dependency.

## Limitations and next step

Conservative local rules cannot resolve many implicit subjects, relative clauses,
generic aliases, omitted attributes or paraphrases. Even paired fragments can be
incorrect; inspect the report's pair mismatches. Shared negation and unaligned lists
are retained unresolved instead of flattened. No claimed typed-value or truth accuracy.

Next: review the delivered CSV, agree on an independent evaluation set, then expand
attribute/attachment coverage against reviewed cases. Value interpretation and truth
reasoning require separate authorization. The official checker was not run: there
is no solver or claim generator, and this work does not satisfy the competition output.

## Working-copy delivery

After isolated implementation and verification, changed source/documentation files and
the generated lab outputs were copied into the original working directory for review.
The original uncommitted extraction plan was preserved byte for byte. That initial
working-copy delivery did not include a commit, push or deployment. A local executable is also available at ignored
`artifacts/assertion-extraction/veridyct`; it runs without a Rust installation.
