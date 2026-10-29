# Assertion text pipeline

- Task: `assertion-pipeline`, 2026-10-28; status: delivered baseline.
- Human owner: unassigned. Implementation: Codex, no delegated agents.
- Branch: `feat/assertion-pipeline`; checkout: `/tmp/veridyct-assertion-pipeline`.
- Base: `e79e83c`.
- Scope: `crates/core`, `crates/cli`, their Cargo dependencies, this lab, and
  architecture/development/index/handoff documentation.
- Acceptance: reusable structured records; independently runnable lexicon,
  normalization, split, and combined commands; practice CSV output; source fidelity;
  explicit ambiguity; tests and measured diagnostic coverage.

The user narrowed the earlier extraction proposal: keep assertion wording rather
than interpret typed values. Subject, attribute, assertion text and provenance are
fields on Rust objects, serialized into separate CSV columns. No display string is
parsed to recover these fields. Labels and practice forms are excluded from the
extraction API. Parent labels can be retained by the CSV adapter.

Use declared lexicon surfaces, with optional explicitly reviewed additional aliases.
Do not infer aliases by removing name prefixes. Resolve overlapping names by longest
span, retain alias collisions, and suppress ambiguous ordinary-word aliases.
Rules are deterministic and local to one row; no cross-row subject inference.
Keep successful splits alongside unresolved fragments. A row can be partial even
when some canonical pairs are available. Scope that cannot be distributed safely
stays unresolved. No typed-value parsing, truth verdicts or claim generation.

Practice forms are used only by a separate diagnostic report. That report measures
subject/attribute occurrence agreement, not assertion-text correctness or unseen
generalization. Curated synthetic tests are development-authored with Codex and
are parser fixtures, never evidence about the Hooly universe.

See [usage](README.md), [handoff](../../docs/handoffs/assertion-pipeline.md), and
[architecture](../../docs/architecture.md).


## Contextual extraction update — 28 October 2026

The [improvement plan](IMPROVEMENT-PLAN-2026-10-28.md) supersedes the baseline's row-local
restriction. The shared Rust core now provides a bounded, ordered `DocumentExtractor`
with explicit antecedent provenance, role/predicate attachment, version assertions,
qualifier wording and unresolved list groups. Schema v2 requires recompiled indexes
and normalized files. CLI context is on by default and can be disabled for comparison.
Common-word aliases can resolve through supported product predicates; counted nouns
are not entity ambiguities. No undeclared aliases or learned world facts are added.

Use deterministic grammar first. A trained non-LLM ranker/tagger remains optional;
this change installs no ML runtime and claims no training or full English understanding.
See [results](V2-RESULTS-2026-10-28.md) and the
[v2 handoff](../../docs/handoffs/contextual-extraction.md).
