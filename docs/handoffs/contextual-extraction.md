# Contextual extraction implementation

- Status: implemented and validated; publication authorized on 28 October 2026
- Human owner: unassigned; implementation author: Codex.
- Branch/checkout: `feat/contextual-extraction`, `/tmp/veridyct-parser-v2`.
- Base: `51db366322abd98e5bbb735f93b2440b7a5988b0`.
- Scope: core extraction, CLI CSV adapter, lab viewer/evaluation, documentation.
- Acceptance: role-aware attachment, bounded nearby context with cross-row provenance,
  explicit version/scope preservation, regression tests and regenerated practice outputs.
- Plan: [context/version plan](../../labs/assertion-extraction/IMPROVEMENT-PLAN-2026-10-28.md).
- No solver, truth engine, external model service or organizer-file changes.

## Documentation and publication follow-up

The user requested saving the algorithm/library explanation and committing, merging
and pushing all pending task work. [Parser internals](../../labs/assertion-extraction/HOW-IT-WORKS.md)
records the implementation methods and limitations; the lab and documentation index
link it. Source, tests, review, plan and documentation are in publication scope.
Generated CSVs, binaries, benchmark outputs and viewer snapshots remain ignored.

## Delivered behavior

Core now exports `DocumentExtractor`, `SourceReference` and `Qualifier` alongside the
row-local API. Schema/index version 2 requires regeneration. CLI stream context is on
by default and accepts `--context off`. Viewer antecedent links and qualifier display
use the exported metadata; no second extractor exists in the UI.

See [results/manual inspection](../../labs/assertion-extraction/V2-RESULTS-2026-10-28.md),
[scope decision](../../labs/assertion-extraction/DECISION.md), and
[usage/schema](../../labs/assertion-extraction/README.md). No trained NLP model was
added: structural grammar and bounded discourse improve the reviewed cases without
training leakage or additional runtime dependencies. Unsupported shorthand and complex
syntax still need work; the broader plan is not claimed complete.

## Verification

All commands ran in the isolated checkout with Rust 1.90.0 and a checkout-specific
Cargo target directory (`/tmp/veridyct-parser-v2-target`).

- `cargo xtask check`: passed formatting, Clippy with warnings denied, documentation
  links/graph and organizer checksums. A Clippy style finding was fixed before passing.
- `cargo xtask test`: 38 tests passed across the workspace, including 11 contextual
  extraction tests and six CSV integration tests. Existing behavior tests were retained;
  the Holdan joining fixture now expects its newly supported correct pair.
- `node --test labs/assertion-extraction/tests/viewer.test.mjs`: four passed against
  regenerated outputs and diagnostic totals.
- `node labs/assertion-extraction/tests/viewer-browser.mjs /usr/bin/brave`: 44 browser
  checks passed, across 1440px and 390px widths, including antecedent navigation.
- Release generation and context-off ablation: 901 versus 755 paired occurrences;
  metrics and limitations are in the results document.
- `python3 labs/assertion-extraction/benchmark.py --binary
  /tmp/veridyct-parser-v2-target/release/veridyct`: 20,000 repeated practice rows with
  unique IDs and no forms/labels, 4.03 seconds, 41,084 KiB child-process peak RSS.
  Hardware: AMD Ryzen 7 6800HS; affinity CPUs 0/1; parser uses one thread. This is a
  scaling check, not a diverse unseen dataset or a full-solver benchmark.
- Native measured binary SHA-256:
  `2602e4d63cc7ca286c1378e2e30af1ccb43e8e5d58cce4b2e9ed13f59d655b81`.
  Measurement base is the commit above plus the uncommitted task changes; later
  formatting/help-only edits do not change extraction behavior.
- Container smoke: 20,000 rows, 4.67 seconds including container startup, output
  SHA-256 identical to native. `linux/amd64`, UID 10001, network none, read-only root,
  two CPUs, 6 GiB memory, 256 PIDs, `/tmp` 128 MB, `/output` 256 MB. Image size:
  79,509,337 bytes (about 75.8 MiB); image ID
  `sha256:d05b1dbde4c823a5836f9ece7c288c88a5a72f15e58a6084b58fbcb33fed8915`.
- The root Dockerfile build stopped because this host lacks BuildKit support for its
  existing cache mounts. A generated temporary copy removed **only those build cache
  mounts**, then successfully built the same packages and runtime layers. Root
  Dockerfile remains unchanged. This validates parser runtime constraints, not the
  root build environment or the official competition checker.

Generated measurement manifests, outputs, binary and viewer are ignored. The earlier
manual review and improvement plan are preserved. No organizer data, checker, Cargo
lockfile or dependency was changed. No official checker success is claimed.

## Remaining work

Shorthand/plan disambiguation, broader predicate and relation parsing, robust document
boundaries and independent semantic evaluation remain. A learned non-LLM candidate
ranker or sequence tagger is an optional next experiment, not an installed dependency.
Do not interpret `paired`/`split` or inherited context as a truth judgment. The solver,
count arithmetic, typed-value interpretation and 1,000-claim generator are still absent.
