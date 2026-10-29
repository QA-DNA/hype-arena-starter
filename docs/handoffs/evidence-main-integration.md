# Evidence solver integration into main

- Status: validated integration, 29 October 2026.
- Human owner: unassigned. Agent owner: Codex coordinator.
- Authorization: Teodor requested commit, merge and push before evaluating
  `Downloads/veridyct-million.zip`.
- Integration checkout/branch: `evidence-release-integration` /
  `teodorbalan/evidence-release-integration`.
- Parents: remote main `fa05456cd7c1c31a8c30375b7aca200aba9fc514` and solver
  implementation `20b94a3` (`teodorbalan/evidence-graph-runtime`).
- Scope: combine the implemented solver and explanation/evaluation tools with
  the current main's text-preprocessing pipeline and research. Preserve organizer
  files and both sets of working commands. No deployment.

The [solver handoff](evidence-graph-runtime.md) and
[Romanian stack report](../research/evidence-graph-stack.ro.md) describe the
implementation, independent frozen results, artifacts and limitations. Those
historical scores remain unchanged; they are not scores on the million archive.

## Resulting behavior

The core exports the existing `extraction` module alongside the typed temporal
evidence graph, verification and generation modules. The CLI retains `info`,
`run`, `lexicon compile`, `normalize`, `split` and `parse`. Preprocessing commands
remain independent of truth inference. Main's research, extraction tests and
documentation links are retained. The project graph combines both sets of nodes
and relationships. The new solver source and model weights are not tuned during
integration.

The optional complete CPU build remains [Dockerfile.competition](../../Dockerfile.competition).
Runtime model/library files and raw run outputs are ignored by Git; explicit
staging instructions and model hashes accompany the source. The frozen portable
image from the earlier evaluation is retained separately.

## Validation before publication

- `cargo xtask check`: passes formatting, all-target Clippy, 348 documentation
  links, 17 graph nodes, 16 relationships, and unchanged organizer checksums.
- `cargo xtask test`: all 79 workspace tests pass, including six preprocessing
  CLI, 11 discourse and 15 extraction tests from main, plus solver/API tests.
- Complete CPU image source build: passes with production model hash checks.
- Actual offline 2-CPU/6-GiB format run: exit 0, 380 required labels and 1,000 new
  claims; unchanged organizer checker passes. Its familiar-practice diagnostic
  reports 373 correct definitive labels, zero wrong, seven unsure, rather than
  independent generalization accuracy.
- `git diff --check`: passes. No organizer dataset, contract or checker edits.

Integration image: `veridyct:merged-million-baseline`,
`sha256:4fa26b584fc41af6c73e056d55b76bc1f96a3ff22f159c30809c8fc562d271a3`,
221,990,428 unpacked bytes. Hardware/compiler/runtime environment is the same as
the prior handoff. Local format-run evidence is in ignored
`artifacts/arena-20261029-053726/`.

The million-archive evaluation follows publication, with public solver inputs
separated from scoring-only annotations. Its results will be recorded separately.
