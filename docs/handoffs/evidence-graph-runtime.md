# Evidence graph CPU candidate — final handoff

Status: implemented and validated for this evaluation round, 29 October 2026.
Owner: Codex coordinator; human ownership unassigned. Orca Run `run_bb66820b78cc`.
Isolated checkout/branch: `evidence-graph-runtime` / `teodorbalan/evidence-graph-runtime`.
Base: `d0af1691d49887870eb6dd638cf439afb7e7182d`. Evaluation was completed with
uncommitted sources, preserved byte-for-byte in the frozen snapshot. Teodor
subsequently authorized committing, merging and pushing the implementation and
documentation on 29 October 2026. The existing running workbench is not redeployed.

The [Romanian stack report](../research/evidence-graph-stack.ro.md) records the
full explanation also delivered on the Desktop. Its historical no-commit note
describes the state at the original evaluation freeze.

## Result and limits

The complete non-LLM CPU solver classifies input and produces 1,000 generated
claims. Its frozen final accuracy is **4,387/5,000 (87.74%)** and
**17,516/20,000 (87.58%)** on two fresh independently generated worlds, including
reserved wording families. The same source/model/configuration was used for both;
both inference runs completed before either gold score was opened. These controlled
worlds do not certify unrestricted English or the organizer's hidden truth base.

The 20,000-target result has macro-F1 .87484, definitive coverage 58.17%, and
94.42% accuracy among definitive predictions. Unsure is included in overall
accuracy. True precision/recall are .97744/.74081; false precision/recall are
.91871/.90685; unsure recall is .97975. There are 2,484 wrong labels, including
incorrect abstentions. Model confidence remains uncalibrated.

Development reached 1,000/1,000 labels and 1,000/1,000 independently true generated
forms after tuning. The independent text checker certifies only 83 of those texts;
917 non-fact formulations remain outside its bounded grammar. No private-referee
pass or sealed generated-claim truth result is claimed. The organizer format checker
passes on practice and on the full 20,000-target output, with 1,000 new claim rows.

## Runtime and source ownership

[Decision 0003](../decisions/0003-compiled-evidence-graph.md) describes the boundaries.

| Component | Delivered source | Behavior |
| --- | --- | --- |
| Typed values | [typed.rs](../../crates/core/src/typed.rs) | Exact decimal rationals, physical units, separate money/time channels, numeric version order |
| Explicit time | [temporal.rs](../../crates/core/src/temporal.rs) | Inclusive written scopes, separate from page dates |
| Evidence | [knowledge.rs](../../crates/core/src/knowledge.rs) | Positive/negative constraints, conflict abstention, false-conjunction unit propagation, provenance |
| Binding | [structured.rs](../../crates/core/src/structured.rs) | Schema/text-only entity and attribute ownership, raw values/operators, unknown declarations |
| Verification | [engine.rs](../../crates/core/src/engine.rs), [boosted.rs](../../crates/core/src/boosted.rs) | Full-world seed guard, supplied-world evidence, optional partition-validated GBT |
| Generation | [claims.rs](../../crates/core/src/claims.rs) | Trusted-source templates, typed comparisons, temporal joins, deduplication and MMR |
| Native extraction | [extractor](../../crates/extractor/Cargo.toml) | Isolated safe Rust/ONNX CPU crate, frozen model parity, bounded candidate metadata |
| Competition adapter | [parser.rs](../../crates/cli/src/parser.rs), [main.rs](../../crates/cli/src/main.rs) | Optional native helper, schema binding, extraction hints, atomic CSV |
| Complete image | [Dockerfile.competition](../../Dockerfile.competition), [build tool](../../tools/build-competition.ps1) | Multi-stage source build; no Python, Cargo, GPU or runtime LLM in final image |

Core stays independent of HTTP/CLI. The HTTP workbench shares the changed reasoning
core when rebuilt, but does not invoke the CLI's optional native extraction adapter.
The existing running container remains its previous version.

Only labelled true assertions license positive evidence/generation. Repeated blank
labels and model-predicted true labels do not. False compound rows are not treated
as all-negative. Query IDs/texts cannot provide their own evidence. Explicit validity
never extends from publication order. Foreign worlds cannot inherit practice truth.

`ExtractionHints` distinguishes intentionally empty parses, incomplete clauses and
explicit unknowns. A partial match cannot trigger a hard true proof. In source-only
foreign worlds unresolved clauses abstain; practice/canonical queries can still use
a clearly statistical learned fallback. Explicit unknowns stay unsure unless another
conjunct is independently refuted. Generic whole-row neural fallback is not mistaken
for proof that a clause was omitted.

Context defaults to `none`, because CSV adjacency is not a document boundary.
`previous3text` remains experimental; robust long-distance cross-row coreference is
not solved. Exact public practice forms take precedence for known source texts.
Exact-length batching avoids the frozen BiLSTM's measured padding dependence.

## Measured experiments

| Experiment | Result | Interpretation |
| --- | --- | --- |
| Native parser, paired390 | 336/390 exact; atomic F1 .92275 | Parser development, not fresh truth accuracy |
| Schema binder, paired390 | 338/390 exact, two improvements, zero exact-row regressions | 363 pure neural fallbacks unchanged |
| Current RF with native parsed queries | 316/390 labels (81.03%), macro-F1 .35960 | Clean 1,507-row verifier training partition |
| GBT with native queries | 340/390 (87.18%), macro-F1 .52163 | Same partition; full production routing |
| GBT + schema + final hints | 344/390 (88.21%), macro-F1 .53459 | Development selection; no all-practice checkpoint reuse |
| Over-broad incomplete adapter | 215/390 | Rejected regression; artifact preserved |
| Independent v3 initial pipeline | 52.1% labels; 730 claims | 686 true, 15 false and 29 unsupported forms |
| First schema integration | 93.7% labels, 1,000 claims | Still 16 false forms; preserved |
| Corrected independent development | 100% labels, 1,000 true forms | Tuned controlled language, not final generalization |
| Frozen fresh 5,000 | 87.74%, macro-F1 .87649 | Final one-shot score |
| Frozen fresh 20,000 | 87.58%, macro-F1 .87484 | Final one-shot score |

Final pure-Rust five-split reruns with partition-local GBTs: random 397/475,
bundle_group 395/475, template_group 396/475, forward_time 481/583,
every_fifth 328/380. No neural parser was used here because its training overlaps
some of these test examples. IDs and normalized duplicate query texts are excluded
from each verifier training partition. The folds overlap each other and remain
practice diagnostics. Unsure recall on these folds is zero.

The independent transductive probe is retained as research, without runtime
integration: mean accuracy .839453 baseline versus .840190 global clusters and
.837391 temporal clusters, worse log loss, unchanged false correctness and zero
unsure recall. It does not establish a robust gain from unlabelled agreement.

Other parser experiments were rechecked read-only after delivery. Factorized V3
scores 340/390 exact but CPU atom F1 .90760, below selected-v2's .92275; candidate
GNN controls do not establish a robust graph-specific gain. Those models are not
silently substituted after the final freeze. Remote preparation/export times do
not count as constrained complete-solver benchmarks. Sources: peer
`extraction-factorized-v3/labs/structured-extraction/FACTORIZED.md` at `b84987f`
and `extraction-graph-v3/labs/structured-extraction/GRAPH-EXPERIMENT.md` at `08cb599`.

## Final frozen artifacts

Freeze ID: `veridyct-cpu-20261029-final-v1`.
Confirmation: `2026-10-29T01:41:04.279704+00:00`.
Image: `veridyct:competition-candidate`,
`sha256:0ba3ab040d1c47bf5461796a804e2f1040198e1c9b6028bde5749c73475c5b16`.
Source snapshot SHA256:
`7033e2956fdb9a2ddcaa06f47c2585b5f4b97cdd3d7a51d8b4a286f0259ab63b`.

Ignored, local delivery assets:

- `artifacts/frozen-20261029/freeze.json`: solver/model/runtime hashes and policy.
- `artifacts/frozen-20261029/source.zip`: 425-file complete source snapshot.
- `artifacts/frozen-20261029/source-sha256.json`: source byte hashes.
- `artifacts/frozen-20261029/veridyct-cpu-image.tar`: portable offline Docker image.
- `artifacts/compiled-universe.json`: reviewable practice evidence graph, 850,606 B.
- `artifacts/universe-20261029-034127/`: final 5,000-target output, run and score.
- `artifacts/universe-20261029-034137/`: final 20,000-target output, run and score.
- `artifacts/arena-20261029-033858/`: actual practice format-contract run.
- `artifacts/universe-20261029-033259/`: development labels and versioned claims scores.
- `artifacts/paired390/metrics.json`: complete paired verifier A/B, including failures.
- `artifacts/final-folds/metrics.json`: final-source pure-Rust five-split metrics.
- `artifacts/evaluator-coverage/`: preserved before/after coverage correction reports.

The final bundles remain in the independent evaluator's isolated checkout; gold
was not mounted in either runtime container. Its scorer writes exclusive one-shot
markers before gold access and validates the explicit freeze receipt. No repeated
sealed scoring or post-final model tuning occurred. Subsequent edits to this handoff
and the Desktop report document the frozen result; they do not modify the snapshot
or the deployed image.

## CPU container measurements

Host: AMD Ryzen 9 6900HS; Rust release 1.90.0, Linux amd64, ONNX Runtime 1.23.2.
The two final runs partly overlapped; timings are measured execution results rather
than an isolated microbenchmark. One Rust reasoning thread, two ONNX intra-op threads.

| Run | Input rows | Hidden targets | Wall incl. Docker | Cgroup peak | CSV | Claims |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fresh 5,000 | 6,897 | 5,000 | 31.435 s | 250,576,896 B | 494,441 B | 1,000 |
| fresh 20,000 | 21,897 | 20,000 | 86.515 s | 767,528,960 B | 1,125,842 B | 1,000 |

Image unpacked size 221,169,123 B. Both containers exit 0; no GPU, network,
privileges or writable root. UID 10001, 2 CPU, 6 GiB/no additional swap,
256 PIDs, all capabilities dropped, no-new-privileges, tmpfs /tmp 128 MiB.
Output including diagnostics is 46,744,043 B on the large run, below 256 MiB;
Windows output bind usage is measured after execution, not enforced by a filesystem
quota. The unchanged official checker itself also uses an output bind mount.

## Reproduction

```powershell
# Assets must first be staged per tools/native_parser/README.md.
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build-competition.ps1

# Or load the already-built frozen image offline.
docker load --input artifacts/frozen-20261029/veridyct-cpu-image.tar

# Public input directory contains universe.csv and lexicon.json only.
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run-universe.ps1 -Universe C:/path/public -Image veridyct:competition-candidate -Structured -Batching exact-length

# Organizer files unchanged; this is format/familiar-practice validation.
powershell -NoProfile -ExecutionPolicy Bypass -File tools/arena-check.ps1 -Image veridyct:competition-candidate -SkipBuild
```

Large model/runtime assets remain ignored by Git; a fresh clone needs explicit
staging before a source build. The image export already includes every runtime
asset. ONNX integrity, production verifier integrity and partition membership are
checked; model scores are not independently calibrated probabilities.

## Validation and task outcomes

Coordinator checks: `cargo xtask test` passes 47 tests; `cargo xtask check` passes
formatting, all-target Clippy, local documentation and organizer checksums. The
isolated binder passes 24 semantic tests. Native grammar four tests and all three
staged-model frozen tests pass; native all-target Clippy passes. All 59 independent
evaluator tests pass. The unchanged output checker passes both practice and the
20,000-target output. Source/model identity and leakage guards have separate
reports; old failed outputs and pre-correction scores were not overwritten.

All supervised tasks have settled and their terminals were released:

| Task | Outcome and durable report |
| --- | --- |
| Practice evaluation | Delivered [evaluation handoff](evidence-evaluation.md) |
| Frozen parser integration | Delivered [Python prototype handoff](neural-parser-integration.md) |
| Adversarial semantic audit | Delivered [review](evidence-adversarial-review.md) |
| Native CPU port | Delivered [native handoff](native-parser.md) |
| Verifier laboratory | Delivered [verifier handoff](verifier-lab.md) |
| Independent world factory | Delivered [evaluation handoff](independent-evaluation.md) |
| Five split verifier checks | Delivered [fold handoff](verifier-folds.md) |
| Transductive experiment | Delivered, negative integration recommendation: [handoff](transductive-verifier.md) |
| Schema binder | First Claude attempt stopped after provider retries without source; Codex retry delivered [binder handoff](structured-parser.md) |
| Evaluator coverage audit | Delivered [coverage handoff](evaluator-coverage.md) |

The coverage revision adds conventional physical aliases and a bounded record-fact
text grammar, preserving all dataset/gold bytes and prior reports. On each audited
development run exactly two inch forms changed world status from unsupported to
true. Original false/unsure results and mixed-date unsupported cases stay unchanged.
Prototypes v1/v2 were retired for sampling confounds; all final scoring uses the
corrected v3 bundles. See the evaluator handoffs for assumptions and open limits.

The main remaining issue is generalization to unfamiliar wording and semantic
ownership, followed by reliable unknown handling on practice-style data. Another
model-selection round needs new independent evaluation data. The frozen final
scores must remain the record for this delivered candidate.
