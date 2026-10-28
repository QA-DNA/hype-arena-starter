# MVP extraction and CPU forest

Task: live-mvp-engine. Agent owner: engine; human owner unassigned. Base e79e83c.
Paths: [engine](../../crates/core/src/engine.rs), [forest](../../crates/core/src/forest.rs).

The runtime uses a seeded 48-tree class-balanced bagged CART forest, depth at most
nine, with 80 lexical, template, entity and same-day evidence features. No LLM,
external inference, unsafe code or GPU dependency is used. The classes are true,
false and unsure; model probabilities are estimates, not calibrated confidence.

Mihai's commit 4478b99 is used directly: `normalise`, `compile_surface`,
`raw_matches`, `longest_matches` and `longest_predict` from
[the lexicon notebook](../../analysis/01_lexicon_analysis.ipynb) are ported to
Rust using NFKC, lowercase folding, variable whitespace, word boundaries and
longest non-overlapping spans with alias owners grouped by span. ASCII lexicon
names have exact case-fold equivalence; full Unicode case-fold tables are not
implemented (sharp-s and final-sigma folding are explicit). The supplied runtime
lexicon is authoritative; canonical indexes are rebuilt from it.

His [practice findings](../../analysis/practice/README.md) informed the rules:
compound false rows are never split into false facts; implicit subjects require
strong template similarity; repeated unknown rows are never trusted; source page
dates do not establish validity intervals. Known true input rows without forms
are extracted and included as observations. Evidence IDs, dates, labels, text and
typed assertions remain inspectable.

Exact practice text/date matches are explicitly identified as memorization.
Only unambiguous same-day true observations can provide decisive support or a
contradiction. Earlier observations are shown but do not prove interval continuity.
The fallback forest can still estimate a true/false label; reasons disclose this.
Unsupported extraction or low confidence causes abstention.

Public interface follows [the shared agreement](live-mvp.md). Additional methods:
`Engine::extract`, `Engine::tree_count`, and `evaluate_holdout`. Holdout removes
every fifth row and every matching normalized test text from training, clears
test labels/forms, and reports accuracy, macro-F1 and a confusion matrix. Shared
facts and templates remain, so this is diagnostic rather than independent proof.

Verification at initial handoff: isolated Docker Rust 1.90 harness compiled these
modules and passed four regression tests: seeded forest separation, changed-value
and nested-entity extraction, known-label preservation/no future evidence, and
false-row evidence exclusion. Integrated checks and release benchmark are next.
