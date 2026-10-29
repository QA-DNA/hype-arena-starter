# Verifier research and training

- Status: delivered for integration; no independent final evaluation claimed.
- Task: `task_3251cf8800e9`, dispatch `ctx_73070eff7fbe`, 2026-10-29.
- Agent owner: verifier research and training. Human owner remains unassigned.
- Checkout/branch: `evidence-verifier-lab`, `teodorbalan/evidence-verifier-lab`.
- Base: `d0af1691d49887870eb6dd638cf439afb7e7182d`.
- Authorized paths: `tools/verifier_lab/`, new `boosted.rs`, feature/world examples,
  and this handoff. Root owns engine, forest, knowledge, typed comparisons and CLI.
- Acceptance: repeatable oracle/inferred comparison, partition-safe model training,
  portable Rust inference, source/artifact hashes, actual errors and honest limits.

## Result and API

[The reusable module](../../crates/core/src/boosted.rs) adds an experimental
classifier without changing default engine behavior or the dependency graph.
It retains per-atom minima, means and maxima for typed evidence, contradiction,
numeric distance, dates, prior/future observations and property information.
Hashed lexical features were measured; the selected model excludes them.
No inferred assertion becomes accepted evidence through this module.

```rust
let verifier = BoostedVerifier::from_json(checkpoint_json)?;
verifier.validate_training_partition(training_rows)?;
let index = FeatureIndex::compile(training_rows);
let features = index.features(query_with_blank_label, inferred_facts);
let probabilities = verifier.predict(&features)?; // true, false, unsure
```

`predict_logits` exposes raw scores for parity. Use `from_json`: direct typed
deserialization shifted one exact threshold by one ULP in the experiment.
The Value-first loader and root's `serde_json/arbitrary_precision` preserve it.
Do not apply the balanced Random Forest's prior restoration to GBT scores.
These probabilities have not received independent calibration.

The partition guard compares IDs and FNV signatures of source text/date/label.
Artifact SHA256 and normalized-text SHA256 lists provide the separate audit.
It rejects the all-practice checkpoint against the 1,507-row training partition
before the harness creates an output file. The caller must run this guard when
attaching a checkpoint to an engine.

## Practice diagnostic and ablations

All 390 outer IDs and their Unicode NFKC/casefold/whitespace-normalized texts are
excluded from verifier training. The remaining 1,507 rows split into 1,200 fit
and 307 validation rows. Training features exclude the query ID and text from
evidence. Inferred empty forms stay empty in fit features; exact-text template
reuse must not recover a training form and make parser quality appear perfect.
Training uses supplied practice forms for other labeled evidence, which is allowed.

Fifty candidate/configuration combinations covered gradient boosting, Random
Forest, Extra Trees and regularized multinomial logistic regression. Selection
used only inner validation accuracy, then macro-F1, then log loss. The selected
GBT has 120 iterations, three class trees per iteration, depth 2, minimum leaf
20, learning rate 0.045, seed 417 and no class balancing.

| Best inner validation configuration by feature ablation | Correct / 307 | Accuracy |
| --- | ---: | ---: |
| No lexical features, GBT | 283 | 92.18% |
| All features, Random Forest | 283 | 92.18% |
| No property identities/label priors, GBT | 282 | 91.86% |
| Evidence features, Random Forest | 282 | 91.86% |
| Lexical/row features, Random Forest | 269 | 87.62% |

The lexical-only winner predicts the majority class. The selected model's gains
come with substantially better false recall, rather than a different abstention
or majority rule. Frequent tree splits use distances to supporting/contradicting
observations and typed numeric differences.

| Outer 390 diagnostic | Correct | Accuracy | Macro-F1 | False correct / 74 |
| --- | ---: | ---: | ---: | ---: |
| Majority | 312 | 80.00% | 0.29630 | 0 |
| Initial graph/RF, inferred parse | 313 | 80.26% | 0.34325 | 6 |
| Initial graph/RF, oracle query parse | 316 | 81.03% | 0.33956 | 5 |
| Initial graph + selected GBT, inferred | 340 | 87.18% | 0.52115 | 41 |
| Exact-type graph/RF, inferred | 316 | 81.03% | 0.35960 | 8 |
| Exact-type graph + same selected GBT, inferred | 339 | 86.92% | 0.51711 | 40 |

Exact-type GBT confusion, rows gold and columns predicted in true/false/unsure order:
`[[299,13,0],[34,40,0],[4,0,0]]`. It still misses all four unsure rows.
Log loss improves from 0.48322 to 0.35026 against the same exact-type RF.
No hyperparameter was retuned after opening the 390 outcomes or refreshing types.

An oracle-form training diagnostic selects a Random Forest at 353/390 and its
best portable GBT reaches 354/390 (90.77%). This is a component diagnostic with
gold forms and cannot be presented as an inferred pipeline result.

Actual remaining practice errors include `p-14`, â€œThe programme packed 40 sessions
into the scheduleâ€ (false; empty inferred form; predicted true), `p-59`, â€œHooly
Chrome does not include an AI sidebar yetâ€ (false; parsed correctly; predicted
true), and `p-121`, â€œHooly Android 17 supports 19 models in the betaâ€ (unsure;
predicted true). Full errors are in the ignored training reports.

## Synthetic development world and context

Archive SHA256:
`300623a5080ffb69eeb471e7069b88878f010059f73f002afee1995e00d99bc3`.
The archive's `GUIDE.md` was read first. Only development gold was opened here;
calibration and sealed gold were not read. The provided MMR selection's evidence
uses gold proof IDs, so it was not used as a retrieval input or model feature.
Every world uses its own public anchors. Synthetic facts never enter the
production practice evidence index.

[The world evaluator](../../crates/core/examples/evaluate_world.rs) calls root's
`predict_universe`, with canonical practice truth excluded from a foreign world.
Normal runs clear input forms and finish prediction before loading gold. Explicit
`--oracle-forms`, `--oracle-anchor-forms` and `--oracle-target-forms` modes are
clearly marked component diagnostics. Public interval prefixes are removed only
for neural parsing through root's `explicit_scope`; original text/date/labels
remain in solver input. Gold expected values, world IDs, proof selections and
gold context pointers never become features.

Same exact-type snapshot, 18,103 hidden development targets and 1,897 anchors:

| Parse/context mode | Correct targets | Accuracy | Target tuple exact | Anchor tuple exact |
| --- | ---: | ---: | ---: | ---: |
| Oracle anchors and targets | 18,103 | 100.00% | 100.00% | 1,897 / 1,897 |
| Neural, context off | 17,649 | 97.49% | 95.82% | 1,896 / 1,897 |
| Neural, actual prior three public texts | 18,044 | 99.67% | 98.30% | 1,893 / 1,897 |
| Context off for public labeled anchors, on for targets | 18,076 | 99.85% | 98.30% | 1,896 / 1,897 |

The mixed policy selects passes using only public label availability. Its 27
verdict errors all have mismatched target forms; there are no exact-target
reasoning errors. Confusion is `[[15064,7,17],[1,2640,2],[0,0,372]]`, macro-F1
0.99079. Four bad anchors in the all-context pass cause 32 additional errors on
exactly parsed targets, illustrating why anchor parsing matters independently.

Remaining examples include `r-9bea2c42dfb4c66939bb00`, â€œThey have it on API version
11.3â€ (true, empty parse, unsure); `r-66ca8957c15cf6a4df7653`, a Maps row whose
second pronoun-bound release-date atom is assigned to Photos (true, false); and
`r-95cbe0a7034ebf0e682ce9`, a Chrome conjunction missing its user-count atom
(false, true). Reports retain up to 100 errors plus all target predictions.

The archive zero-pads versions for equality; the official contract says written
versions such as `2.3` and `2.3.0` differ. Production keeps official semantics.
No version-policy disagreement caused an error in this development oracle run.

## Artifacts, parity and boundaries

All assets below are ignored, under `artifacts/verifier-lab/`:

| Asset | SHA256 |
| --- | --- |
| `models/inferred-no_lexical-gbt-exact.json` (1,507 training rows, 442,745 bytes) | `80eb4f2701052b4f8524da8ecc0df8655f12b27ad928b6115fa7d8da6583c307` |
| `models/PRODUCTION-all-practice-gbt.json` (1,897 rows, 482,706 bytes) | `007d278c95e5cffc785efb89a66ca0b2d2b9428b74f02986798dd2da716c8f59` |

The production checkpoint has no heldout score. Never use it for any Mihai split
or the 390 diagnostic. Each other split needs its own excluded training partition
and checkpoint; parser exposure also prevents treating other practice splits as
clean paired pipeline tests. The old-core 87.18% artifact remains separate.

`parity-exact390.json` verifies all 390 rows: feature maximum absolute error 0,
logit error 0, probability error `4.336808689942018e-19`, identical classes, zero
training/test ID overlap and zero normalized-text hash overlap. Python exported
tree probabilities match sklearn exactly. Node validation rejects invalid child
indices/cycles and non-finite model values.

Source copies and hashes are in `baseline/`, `baseline-source.json`,
`world-baseline/` and `exact-world/source-sha256.json`. Exact-world kernel hashes:
engine `40f6c0e9a3868e060c851a266816212e2f5de283f5f4765dde2bc92ef2ce2934`,
knowledge `d2cecbc0a4d9e8edde72ca92207371123fb844cb43d05dbb0df4b6dba1f1e9cf`,
typed `07086bd5a62166b6b951d51312c6ccf3605aea2385f924f79c19cd52c80d3aac`.
These are copies of uncommitted root integration source, not a published commit.

Runtime: AMD Ryzen 9 6900HS host; release Rust 1.90; single Rust computation
thread under Docker `--cpus 2 --memory 6g --network none`. Exact-type world
prediction took 7.74â€“8.74 seconds in these runs. Host Python 3.14.0 with NumPy
2.4.4/sklearn 1.9.1 ran the frozen two-thread neural helper: 34.56 seconds without
context and 81.29 with context. These host/helper timings are not a constrained
full competition-container benchmark, and this worker did not measure peak RSS.

Both development world and practice 390 are diagnostic: their outcomes informed
earlier parser selection and/or current routing. A new frozen independent-world
test remains for the coordinator. The coordinator subsequently reported only
51.1% accuracy on a new 1,000-target style-transfer development set; this worker
did not run that report. The old-family 99.85% result does not establish broad
generalization. No new sealed final test has been opened or scored.

## Reproduction and verification

[Lab commands](../../tools/verifier_lab/README.md) cover snapshotting, feature
export, training, context routing and parity. Raw reports are
`training-inferred.json`, `training-inferred-exact.json`, `training-oracle.json`,
`production-model.json`, `world-oracle-exact-v2.json`, `world-neural-exact-v2.json`,
`world-context3-exact-v2.json` and `world-mixed-exact-v2.json`.

Initial `cargo test -p veridyct-core --example verifier_features` passed 19 tests,
including three feature/model boundary tests and the copied graph/engine tests.
`cargo xtask check` passed formatting, Clippy with warnings denied, 123 local
links, graph validation and organizer checksums. Docker required a read-only
mount of the common Git directory plus `GIT_DIR`, `GIT_COMMON_DIR` and
`GIT_WORK_TREE` because this Windows worktree's `.git` path is not a Linux path.
Python compilation of all lab tools also passed. `cargo xtask test` passed all
23 workspace tests (API, CLI integration, core and tooling).

No organizer files, root-owned implementation, commits, pushes or deployments
were changed. This work extends the measured CPU evidence direction in
[decision 0002](../decisions/0002-evidence-mvp.md); root owns activation in Engine.
