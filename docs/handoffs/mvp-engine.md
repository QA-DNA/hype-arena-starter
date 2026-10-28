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
Unfamiliar text or low confidence causes abstention. A statistical label may lack
grounded extracted facts, which its explanation discloses. Balanced-bootstrap
posteriors are adjusted by observed class priors. Training features use
leave-self-out extraction rather than oracle forms, matching runtime behavior.

Public interface follows [the shared agreement](live-mvp.md). Additional methods:
`Engine::extract`, `Engine::tree_count`, and `evaluate_holdout`. Holdout removes
every fifth row and every matching normalized test text from training, clears
test labels/forms, and reports accuracy, macro-F1 and a confusion matrix. Shared
facts and templates remain, so this is diagnostic rather than independent proof.

Verification at initial handoff: isolated Docker Rust 1.90 harness compiled these
modules and passed four regression tests: seeded forest separation, changed-value
and nested-entity extraction, known-label preservation/no future evidence, and
false-row evidence exclusion. A fifth test covers Mihai's NFKC, whitespace,
nested-name and word-boundary matching. All five passed after the final change.

Reproduce diagnostics with `cargo run --release -p veridyct-core --example evaluate`.
Set `VERIDYCT_BENCH_COMMIT` to the current SHA and record container limits.
On Ryzen 9 6900HS, Linux container limited to 2 CPUs and 6 GiB, final release
training took 1.945 s and prediction of 20,000 runtime-shaped synthetic rows
took 2.412 s, total 4.356 s, peak process RSS 125,840 kB. It uses one compute
thread. The load includes 1,897 known rows and 18,103 modified practice sentences,
all without forms; it measures throughput, not novelty or prediction quality.

Diagnostic holdout after the adjustment: 1,513 training rows, 380 tests,
accuracy 0.8026, macro-F1 0.3346, non-abstaining coverage 357/380 (93.95%).
Confusion matrix, actual rows / predicted columns in true,false,unsure order:
`[[302,3,19],[42,3,4],[7,0,0]]`. Before the adjustment the overly conservative
gate achieved accuracy 0.0526, macro-F1 0.0689 and coverage 16/380 (4.21%).
The majority baseline accuracy is 0.8526, macro-F1 0.3068, so this remains a
weak statistical baseline, especially on false and unsure. The holdout was used
to diagnose this change and is not independent validation. Existing practice
memory accuracy must not be reported as generalization.
