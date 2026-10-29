# Independent generated-claim review

Task: live-mvp-contract-review. Agent owner: contract_review; human owner unassigned.
Base: d1617ba. Scope: core claim generation and independent checks.

The review removed `training_data_cutoff` from the immutable historical-date allowlist:
a model's cutoff can change, so an earlier observation cannot license a current fact.
It aligned claim newness with the organizer's whitespace, case and trailing punctuation
normalization, includes all prediction texts and IDs in exclusion/reservation, and keeps
boolean attributes outside the two change-value sides to avoid `end_to_end` introducing
another `to` inside a value side. The resulting boolean sentence still contains the full
attribute and states polarity separately on each side, as the value grammar requires.

Validation: Docker Rust 1.90 core suite: 13 tests passed, including three regressions for
these changes. Independent generator harness: 1,000 distinct claims from 1,315 candidates
(674 compare, 233 change, 40 fact, 37 at_event, 16 relation); no unsupported padding.
Published grammar was reviewed against samples, including duration symbols, relation
subject/link wording, boolean polarity, and date comparisons. Private referee truth
checks are unavailable; true historical observation and immutable-date assumptions
remain explicit. An output/schema pass does not guarantee hidden-universe truth.

Additional verification: [independent validator](../../tools/validate_claims.py) checked
all 1,000 generated claims against the organizer JSON schemas, lexicon names/attributes,
normalized newness, 1,960 source references, ordered change evidence, comparison direction,
contemporaneous relation links and event-day matches, plus selected public grammar
conditions. The validator needs Python jsonschema/referencing and takes a report JSON
(or API job snapshot); it does not implement the private referee. Core Clippy with
warnings denied passed after the review changes.
