# task_56f1250f119a: independent parser V3 evaluation

- Status: done for the coordinator's bounded submission scope; harness and
  immediate safety review delivered, full adapter/final scoring explicitly deferred.
- Human owner: unassigned.
- Agent role: independent evaluator/reviewer; no parser implementation ownership.
- Branch: `teodorbalan/parser-v3-evaluation`.
- Checkout: `C:\Users\Teodor\orca\workspaces\QA-DNA-JEV\parser-v3-evaluation`.
- Base: `22fa97b6fe27fcfa8d0bab7ae2e85c10c5386148`.
- Implementation commit: `fa827a544b4a356dec511b2097cec58fafcc1f3f`.
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
  (format, Clippy, 371 local links after staging this harness, graph, preserved
  organizer hashes).
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

On 2026-10-29 the coordinator redirected this worker to immediate read-only
review for submission readiness. The bounded candidate keeps the new logical
AST experimental/off by default. The dedicated challenge adapter was not yet
implemented, and neither development parser scoring nor held-out parser scoring
ran. No new accuracy estimate is claimed. The reserved final remains untouched
by a solver, its gold undisclosed, and no final one-shot marker exists.

The coordinator can dispatch a follow-up for the Rust adapter and nuisance runs.
Review development failures before coordinator freeze; keep reserved final
wording/gold private until freeze. Final scoring requires the documented receipt,
hashes all solver/source artifacts, and opens gold only after an exclusive marker.
Missing adapter variants remain untested.

## Immediate safety review

Read-only target: `parser-v3-integration` engine empty/incomplete guards,
`latest_history_judgement`, CLI owner filtering, and `ClaimContext`. No production
file was edited by this worker. The reproducible controlled helper probe lives
under ignored `artifacts/parser-v3-evaluation/review-probe/`; it supplies explicit
synthetic proposals to isolate guard behavior and is not a model accuracy test.

Two concrete issues were reported to the coordinator before settlement:

1. A valid public alias in `Chrome's stable version is v12.4.` was classified as
   `ambiguous_common_word` by the conservative normalizer and then deleted by the
   new owner whitelist. This was collateral rejection of a legitimate owner.
2. `Emberkeep offers EUR 17 per month and competes with Hooly AI Pro.` retained a
   hallucinated `Hooly AI Pro/price` proposal because the known entity occurred
   as an object. With one same-day price anchor the engine returned true at 0.94
   and described graph entailment of the extracted assertion.

The coordinator repaired both in `grounded_owner`. Running the same probe against
preserved before/after CLI source snapshots confirmed:

| Control | Before | After |
| --- | --- | --- |
| Chrome possessive alias | Correct fact erased | Correct fact retained; unsure without evidence |
| Foreign company with known object | Wrong-owner fact; true | Empty parse; unsure |
| Explicit canonical plan owner | Correct fact; true | Correct fact; true |
| Foreign owner without a known mention | Empty parse; unsure | Empty parse; unsure |

`review-probe/run.py` reproduces both snapshots using Docker `veridyct:dev`, no
network, a read-only root source bind, the shared registry, and this worker's own
target volume. `before-output.txt`, `after-output.txt`, `parser_before.rs`,
`parser_after.rs`, and `review.json` preserve actual output and source hashes.
The preserved probe root base was `7df79c2e542069855805ec5988ea72a5f308d577` plus the
owner-filter fix recorded by `review.json`. An explicit-document context control
also rewrote `Its uptime SLA` to the declared Hooly Cloud antecedent.

The supplied unlabelled 20-row safety output had zero definitive empty parses;
its preserved baseline had seven. This is a guard-behavior check with no truth
gold, not an accuracy measurement. General ownership recognition remains bounded
by the parser and explicit object phrases; the review does not establish a
complete English role grammar. Full challenge coverage and nuisance invariance
await the deferred adapter work.
