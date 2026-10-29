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

## Final release receipt, 29 October 2026

- Root Dockerfile built successfully with the default public Rust 1.90 builder,
  no staged local assets or builder override. Runtime image `veridyct:submission-v3`,
  ID `sha256:9ea562af53ef29a02cb40075a24eb5935938b1e9edaad0993e6c20d96c43a080`,
  unpacked size 222,884,235 bytes; configured USER `10001`.
- `cargo xtask check`: format, all-target Clippy with warnings denied, 404 local
  documentation links, project graph and organizer checksums passed.
- Official unchanged `scripts/input.py` and `scripts/check_output.py`, via
  `tools/arena-check.ps1 -SkipBuild -Image veridyct:submission-v3 -Minutes 2`:
  offline read-only non-root 2 CPU/6 GiB run exited 0, 380/380 requested labels,
  1,000 new claims, 263,927-byte output and **the format checks pass**. Runtime
  reported 5.706 seconds. The 373 right/0 wrong/7 unsure familiar practice labels
  use allowed embedded exact matches and are not independent accuracy.
- Final image live20 run exited 0 in 7.492 seconds, produced 1,000 claims and
  label counts 3 true / 3 false / 14 unsure. No gold exists for those 20, and the
  chain's decided weights are statistical, not newly calibrated probabilities.
- The release contains a same-proposal independent development comparison:
  baseline AST331/512 versus intermediate shared native AST389/512. Native parse
 367/512 and semantic345/416 are separate metrics; subsequent literal fixes were
 not rescored on that challenge under the release deadline. Every failure is
 retained and the reserved final remains unopened.
