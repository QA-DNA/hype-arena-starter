# Assertion extraction lab

To inspect the existing results in a browser, run
`node labs/assertion-extraction/serve-viewer.mjs` and open `http://127.0.0.1:8791`.
The [simple review viewer](VIEWER.md) shows original/normalized text, extracted
columns, unresolved reasons, source highlights and separate practice annotations.

Offline Rust preprocessing: canonicalize entity mentions, then split supported prose
into **subject**, **attribute**, and **assertion_text** fields. Values remain wording:
`serves over 100 customers` is not converted into a quantity or a truth verdict.

The core returns `NormalizedRow`, `ParsedRow`, and `AssertionText` objects. The combined
command passes objects directly between stages. No display sentence is constructed
and then parsed. CSV is an input/output adapter, not the internal data model.

## Quick start

From the repository root, using the Rust version pinned in `rust-toolchain.toml`:

```sh
cargo build --locked --release -p veridyct-cli
target/release/veridyct lexicon compile --input data/lexicon.json --output labs/assertion-extraction/outputs/lexicon-index.json
target/release/veridyct parse --index labs/assertion-extraction/outputs/lexicon-index.json --input data/practice.csv --output labs/assertion-extraction/outputs/practice.assertions.csv --summary labs/assertion-extraction/outputs/practice.rows.csv
```

`outputs/` is generated and ignored by Git. Open `practice.assertions.csv` in a CSV
viewer. Each original ID has consecutive output records; input order is retained.
`practice.rows.csv` has one summary record for each input row.

To inspect or run the stages independently:

```sh
target/release/veridyct normalize --index labs/assertion-extraction/outputs/lexicon-index.json --input data/practice.csv --output labs/assertion-extraction/outputs/practice.normalized.csv
target/release/veridyct split --index labs/assertion-extraction/outputs/lexicon-index.json --input labs/assertion-extraction/outputs/practice.normalized.csv --output labs/assertion-extraction/outputs/practice.staged.csv
```

The staged output matches the combined output byte for byte. Persisted normalization
records include alignment metadata and an index fingerprint; the standalone split
command verifies them against their source before use. This verification re-runs
normalization for persisted input, but the combined path normalizes only once.

Input is comma-delimited UTF-8 CSV with `id,text,date`. `label` is optional. A `form`
column and other extra columns are ignored, never consulted for extraction. Columns
are matched by name. Quoted commas, quotes and embedded newlines are supported.
Empty dates are retained, not interpreted. IDs must be nonempty and unique. Individual
text cells are limited to 1 MiB after CSV decoding. Input records are processed one at
a time; the adapter retains a set of IDs to reject duplicates. It uses one thread.

Failures return exit code 2 and diagnostics on stderr. CSV files are written to sibling
temporary files and renamed after success. An existing output is preserved if parsing
fails. Input, index, aliases and output paths must differ. Each output is atomic;
the assertion file and optional summary are not a multi-file transaction. Filesystem
rename rules apply (on Windows, remove an old generated destination before rerunning
if the filesystem refuses replacement).

## Output fields

| Field | Meaning |
| --- | --- |
| `id`, `occurrence_id` | Parent input ID and stable `id:aN` occurrence ID |
| `date`, `parent_label` | Original row metadata; never per-assertion truth labels |
| `subject`, `attribute` | Canonical pair when identified; blank fields remain unknown |
| `assertion_text` | Original wording with supported entity normalization; no typed value |
| `status` | `paired` or `unresolved` for this fragment |
| `row_status` | `split`, `partial`, or `unresolved` for its parent row |
| `reason`, `rule` | Why resolution failed, or the rule assigning the pair |
| `normalized_start`, `normalized_end` | Half-open UTF-8 byte offsets of assertion wording |
| `subject_source_start`, `subject_source_end` | Original subject mention, possibly shared |
| `source_spans_json` | Original byte ranges supporting the assertion wording |
| `normalization_issues_json` | Unreplaced ambiguous aliases and their candidates |
| `original_text`, `normalized_text` | Full row context, repeated for independent inspection |
| `index_fingerprint` | Identifies the exact lexicon normalization configuration |

`paired` means a rule found a subject/attribute association. It is **not** a verified
parse, a true fact, or an instruction to trust the statement. `split` means this
version emitted only paired fragments and found no normalization issues; it is not
a guarantee that every implicit assertion was discovered. The diagnostic report
explicitly counts split rows whose pair multisets disagree with practice forms.

Use original row context with the fragments. Date/conditional/temporal interpretation
is deferred; an assertion fragment is not a complete standalone truth proposition.
The full row is always retained, including unsupported wording. Repeated pairs are
not deduplicated. Shared predicates can have shared source spans. Labels do not flow
from a false parent into each individual assertion.

## Normalization policy

Names and aliases come from the supplied lexicon. Matching is case-insensitive, checks
word boundaries, tolerates whitespace/compact spellings and straight/curly apostrophes,
and selects longer overlapping names first. Original bytes and replacement alignment
are retained. It does not globally lowercase or strip punctuation from the input.

Aliases with multiple canonical candidates remain unresolved. The ordinary-word
aliases `Search`, `Maps`, `Photos`, `Translate`, `Chrome`, `Android`, `outage`, and
`devices division` are conservatively left unchanged and recorded as ambiguous,
including capitalized occurrences. Full canonical names and longer specific aliases
still work. This deliberately sacrifices some recall; case alone is not disambiguation.
Short names absent from the lexicon, such as bare `Cloud` or `Docs`, are not invented.

Optional reviewed additions are a JSON array supplied to `lexicon compile --aliases`:

```json
[{"alias":"Example shorthand","subject":"Hooly Cloud","provenance":"review ID and rationale"}]
```

The target must already be a canonical subject. An addition does not bypass collision
or ordinary-word safeguards. The index records source SHA-256, reviewed aliases,
schema version and a derived fingerprint; tampering/inconsistency is rejected.
Compile a fresh index from the evaluation lexicon when that lexicon changes.

## Splitting policy and limitations

Supported structures include explicit subject clauses, subject sharing over supported
coordination, one predicate shared by explicit coordinated subjects, and percentage
lists explicitly aligned with `respectively`. Attribute cues are restricted to each
subject's allowed lexicon attributes. Longer cues take precedence over contained cues
(for example, minimum seats versus seats). Alias matches inside entity names do not
also count as attribute cues.

Rules preserve phrases such as `over 100`, negation within a single claim, decimal
numbers, versions, billing wording and date commas. Unsupported coordination, shared
negation, conditions, missing subjects, ambiguous attribute matches and unaligned lists
stay unresolved. A compound fragment with multiple attribute cues is retained until a
supported split exists. Subject inheritance is limited to recognized predicate/count
prefixes within a sentence, not arbitrary following clauses or neighboring rows.

This is a conservative **first baseline**, not a general English parser. Entity objects
versus subjects, implicit names, relative clauses, quotations, ranges, shorthand and
many paraphrases still need work. No practice ID/text lookup, cross-row context,
LLM/SLM, model weights, network calls, typed-value parser, or truth evaluator is used.

## Evaluation

```sh
cargo xtask check
cargo xtask test
python3 labs/assertion-extraction/evaluate.py --practice data/practice.csv --assertions labs/assertion-extraction/outputs/practice.assertions.csv --output labs/assertion-extraction/outputs/practice.report.json
```

Python 3 standard library is used only for this development report. The Rust binaries
do not require Python. Pair precision/recall use multiset matching, preserving repeated
subject/attribute occurrences. The report includes whole-row pair matches, row status,
unresolved reasons, single/multiple assertion and subject slices, and every pair mismatch.
It does not evaluate value semantics or assertion-text alignment. Full-practice results
are diagnostic, not held-out generalization estimates: development examples informed
the rules. No training step is claimed. Establish frozen independent/template holdouts
before claiming extraction accuracy on unseen data.

Code, cues and synthetic regression fixtures were authored with Codex assistance.
Rule sources are lexicon attribute names, the lexicon analysis findings, and reviewed
development examples; synthetic fixtures are not Hooly evidence. Organizer files are
unchanged. See the [decision](DECISION.md), [core implementation](../../crates/core/src/extraction/mod.rs),
[attribute cues](../../crates/core/src/extraction/attribute-cues.json),
[CLI](../../crates/cli/src/preprocessing.rs), and [handoff](../../docs/handoffs/assertion-pipeline.md).

## Delivered practice snapshot

The initial delivery contains 1,897 input rows and 2,639 output fragments: 593 paired,
2,046 unresolved. Row statuses: 345 split, 176 partial, 1,376 unresolved. Pair agreement
against practice forms is 96.63% precision and 23.86% recall; only 363 rows have exactly
matching pair multisets. This is deliberately limited coverage. There are 53 split
rows with pair mismatches, so `split` must not be treated as a completeness guarantee.
See the generated report for every mismatch and the handoff for validation details.

A local executable was supplied at `artifacts/assertion-extraction/veridyct` for this
working copy. It can replace `target/release/veridyct` in the commands above and runs
without Rust installed. It is a generated local artifact, not committed source.
