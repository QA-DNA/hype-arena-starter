# task_56f1250f119a: independent parser V3 evaluation

- Status: active; harness verified, adapter review and final scoring pending.
- Human owner: unassigned.
- Agent role: independent evaluator/reviewer; no parser implementation ownership.
- Branch: `teodorbalan/parser-v3-evaluation`.
- Checkout: `C:\Users\Teodor\orca\workspaces\QA-DNA-JEV\parser-v3-evaluation`.
- Base: `22fa97b6fe27fcfa8d0bab7ae2e85c10c5386148`.
- Scope: `tools/parser_v3_evaluation/` and this handoff only.
- Interface: complete public text/context JSONL to independent AST/status/assertion
  JSONL; no production exports, model, engine, CLI, context module or weights changed.
- Acceptance: broad exposed 512-case development and fresh reserved 2,048-case
  final, independent labels/tests, input/gold isolation, pre-score hashes,
  one-shot final gate, concrete adapter review, local scoped commit.

## Delivered behavior

The [harness README](../../tools/parser_v3_evaluation/README.md) documents the
[static interface](../../tools/parser_v3_evaluation/interface.schema.json),
[factory](../../tools/parser_v3_evaluation/factory.py),
[independent oracle](../../tools/parser_v3_evaluation/oracle.py),
[audit](../../tools/parser_v3_evaluation/audit.py), and
[scorer](../../tools/parser_v3_evaluation/score.py).
Sixteen equally sized families cover all eight value kinds, nested logic,
ownership, explicit bounded pronouns, abstention, precision, billing and
punctuation. Truth-only pairs and external adapter nuisance runs have separate
metamorphic checks. Development-time OpenAI Codex provenance is explicit.

Inputs have only `id,document_id,text,context`. Candidate generation belongs to
the frozen adapter; the evaluator supplies no bound subject/attribute hypotheses.
Gold holds constructed ASTs, acceptable parse statuses, assertion sets, note
categories, private counterfactual worlds, and separate semantic labels. Raw
decimal strings compare as exact fractions; kinds/currencies/billing/dimensions
remain distinct. Unsupported/ambiguous English receives no invented source ID.

All generated data and reports remain ignored under `artifacts/`. Initial
development, development-v2 and development-v3 are preserved audit revisions.
The authoritative development bundle is
`artifacts/parser-v3-evaluation/development-v4/`; the fresh final is
`artifacts/parser-v3-evaluation/reserved-final/`. Both were constructed before
the production adapter was supplied, and final labels/wording remain undisclosed.
No old sealed runs or scores were opened or modified. No organizer file was edited.

| Preserved artifact | SHA-256 |
| --- | --- |
| Development public bundle | `812cfb9cf3faa8f29688d1d79cab5b5c81e07acc01f3df275c090e0741c1b9f3` |
| Development input JSONL | `770a97f4bf67889aa4ce20e89a76021f93cf0ca5f4503efadf64b784ebe03fcf` |
| Development gold JSONL | `0d42f0145f206f0116597f09e3e847d89775798dbf39ece75ba99523a758315e` |
| Reserved final public bundle | `24822a4f7cafbf64a2a3537c10b70ed6857bc9b49371793eb3f1fb8c84326581` |
| Reserved final input JSONL | `59db5653893610ec151d7e857ab9a5d768bb717e5f6c3ee5e6c0ef9a7cf310c9` |
| Reserved final gold JSONL | `2858a633d499850626fbe9fac957a2ad062820a57d008a4aea06d7b990067534` |

The bundle digest hashes a canonical mapping from every public relative path to
its file digest. Each manifest additionally records per-file and factory-source
hashes. Public hashes were sent to the coordinator before any final prediction.

## Verification

- `py -3.14 -X utf8 -m unittest tools.parser_v3_evaluation.test_evaluation -v`:
  38 tests passed, covering hand-authored typed arithmetic, exhaustive three-valued
  connectives, scope distinctions, label tampering, input isolation, abstention,
  prediction validation, hash integrity, and final freeze/one-shot boundaries.
- `py -3.14 -X utf8 -m tools.parser_v3_evaluation.audit --bundle artifacts/parser-v3-evaluation/development-v4 --include-gold --report artifacts/parser-v3-evaluation/development-v4/audit.json`:
  512 rows and all input/gold/construction checks passed.
- `py -3.14 -X utf8 -m tools.parser_v3_evaluation.audit --bundle artifacts/parser-v3-evaluation/reserved-final --report artifacts/parser-v3-evaluation/reserved-final/public-audit.json`:
  2,048 rows and public hashes passed; gold was not opened by this audit. Internal
  construction validation ran before final files were written.
- Docker `veridyct:dev`, Rust 1.90, `--network none`, shared registry volume
  `veridyct-mvp-registry`, own target volume
  `veridyct-parser-v3-evaluation-target`: `cargo xtask check` passed
  (format, Clippy, 361 local links, graph, preserved organizer hashes).
- Same Docker configuration: `cargo xtask test` passed, 79 workspace tests plus
  empty/doc-test suites. No full neural training or model changes were run.
- The new Docker target initially required `chown vscode:vscode /work/target`;
  this touched only the worker's own named volume. The Windows worktree `.git`
  path needs a read-only common Git metadata mount and explicit Linux
  `GIT_DIR/GIT_COMMON_DIR/GIT_WORK_TREE` for the docs check.

## Limits and next action

This is a controlled synthetic challenge, with shared templates and correlated
examples, not a competition/general-English accuracy estimate. Python oracle
semantics and labels have hand-authored sentinel coverage and manual self-review;
additional human linguistic review remains useful. Semantic unsure accuracy is
reported with AST coverage because abstention can otherwise inflate it.

The coordinator supplies the Rust adapter and its nuisance variant runs. Review
development failures before coordinator freeze; keep reserved final wording/gold
out of messages until freeze. Final scoring requires the documented receipt,
hashes all solver/source artifacts, and opens gold only after an exclusive marker.
Missing adapter variants remain untested. Implementation/delivery commits will
be recorded before completion.
