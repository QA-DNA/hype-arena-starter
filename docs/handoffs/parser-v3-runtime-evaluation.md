# Parser v3 runtime evaluation

- Task: `task_679202e3bfb9`, dispatch `ctx_3ca779ffd1f2`; worker owns `tools/parser_v3_runtime/` and this handoff only.
- Human owner: unassigned. Branch: `teodorbalan/parser-v3-runtime`.
- Tested core: coordinator commit `92f34fc`, cherry-picked as `ebe97b8`, after base `6a9b997`; subsequent coordinator fixes are not silently included in these scores.
- Deliverable: standalone safe Rust JSONL adapter and public-only Docker runner; no production file authored by this worker.

## Input and scorer boundary

The adapter generates values with the existing selected-v2 Rust Grammar using only the public lexicon, and calls the real ClaimParser (ClaimContext, SchemaParser, ProgramParser and owner checks). The native variant additionally runs the actual frozen selected-v2 ONNX model, one CPU thread, hash validated. No practice-form reuse, runtime LLM, network, family, gold, hidden world or opaque-ID features enter prediction. Numeric spelling survives the Python wrapper as exact strings. The runtime mounts public files, own outputs and optional frozen model only; private scoring occurs after every prediction variant finishes.

Development public digest: `812cfb9cf3faa8f29688d1d79cab5b5c81e07acc01f3df275c090e0741c1b9f3`. The reserved final wording/gold was not opened and no final solver run occurred. The development runner refuses final bundles.

## Actual development results

| Path | Parse + status | AST | Status | AST coverage | Private semantic truth | Truth with AST |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| shared-grammar | 380/512 | 388/512 | 385/512 | 310/512 | 337/416 | 300/303 |
| shared-native | 367/512 | 389/512 | 372/512 | 342/512 | 345/416 | 317/322 |
| frozen-schema-native | 293/512 | 331/512 | 339/512 | 444/512 | 338/416 | 330/390 |

Semantic truth is the independent scorer evaluating a predicted AST in a private invented world. It is not full-solver, competition, calibration or unrestricted-English accuracy; null AST guesses semantic unsure. Assertion micro F1 is 0.829971 (grammar), 0.842301 (native), 0.743003 (frozen baseline). Diagnostics are 48/96 for the shared paths.

All families have 32 rows. Cells are exact AST / correct status; parse+status is reported in the full artifact.

| Family | Shared grammar | Shared native | Frozen native binder |
| --- | ---: | ---: | ---: |
| ambiguous_ownership | 32/24 | 24/16 | 9/9 |
| comparisons | 31/31 | 31/31 | 31/31 |
| document_bounds | 32/32 | 32/32 | 17/17 |
| metamorphic | 32/32 | 32/32 | 32/32 |
| missing_values | 27/27 | 22/22 | 24/24 |
| multi_clause | 0/0 | 0/0 | 7/0 |
| multi_entity | 19/19 | 19/19 | 19/19 |
| negated_comparisons | 28/29 | 28/29 | 0/29 |
| nested_scope | 25/25 | 25/25 | 1/16 |
| object_distractors | 8/8 | 13/8 | 16/16 |
| pronouns_enabled | 27/27 | 27/27 | 29/27 |
| punctuation | 28/28 | 32/28 | 32/28 |
| raw_precision | 30/30 | 30/30 | 32/32 |
| typed_exact | 31/31 | 31/31 | 32/32 |
| units_and_billing | 26/30 | 26/30 | 26/27 |
| version_binding | 12/12 | 17/12 | 24/0 |

All six real nuisance runs preserve status/AST and ownership on 512/512 rows for both shared paths: reversed/shuffled candidates, changed candidate IDs, injected untrusted fields, reversed document order and replaced input IDs. Both preserve all 16 truth-only pairs. Context is reset for every independent input and replays only enabled, matching explicit document context.

The frozen pre-v3 binder source is the real `22fa97b` snapshot, compiled via the optional feature. All 512/512 row proposal SHA-256 hashes equal the shared native path. This compares binders with a common current context frontend and identical grammar/native proposals; it is not a historical complete-solver A/B. Baseline variants were not run.

## Verification and artifacts

- Five Rust adapter boundary tests passed: nuisance isolation, explicit/mismatched/disabled context, input limits, Unicode euro money and foreign-owner rejection.
- Actual frozen-native sentinel controls: {"unicode_eur_money": false, "foreign_unicode_owner_abstains": true, "foreign_ascii_owner_abstains": true}.
- Isolated release build, default all-target Clippy with `-D warnings`, and format completed; the optional frozen-baseline feature also built successfully.
- Existing independent evaluator suite: all 38 tests passed.
- Foundation xtask checks were not rerun by this worker after the coordinator imposed a four-minute completion deadline; coordinator owns the release checks.

All runs remain under ignored `artifacts/parser-v3-runtime/`: `shared-grammar/`, `shared-native/`, `frozen-schema-native/`, and `sentinels-native/`. Each scored run keeps source/model/binary receipts, exact raw predictions, metrics, score, summary and `all-failed-rows.jsonl` containing every failed row. `paired-baseline.json` records real proposal equality. `proposal-diagnostic/dump.jsonl` independently dumps candidates and actual raw schema/program/shared results for the two coordinator-requested currency/unit failures.

The earlier `initial-grammar/` and `initial-native/` runs directly called ProgramParser on ordinary rows. `score-exact.json` rescored their preserved raw decimals after correcting exploratory Python float round-tripping; their original `score.json` is superseded. They are retained as failure evidence, not final candidate measurements.

## Measured limits

- shared-grammar: 4.066 s including initialization, candidate generation, context, parser, JSONL IO/serialization and selected inference; peak process RSS 139336 KiB; one parser thread and 0 native thread(s).
- shared-native: 7.060 s including initialization, candidate generation, context, parser, JSONL IO/serialization and selected inference; peak process RSS 195548 KiB; one parser thread and 1 native thread(s).

Hardware: AMD Ryzen 9 6900HS, Linux amd64 Docker, Rust 1.90, each container limited to 2 CPU / 6 GiB. Runs overlapped other development work, so timings are workload observations rather than a controlled performance comparison. Main adapter caps text/context, proposals, JSONL line size, row count; parsers cap depth/nodes; runner subprocesses time out at 300 seconds.

Remaining failures include shared-subject multi-clause references, product/API version ellipsis, ambiguity diagnostics and nominal shielding inside logical leaves. The preserved diagnostic proves ProgramParser shields some raw Grammar name proposals (including currency/ASCII unit tokens) into fullwidth text before SchemaParser repair, then restores only name values. This was sent to the coordinator; no core fix was made here. The coordinator may rerun this adapter against subsequent fixes before its explicit final freeze.

Code and invented sentinel controls were authored with development-time Codex assistance. Generated worlds are evaluation-only and no Hooly evidence. No organizer fixtures, final gold, production model weights, infrastructure, external posts, push or deployment changed.
