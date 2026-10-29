# Task: evaluate the million-row V1 and refined V2 archives

- Status: complete, 29 October 2026. See the [full Romanian comparison](../research/million-v1-v2.md).
- Human owner: unassigned. Agent owner: Codex coordinator.
- Authorization: Teodor requested commit/merge/push of the implemented solver,
  then testing all of `Downloads/veridyct-million.zip`, followed by the refined
  `Downloads/veridyct-million-v2.zip` and a comparison.
- Branch/checkout: `teodorbalan/evidence-million-evaluation` /
  `C:\Users\Teodor\orca\workspaces\QA-DNA-JEV\evidence-million-evaluation`.
- Base: main `e6f687c95e018a3948b0a970325007523190cb43`, following the completed
  [solver integration](evidence-main-integration.md).
- Scope: `tools/million_evaluation/` and curated documentation. No production
  model training, organizer edits, submission/deployment or application API changes.
- Acceptance: validate both original archives with their full shipped checkers,
  process all rows, separate incompatible protocols/cohorts, retain the strict V2
  transfer result and publish a reproducible, explicitly adapted comparison.

## Implementation and boundaries

Both complete million-row pools were processed. V1 accuracy is 995,024/999,603
(99.5419%); V2 with the declared grammar extension is 997,062/999,603 (99.7458%).
The unchanged V1 grammar on V2 scores 8.0827% and recognizes none of the rewritten
queries. All 397 null-label parsing cases are counted outside truth accuracy.

The unchanged 9,899 inputs have zero prediction changes (93.0330% on 9,502 truth
labels). Across related rewrite IDs, 3,914 cases improve and 1,876 regress.
The V2 note subset has 1,879 errors: every one contains a target `api_version`
bound as `version` in a revised unqualified clause. Nine are definitive mistakes;
1,870 are abstentions. V2 can erase the API qualification while preserving the
target attribute. No dataset or parser was patched after its frozen score.
The larger aggregate accuracy is not evidence of uniformly improved parsing:
macro-F1 decreases from 99.5737% to 99.4227%.

The [harness guide](../../tools/million_evaluation/README.md) documents commands,
feature isolation, runtime semantics, cache keys and exclusions. The
[protocol decision](../decisions/0004-development-note-protocol.md) records why the
recursive supplied-note task is evaluated outside the competition CLI.

The original selected-v2 neural weights, schema binder, GBT and numerical kernel
are reused. Safe Rust handles extraction and typed comparison; bounded Python
grammars supply the broader development protocol. No runtime LLM or external API.
Containers have two CPUs, a six-GiB cap, network disabled, a read-only root and
unprivileged UID 10001. Only input-derived features/public practice training data
are mounted; target sidecars, bank and oracle are excluded.

V1 was frozen before its full label scores. Its unchanged adapter is also applied
to all V2 rows, exposing unsupported syntax rather than silently adapting. An
opt-in V2 language extension uses literal public renderer vocabulary and is frozen
separately before its full score. All V1 feature plans, requests and practice CSV
are byte-identical under that extension (plans compared after decompression).

Local ignored receipts and artifacts:

- `artifacts/million-runtime/freeze.json`: original adapter, model, binary hashes.
- `artifacts/million-runtime/compatibility-freeze.json`: separate V2 language freeze.
- `artifacts/million-runtime/v1-compatibility-parity.json`: full V1 feature parity.
- `artifacts/million-input/` and `million-input-v2/`: unmodified extracted archives.
- `artifacts/million-v1-final/`: V1 features, separate target sidecar, parse outputs,
  pair requests, prediction stream, confusion matrices, timings and diagnostics.
- `artifacts/million-v2-frozen/`: unchanged V1 adapter on V2, including failures.
- `artifacts/million-v2-final/`: opt-in compatible V2 interface and frozen models.
- `artifacts/million-comparison/`: paired development analysis and input overlap.
- `artifacts/million-*-integrity*`, `million-v2-tests*`: original archive gates.
- `artifacts/million-kernel-tests/`: test-only arithmetic/oracle differential data.

## Verification

The committed main foundation already passed all 79 workspace tests, Clippy,
organizer fingerprints and the actual offline container format contract before
archive evaluation. Production code is unchanged in this task.

- New grammar tests: 12 pass, including three-valued short-circuit logic,
  missing evidence despite a cached parse, dates, ordinal bindings, operator
  strictness, negation scope, specific attribute precedence and V1 compatibility.
- Bridge: all-target Clippy with warnings denied passes; the date-range unit test
  passes. Test-only exhaustive differential checking: 20,723 typed comparisons,
  zero discrepancies. The supplied oracle is not present in inference mounts.
- Original V1 full delivery replay: all 1,000,000 rows pass, including hashes,
  SQLite integrity, quotas, original recipes, oracle and exact pool correspondence.
- V1 generation/oracle tests: all 16 pass.
- Original V2 full delivery replay: all 1,000,000 rewritten/retained rows pass,
  including source/code hashes, parent audits, registry and exact oracle replay.
- V2 revision tests: all eight pass with documented `REVIEW_BANK` and `REVIEW_SAMPLE`
  pointing at the shipped bank and original review packet; all 16 inherited
  generation/oracle tests pass.
- Both archives' legacy pilot tests: 12/13 pass. The unchanged volume assertion
  expects 20,000 while the delivered retained pilot has 17,176. Do not alter the
  fixture, checker or dataset to conceal this failure.
- V1 host checker cannot import Unix `resource` on Windows; rerun and successful
  validation used Linux. V2 revision test defaults point at the author's machine;
  supported environment overrides resolve these paths without editing tests.
- Final foundation checks: `cargo xtask test` passes all 79 tests; `cargo xtask check`
  passes format, all-target Clippy, 360 local links, 19 graph nodes/19 edges and
  unchanged organizer fingerprints. Linux checking of a Windows worktree requires
  the shared Git metadata mounted read-only with explicit `GIT_DIR`/`GIT_WORK_TREE`;
  the first unconfigured attempt failed on the Windows absolute `.git` path.

Final archive replay receipts, per-family scores, null handling, paired changes,
hardware, runtime and limitations are included in the final comparison report.
Do not describe the adapted synthetic-note score as unmodified competition
accuracy, unseen fact generalization, calibrated confidence or human validation.
