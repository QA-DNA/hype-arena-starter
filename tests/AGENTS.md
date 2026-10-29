# QA and evaluation scope

Read [root instructions](../AGENTS.md). Current tests live beside Rust modules and in
crates/cli/tests. This directory reserves the cross-component evaluation scope.

- Preserve organizer examples and scripts. Add independent tests and wrappers separately.
- The official checker verifies structural output but does not fully validate semantic
  truth, claim grammar, schemas, or lexicon references. Test these layers explicitly.
- A clean holdout excludes its labels, forms, duplicates that reveal answers, and derived
  knowledge from all training/evidence artifacts used by that evaluation configuration.
- Separate permitted use of practice data in the final image from honest generalization
  estimates. Record the split, seed, input fingerprint, configuration, and source commit.
- Report per-class errors and confidence calibration, not just an aggregate success number.
- Include temporal boundaries, compound claims, aliases, unit conversions, malformed input,
  CSV quoting, unknown evidence, generation uniqueness, and exact output counts as relevant.
- Verify generated text, structured forms, and provenance together. Schema validity alone
  does not prove a generated claim true.
- Exercise offline CPU container limits, termination, atomic output, and maximum output size
  once the required behavior exists. Do not invent passing results for planned components.
- Maintain a small fast suite; run expensive integration or performance checks when relevant.
  Do not fail unrelated work on noisy microbenchmark timing from shared runners.
