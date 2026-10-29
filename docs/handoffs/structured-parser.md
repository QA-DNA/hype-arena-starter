# task_157e41cf4f8c: schema-guided assertion binder

- Status: delivered for coordinator integration and independent final evaluation.
- Human owner: unassigned. Agent owner: dispatched structured-parser Codex worker.
- Branch/checkout: `teodorbalan/evidence-structured-parser-codex`, isolated checkout.
- Base commit: `d0af1691d49887870eb6dd638cf439afb7e7182d`.
- Scope: `crates/core/src/structured.rs`, `tools/structured_parser/`, this handoff.
- Acceptance: stable staged API; schema/text-only binding; exact raw values and
  local operators; unknowns never promoted to booleans; meaningful tests;
  released development and paired390 A/B with hashes and unchanged fallbacks.

## Delivered behavior and decision

[structured.rs](../../crates/core/src/structured.rs) uses public lexicon aliases
and literal attribute phrases, not accepted graph values, to choose subjects.
Longest names and fields win, with special care where a name ends in a field
word (`AI Pro: price` versus `pro_price`) or a short alias occurs inside a field
(`cloud_provider`). Punctuation, underscore, hyphen and letter/digit variants
are matched. Clauses and explicit same-row `Record subject` declarations bound
scope. No private context file or pointer is used.

Candidates retain Unicode character offsets. Numeric repairs read the whole
written decimal spelling around a candidate, including truncated decimal-comma
money proposals, and preserve case-sensitive units and billing periods. Versions
are never zero-padded. Comparator interpretation is local, including `ne`, all
numeric/date/version operators and `US$` spacing. Bracketed descriptors and
numbers inside names/fields are excluded from value proposals. Nested currency,
unit and month-name proposals cannot replace their containing typed values.

Unknown declarations produce zero ordinary facts and an explicit note. A mixed
row can keep facts while remaining incomplete. Neural facts are unchanged when
no reliable schema binding exists. In an unresolved omitted-subject clause,
the merge also retains a neural fact whose exact typed value proposal appears
there, without inventing a new antecedent or claiming the row is complete.
This preserves measured ordinary-English behavior while repairing explicit
schema syntax. The choice follows the existing
[CPU/evidence boundary](../decisions/0002-evidence-mvp.md).

## Stable API and integration

```rust,ignore
SchemaParser::compile(lexicon: &serde_json::Value) -> Result<Self, String>
SchemaParser::parse(&self, text: &str,
    candidates: &[ValueCandidate], neural: &[Fact]) -> Parsed
// public serde ValueCandidate { value: Value, start: usize, end: usize }
// public serde Parsed { facts: Vec<Fact>, complete: bool, notes: Vec<String> }
```

Frozen module SHA256:
`e04748a7df6a80204bb34c7c47ec3e883b53f85434f29e568d9579195671f3f6`.
Compile once per lexicon. Use `serde_json/arbitrary_precision` to preserve decimal
lexemes; the standalone harness and coordinator integration both enable it.
Without that feature a raw decimal that would round is left unresolved.
The coordinator owns exports, engine/native/CLI integration and extraction hints;
none of those files were edited in this checkout.

Notes used by the adapter:

- `explicit_unknown:SUBJECT:ATTRIBUTE`: recognized absence, never yes/no.
- `metadata_only`: no assertion in the row; do not invent template facts.
- `unresolved subject/value ...`: a literal clause remains unresolved.
- `neural_fallback:...`: the original neural facts were retained.
- `neural_clause_fallback:SUBJECT:ATTRIBUTE`: a measured neural proposal was
  retained for an unresolved clause; completeness remains false.

The coordinator preserves its existing policy on pure nonliteral neural
fallbacks. Partial literal rows must not prove a true conjunction, and unknown
notes must prevent accidental truth through an empty/subset parse.

## Verification and measurements

All results below use released development data, not sealed/calibration data.
Gold was read only by separate diagnostic evaluators after extraction. No
training, commits, pushes, deployment or runtime LLM/network dependency was added.
Development-time code/tests were assisted by OpenAI Codex; the new unit cases
use invented names/values plus four explicitly identified public practice cases.

| Corpus and candidate source | Native exact rows | Binder exact rows | Other evidence |
| --- | ---: | ---: | --- |
| Released v3 targets, frozen candidates | 243/1,000 | 998/1,000 | 1,777 TP, 0 FP, 2 missing literal-inch candidates |
| Same targets, coordinator binding candidates | 243/1,000 | 1,000/1,000 | 1,779 TP, 0 FP, 0 FN after physical-unit normalization |
| Official practice parser development390, reused frozen predictions | 336/390 | 338/390 | 2 improved, 0 regressed; all 363 pure fallbacks unchanged |

Literal-unit comparison is 998/1,000 for the final v3 targets: two raw `in`
values are represented as the equivalent canonical `inch`. No numerical
tolerance is used. With coordinator binding candidates all 1,897 anchors are
complete, and all 889 explicit unknown anchors carry no ordinary facts.
All 26 root-reported source mismatches re-audit cleanly after exact unit
normalization. The 13 supplemental inch candidates change zero frozen neural
forms across all 2,897 input rows.

An initial paired390 audit exposed four lost omitted-subject conjuncts (`p-25`,
`p-1086`, `p-1349`, `p-1518`). All four now have explicit regression tests.
Examples of other diagnosed errors and their general repairs are truncated
`1877,36 EUR` candidates, an apparent year inside `2022,1 EUR`, bracketed
`[USD, one-off]`, `SOC 2` numeral proposals, and `Record subject: Hooly I/O.`.

Checks run successfully with Rust 1.90.0 in the existing Docker dev image:

- Isolated `cargo test --locked --manifest-path tools/structured_parser/Cargo.toml`:
  24 semantic tests passed.
- Isolated `cargo clippy ... --all-targets -- -D warnings` and formatting passed.
- `py -3.14 -X utf8 -m unittest discover -s tools/structured_parser -p test_evaluate.py`:
  five evaluator tests passed.
- `cargo xtask check`: formatting, workspace Clippy, 117 local links, graph and
  organizer snapshots passed. Docker required explicit read-only git metadata
  mounts because this Windows worktree's `.git` points to a Windows path.
- `cargo xtask test`: 23 foundation tests passed. This isolated foundation does
  not export the staged module; the separate harness above verifies that module.

Release binder measurement: 2,897 rows, 2.270 s total, 2.112 s parsing, 49,464 KiB
peak process RSS. The 390-row pass took 0.307 s total and 24,424 KiB. Hardware:
AMD Ryzen 9 6900HS, Docker Linux amd64, two-CPU/3-GiB container, one parser thread,
Rust 1.90.0 release, base commit above plus the frozen source hash. Other work
was active on the host; timings are diagnostic. Neural candidate preparation is
excluded (separately 5.112 s for the augmented 2,897-row native run).

## Reproduction, evidence and next action

Commands are in [the tooling README](../../tools/structured_parser/README.md).
[validation.json](../../tools/structured_parser/validation.json) records source,
fixture, model and image fingerprints and compact metrics.
Generated full reports remain ignored in this checkout:

- `artifacts/structured-parser-v3/evaluation-binding/{scores,errors}.json`
- `artifacts/structured-parser-v3/anchor-reaudit.json`
- `artifacts/structured-parser-v3/{native-binding,structured-binding}.json`
- `artifacts/structured-parser-practice390/{input,structured,evaluation}.json`

The paired390 `structured.json` retains all ID/facts/complete/notes records for
the coordinator's clean 1,507-training-row end-to-end comparison. Unknown/open
language, ambiguous scope and missing candidate kinds remain supported through
fallback/incompleteness, not a claim of open-domain accuracy. The coordinator
owns full solver checks and the once-only independent final after source freeze.
