# Five-split boosted verifier validation

- Status: delivered, 2026-10-29; modest practice gains, no final-score claim.
- Task: `task_33f61792b815`, dispatch `ctx_b92cb31855a0`.
- Agent owner: five-split boosted verifier validation. Human owner unassigned.
- Checkout/branch: `evidence-verifier-folds`, `teodorbalan/evidence-verifier-folds`.
- Base: `d0af1691d49887870eb6dd638cf439afb7e7182d`.
- Authorized paths: `tools/verifier_folds/`, the new core example, this handoff.
- Acceptance: five Mihai partitions, pure Rust inference, excluded IDs/texts,
  fresh portable models, full Engine routing, metrics/parity/provenance and commands.

The [gold-free evaluator](../../crates/core/examples/evaluate_boosted.rs) and
[reproduction tools](../../tools/verifier_folds/README.md) implement the measured
CPU evidence direction in [decision 0002](../decisions/0002-evidence-mvp.md).
No root-owned engine/model/knowledge/boosted code is changed. The advanced core,
manifests and lockfile are copied into ignored `artifacts/verifier-folds/current/`
and hashed. The originalRF comparison uses the checked-in original MVP at base;
currentRF and newGBT share the advanced frozen kernel.

Every test query has a blank label and empty form. IDs and normalized test texts
are removed before creating any Engine or evidence index. Fit parses use five
fixed, text-grouped crossfit blocks through the same Rust Engine; their feature
index physically excludes the query ID and every normalized copy. Other proper
training forms remain usable evidence. Outer prediction uses the complete cleaned
train partition, the Value-first model loader, membership guard and actual
`Engine::predict`, including production graph/confidence overrides.

No neural parser, model search, calibration fit, external world, reserved final
gold, commit, push or deployment is used. The model settings were preselected on
the original paired390 experiment's inner307 only: GBT 120 iterations, depth 2,
minimum leaf 20, learning rate 0.045, subsample 1, seed 417; `lex.*`/`cue.*` omitted,
no class balancing. The five practice partitions are diagnostic, because practice
facts overlap and the original model selection used other practice examples.

## Measured full Engine results

Accuracy includes production graph and confidence routing, rather than raw GBT
argmax. Test counts are the unchanged Mihai partitions. Excluding normalized test
copies removed 7, 0, 0, 8 and 4 training rows respectively; every remaining model
has zero test-ID and normalized-test-text overlap.

| Split | Clean train / test | Majority accuracy | OriginalRF accuracy | CurrentRF accuracy | GBT correct | GBT accuracy | Delta currentRF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| random | 1,415 / 475 | 83.37% | 76.63% | 83.16% | 397 | 83.58% | +2 rows |
| bundle_group | 1,422 / 475 | 83.16% | 74.74% | 83.16% | 395 | 83.16% | 0 |
| template_group | 1,422 / 475 | 83.16% | 78.53% | 82.74% | 396 | 83.37% | +3 rows |
| forward_time | 1,306 / 583 | 82.50% | 70.84% | 82.68% | 481 | 82.50% | -1 row |
| every_fifth | 1,513 / 380 | 85.26% | 80.26% | 85.53% | 328 | 86.32% | +3 rows |

| Split | Model | Macro-F1 | Non-unsure coverage | Log loss | Brier |
| --- | --- | ---: | ---: | ---: | ---: |
| random | currentRF | 0.32878 | 100.00% | 0.51364 | 0.27240 |
| random | GBT | 0.37929 | 99.58% | 0.49137 | 0.26940 |
| bundle_group | currentRF | 0.33694 | 99.79% | 0.53417 | 0.28722 |
| bundle_group | GBT | 0.35164 | 99.79% | 0.52639 | 0.28554 |
| template_group | currentRF | 0.32729 | 100.00% | 0.53363 | 0.28648 |
| template_group | GBT | 0.37636 | 100.00% | 0.52274 | 0.28291 |
| forward_time | currentRF | 0.30868 | 100.00% | 0.54344 | 0.29649 |
| forward_time | GBT | 0.33341 | 99.83% | 0.54526 | 0.30105 |
| every_fifth | currentRF | 0.35465 | 100.00% | 0.43899 | 0.22912 |
| every_fifth | GBT | 0.39572 | 100.00% | 0.42544 | 0.22396 |

The GBT improves macro-F1 on all five folds, accuracy on three, and log loss/Brier
on four. Forward-time accuracy and probability scores regress slightly. Majority
uses the cleaned-train class frequencies as probabilities, with the most frequent
class as its prediction. All model/baseline per-class precision, recall and F1,
confusion matrices, coverage, log loss and Brier are in ignored
`artifacts/verifier-folds/results.json`; Brier sums the three squared errors before
averaging over rows. Macro-F1 includes all three labels, undefined F1 zero.

GBT confusion matrices, rows gold and columns predicted in true/false/unsure order:

| Split | Confusion | False precision / recall / F1 |
| --- | --- | --- |
| random | `[[387,8,1],[58,10,1],[9,1,0]]` | 0.52632 / 0.14493 / 0.22727 |
| bundle_group | `[[389,5,1],[64,6,0],[10,0,0]]` | 0.54545 / 0.08571 / 0.14815 |
| template_group | `[[386,9,0],[60,10,0],[8,2,0]]` | 0.47619 / 0.14286 / 0.21978 |
| forward_time | `[[476,4,1],[89,5,0],[7,1,0]]` | 0.50000 / 0.05319 / 0.09615 |
| every_fifth | `[[320,4,0],[41,8,0],[7,0,0]]` | 0.66667 / 0.16327 / 0.26230 |

All unsure precision/recall/F1 values are zero. High coverage does not establish
good uncertainty handling. These fold results do not reproduce the much larger
gain previously measured with neural inferred forms on paired390; that pretrained
parser was deliberately excluded here because it saw many of these test rows.

## Parsing and production routing audit

The post-prediction `error-audit.json` scores supplied gold forms as typed JSON sets
(order/duplicates ignored, numeric 1 equals 1.0, strings/operators/units distinct).
It does not feed a gold form into prediction or refit a model.

| Split | Exact parses | Empty parses | Verdict errors with exact parse | Verdict errors with inexact parse | RF errors fixed / introduced |
| --- | ---: | ---: | ---: | ---: | ---: |
| random | 167 / 475 (35.16%) | 240 | 20 | 58 | 7 / 5 |
| bundle_group | 95 / 475 (20.00%) | 312 | 13 | 67 | 2 / 2 |
| template_group | 166 / 475 (34.95%) | 238 | 15 | 64 | 7 / 4 |
| forward_time | 168 / 583 (28.82%) | 349 | 29 | 73 | 4 / 5 |
| every_fifth | 146 / 380 (38.42%) | 181 | 17 | 35 | 4 / 1 |

Both extraction and verification remain weak. The audit retains changed outcomes,
gold/inferred forms and first errors for the coordinator's separate parser work.
Graph/confidence routing changes 7, 4, 5, 1 and 5 raw GBT argmax labels respectively.
Raw fallback correct counts are 401, 397, 396, 482 and 327; only full Engine counts
above are pipeline results. No graph rule or confidence threshold was changed.

## Artifacts and identity

All generated assets are ignored, local to this checkout under
`artifacts/verifier-folds/`. `protocol.json`, `current-source-sha256.json`,
`original-source-sha256.json`, `lab-source-sha256.json`, `build-sha256.json` and
`artifact-sha256.json` record source, data, request, feature, binary and output
identities. Original manifests/lockfiles remain beside derived core-only copies.

| Model artifact | SHA256 |
| --- | --- |
| `models/random.json` | `bcf6afc88ec8018e17af1781a8e50d02975d421fbde0c08ee07a5cc15af232de` |
| `models/bundle_group.json` | `cfe2f8695aeac60af6c166877eceaa7d612a51e6cdef6fbdede67ce14cf9a814` |
| `models/template_group.json` | `7b2a52db3287ba1acf13811547378f50ac509fb7bd26a037c30128a7e850233f` |
| `models/forward_time.json` | `711c550eab747043f578f5ffc0b4a960c3d5b36cbaf6caf5bd36852193d17920` |
| `models/every_fifth.json` | `39c42479bfeff5b065fe79ad826cb549920a724fb118184ed7eb52263ede48bd` |

Key frozen hashes:

- engine: `61f88e96a8edd53006cabbe379340070ce8b9a33561e325fae6a4f42f2053ecc`
- boosted: `117c43145179f3506a65362c15ca6fb876283163468dae79660cbc457a11a41c`
- knowledge: `d2cecbc0a4d9e8edde72ca92207371123fb844cb43d05dbb0df4b6dba1f1e9cf`
- typed: `07086bd5a62166b6b951d51312c6ccf3605aea2385f924f79c19cd52c80d3aac`
- practice CSV: `52743befaa0fa38b89b5c802c0f953d242ae027c86839c9c0f05a9e69a86d8e9`
- lexicon: `d0fd5e9bdc6b33ad3ec160001f50e00e7f8bf2b25a92779022f893db7c3d5507`
- assignments: `e84baec6fc52372d4e6adaa8771ab58a11ee75191e28343ee299b6f6cc53f8af`

Each portable artifact has train IDs, normalized-text SHA256 lists, FNV signatures
of ID/date/label/text, exact request/feature/source hashes and the frozen settings.
Python portable probabilities equal sklearn exactly. Across all 2,388 outer row
evaluations, Rust feature/logit maximum error is zero, probability error is at most
`2.220446049250313e-16`, and raw predicted classes are identical. CurrentRF and GBT
query forms are identical. All source/model checks use the Value-first loader.

`guards/results.json` proves a bundle checkpoint is rejected against random's
training partition, and a labelled test query is rejected, both before output
creation. Every emitted evidence row ID is checked against its train partition.

## Verification and reproduction

The [README commands](../../tools/verifier_folds/README.md) reproduce staging,
release builds, crossfit features, five fixed fits, full predictions, guards,
reporting and post-prediction error analysis. `commands.jsonl` retains actual Docker
argument arrays and durations. No organizer files or protected source files changed.

Hardware: AMD Ryzen 9 6900HS with Radeon Graphics. Release Rust/Cargo 1.90.0,
Docker image `sha256:fd69385ab339602c033529a3b21e751750ad6757f148e3a894e953800fa79210`,
`--user 0 --network none --cpus 2 --memory 6g`, one Rust compute thread. Host training:
Python 3.14.0, NumPy 2.4.4, sklearn 1.9.1, two configured threads. Fits took
4.66-6.79 seconds per split. Full GBT engine construction, prediction and parity
export took 3.23-3.70 seconds, peak RSS 39,396-44,032 KiB. Crossfit export took
25.10-43.95 seconds and reached 77,972 KiB; other development tasks ran concurrently,
so these are diagnostic measurements rather than a controlled benchmark.

- `py -3.14 tools/verifier_folds/test_protocol.py`: three boundary/metric tests pass.
- Python compilation of the owned tools passes.
- `cargo xtask test` in the isolated foundation copy: 43 tests pass, including
  36 core tests. The validation copy uses frozen advanced core plus checked-in
  adapters/tooling, not the coordinator's ongoing native/schema integration.
- Separate workspace/all-target Clippy with warnings denied passes.
- The evaluator's two Rust leakage-boundary tests and formatting of both owned
  Rust files pass.
- Separate `cargo xtask docs` passes 122 local links, graph validation and all
  organizer-file checksums.
- `cargo xtask check` was run and fails at formatting in the frozen root-owned
  `engine.rs` and `lib.rs`. This worker preserves their recorded bytes and reports
  that failure; it does not claim the full check passed.

The coordinator owns final root formatting/integration and any future parser
improvement. These five per-split checkpoints are diagnostic models, not an
all-practice production checkpoint. A new independent final evaluation remains
unopened. No commits, pushes, deployments or organizer modifications were made.
