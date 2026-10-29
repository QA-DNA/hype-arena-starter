# Parser v3 schema/text binding

- Task: `task_c6c3d54da5dd`, dispatch `ctx_0d3d30a9d205`.
- Agent owner: dispatched binding worker. Human owner: unassigned.
- Base: `22fa97b`; isolated branch `teodorbalan/parser-v3-binding`.
- Scope: `crates/core/src/structured.rs`, `tools/structured_parser/`, this handoff.
- Stable interface: `SchemaParser::compile/parse`, `Parsed`, `ValueCandidate`.
- Acceptance: text/schema-only ownership, local operators, exact values,
  incomplete ambiguity, meaningful boundary tests, Docker Rust 1.90 checks,
  released practice390 A/B with every changed row/fallback retained.
- Exclusions: shared exports, model, engine, CLI, context/program modules,
  organizer inputs, neural/model weights, runtime network/LLM, pushes/deploys.

## Delivered behavior

- Reuses existing bundled language cues for legal explicit owners, rejects
  value-only cues and tied field meanings, and marks surface repairs incomplete.
  The tested live survey phrase `recommend rate` selects `would_recommend`;
  `response rate` remains a separate field. No labels or truth values select it.
- Preserves version marker words inside frozen candidate spans. Explicit API or
  interface language selects `api_version`; ambiguous bare product/API values
  stay incomplete. A written count unit prevents a star rating becoming a version.
- Protects date/version/name spans and lexical hyphenated conjunctions during
  clause splitting. A quantity ending in `W.` ends a sentence rather than
  borrowing the initial-letter abbreviation rule.
- Resolves ordinary `field in/on/at subject` and nearer grammatical subjects,
  without crossing another named subject through a possessive. Unique bound
  owners establish row-local `its/his/her/their` focus; named values do not steal
  it, and blank lines or multiple owners clear it.
- Requires a grammatical inverse relation for values before a field. Tracks
  unconsumed numeric and name proposals; partial binding cannot claim coverage
  or drop a genuinely unparsed city/count assertion from neural fallback.
- Interprets operators within the field's predicate, supports explicit local
  comparator complements, and rejects approximations, single proposed range
  endpoints, ambiguous three-place decimals and conflicting/unsupported periods.
- Preserves raw ISO date value/precision, rejects invalid ISO calendar dates and
  ambiguous slash/dotted numeric dates. Repairs written currency suffix symbols
  and up to two explicit count modifiers only when the proposed noun is written.

No public signatures or fields changed. New `surface_binding:...; coverage
remains incomplete` and `unparsed value in assertion clause` notes are diagnostic;
the coordinator must continue respecting `complete == false`. Unknown notes keep
their existing semantics. Generic neural fallbacks remain unreliable proposals,
not evidence or a claim of full extraction coverage.

## Released development result

Original frozen input/predictions and raw output were copied without changes
from the sibling `evidence-structured-parser-codex` practice390 directory.
Gold was used only in the separate evaluator after parser output existed.
The final runtime container mounts only the release binary, public lexicon,
candidate input and output directory, with networking disabled.

| Parser | Exact rows | TP | FP | FN |
| --- | ---: | ---: | ---: | ---: |
| Frozen native | 336/390 | 436 | 20 | 53 |
| Frozen schema binder | 338/390 | 437 | 18 | 52 |
| This binder | 339/390 | 439 | 17 | 50 |

Relative to the frozen binder, `p-467` improves through explicit ownership in
`customers in Hooly's Q2 results`; no exact row regresses. Strict JSON exact
rows are also 339. Relative to native, the existing `p-69`/`p-458` improvements
remain and `p-467` is added. All 328 remaining pure neural fallbacks retain
exactly the input neural fact list. Twenty rows are complete (previously 19).

The full parse changes on 363 rows mostly add incomplete-coverage diagnostics;
the report retains every change. `p-58` now extracts the written stable version
and retains the neural sidebar Boolean while staying incomplete, instead of
inventing a `bring` quantity and claiming completion. Its gold contains only
the version, so this remains inexact; no fact was deleted to optimize that row.
Other raw fact-list changes are ordering changes except the `p-467` owner repair.

An exploratory pass exposed three regressions: `p-550`/`p-929` star ratings
became versions and `p-1552` lost Berlin while binding attendees. General
boundary tests now protect each failure mechanism and the final A/B has none
of these regressions. Earlier exploratory reports remain untouched artifacts.

All final row, completeness, note and fallback transitions are retained in
`artifacts/parser-v3-binding/evaluation-final.json`, including the 37 fallback
changes listed below. Output is
`artifacts/parser-v3-binding/runtime-final/structured.json`; source/input/binary
fingerprints are in `artifacts/parser-v3-binding/receipt-final.json`.

## Verification

- Rust 1.90, `veridyct:dev`, offline, two CPUs, 3 GiB, safe Rust.
- Isolated tooling tests: 43 semantic tests pass (24 preserved + 19 new).
- Isolated tooling Clippy with all targets and `-D warnings`, format and
  five Python evaluator normalization tests pass.
- `cargo xtask check` passes workspace format/Clippy, documentation/graph checks
  and original organizer hashes; `cargo xtask test` passes all 79 workspace tests.
- The scoped tooling lock required an offline refresh for the existing core
  SHA-256 dependency at base `22fa97b`; no parser runtime dependency was added.
- Final release: 390 rows in 0.248 s total / 0.154 s parsing, 26,812 KiB peak
  process RSS, one parser thread, AMD Ryzen 9 6900HS, Docker Linux amd64.
  The measurement excludes frozen neural inference/candidate preparation.

Docker uses shared registry volume `veridyct-mvp-registry` and this worker's
exclusive `veridyct-parser-v3-binding-target`. Foundation docs checks require
read-only Git metadata mounted as `/git`, `GIT_DIR=/git/worktrees/parser-v3-binding`,
`GIT_COMMON_DIR=/git` and `GIT_WORK_TREE=/work` for this Windows worktree.

Reproduce the paired evaluation with `score-practice` in
[the tooling README](../../tools/structured_parser/README.md), adding
`--baseline artifacts/parser-v3-binding/structured-frozen.json` and the final
runtime output above. Old scores/raw outputs and `validation.json` are preserved.

## Limits and next owner

This is development extraction A/B, not independent truth accuracy. The 51
remaining inexact rows largely need document context, semantic extraction or
better frozen candidates. The coordinator owns those modules, integration,
unparseable-claim abstention, end-to-end verification and submission. Non-ISO
English date normalization and word-number arithmetic still depend on frozen
proposals. Surface cues are deliberately incomplete; unknown entity aliases,
schema attributes alone, and missing currencies never create a structured fact.

Development-time code and invented boundary tests were assisted by Codex.
The live language examples were supplied by the coordinator without truth gold.
No neural training, model weight edits, sealed-world or million-target inspection,
organizer-file edits, runtime LLM/network, push or deployment was performed.

The final scoped implementation commit is recorded in the receipt below.

## Complete fallback transition inventory

- pure -> none: `p-28`, `p-302`, `p-390`, `p-467`, `p-495`, `p-735`, `p-813`, `p-944`, `p-1098`, `p-1165`, `p-1280`, `p-1356`, `p-1435`, `p-1563`, `p-1631`, `p-1647`, `p-1722`, `p-1732`.
- none -> clause: `p-58`.
- pure -> clause: `p-170`, `p-384`, `p-400`, `p-521`, `p-523`, `p-552`, `p-808`, `p-1090`, `p-1198`, `p-1269`, `p-1346`, `p-1404`, `p-1513`, `p-1538`, `p-1552`, `p-1694`, `p-1721`.
- clause -> none: `p-1106`.

Every row retains both fact lists, completeness and notes in the ignored full report.

## Commit receipt

Final implementation/test/tooling commit:
`7e1c5d1c32df9f6f74279c61c58d6b1fd51d54ab`.
This receipt is a documentation-only follow-up; cherry-pick the implementation
commit and this receipt commit to retain the complete handoff.
Final `structured.rs` SHA-256:
`341c274375cd07ec9b86c2ca9cb0e868be7558a4d7dc55b6599c3c197a3d6f13`.
