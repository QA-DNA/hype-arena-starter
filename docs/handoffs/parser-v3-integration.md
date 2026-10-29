# Parser V3 integration

- Status: release verification, 29 October 2026.
- Human owner: unassigned. Coordinator: Codex, Run `run_f81fd1639515`.
- Authorization: Teodor requested implementing a cleaner, substantially better
  parser, investigating failures, and using parallel isolated agents as needed.
- Base: `22fa97b6fe27fcfa8d0bab7ae2e85c10c5386148`.
- Integration branch: `teodorbalan/parser-v3-integration`.
- Integration paths: core context/program exports and exact evaluation, CLI
  routing, runtime research adapters, integration tests and documentation.
- Binder worker: `parser-v3-binding`, `structured.rs` and its isolated tests.
- Program worker: `parser-v3-program`, new `claim_program.rs` and isolated tests.
- Independent evaluator: `parser-v3-evaluation`, challenge factory/scoring and
  adversarial review only. No production parser imports in its oracle.

## Acceptance and data boundary

Preserve organizer files, offline CPU operation and the frozen selected-v2 model.
Keep parsing independent of evidence truth, labels and private target fields.
Preserve logical structure rather than flattening disjunction/negation into a
conjunction. Resolve ownership through wording, legal attributes and explicit
document context; ambiguous references stay unresolved. Context must not cross
documents or become trusted factual evidence. Bound input size, memory and depth.

Compare against the original parser on released development examples and public
practice, retaining regressions. Keep new final challenge wording/gold separated
until implementation freeze; report parser structure/status independently from
truth classification. Prior 87.58% and million-pool scores remain historical
measurements and cannot be silently reused as fresh scores for this version.

The coordinator records final interfaces, measured improvements, validation and
remaining limits here after all worker deliveries and independent checks settle.

## Integrated release

Edi's `origin/main` chain port at `0dda354` is merged. The public APIs are
`ClaimParser::compile/parse`, `ExtractionHints.programs`, exact
`program_verification::verify` and `belief::compose`. Parsing is shared in core;
the CLI handles model process input/output, deadlines and atomic publication.
Ordinary conjunctions preserve the measured neural fallback. OR, grouped NOT,
slot comparisons and unsupported logical constructs retain their AST and cannot
become a positive bag of accepted facts. `ClaimContext` requires a document ID;
the official CSV does not supply one, so competition routing passes `None`.

The production chain preserves exact proofs, program decisions and unknown or
missing extraction. It keeps the measured reference emissions: a neutral-vote
variant worsened practice arena/Brier results and was rejected. Duplicate target
votes are capped and self-source exclusion is normalized. Confidence is no longer
rounded to tenths, and CSV serializes the full Rust score. Source observations
remain distinct from proved validity intervals. See the
[chain audit](chain-v3-audit.md), [belief interface](belief-v3.md),
[raw-literal fix](parser-v3-refinement.md) and
[independent parser evaluation](parser-v3-runtime-evaluation.md).

The root `Dockerfile` and `Dockerfile.competition` build the standalone Linux
amd64 CPU image from source. A 31,411,858-byte public archive of existing frozen
weights and ONNX libraries is fetched only at build time and checked against
SHA256 `44692ff8fae56274e416b74c6cabc25801511998a2d0b9fae54bb81a7fade0c9`;
individual model/library hashes are checked too. It is available in the
[runtime asset release](https://github.com/teodorbalan/VERIDYCT/releases/tag/runtime-assets-20261029).
No local ignored model files, runtime network, LLM, GPU, or root runtime user
is required. The former web-only Dockerfile is `Dockerfile.workbench`.

## Measurement limits

The binder's released development practice subset improves from 338/390 to
339/390 exact rows, with no exact-row regressions; the literal fix preserves all
339 and all 328 pure-neural fallbacks. These examples are development data.
The separate logical/binder tests cover semantic invariants; their pass rate is
not arbitrary-English accuracy. The independent development challenge includes
harder constructions and retained failures. Final reserved 2,048 wording/gold
remains unopened; no unseen-final score is claimed for this release.

The user's 20 rows have no reference labels, so their label distribution is not
an accuracy measurement. Earlier frozen million-world and evidence-graph scores
do not automatically apply to this changed release. A final router-wide duplicate
cap aggregate and independently calibrated three-class probabilities remain
unmeasured. The 13 belief tests check valid masses, logical laws and 2,916
correlated-joint cases; marginal bounds are epistemic diagnostics, not empirical
calibration. Complex unsupported English can still abstain.

Final Docker/official-checker receipts are retained under ignored
`artifacts/submission-v3` and `artifacts/arena-*`; only checks actually completed
are reported in delivery.
