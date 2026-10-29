# Detailed hidden-label evaluation

Task: presentation-evaluation. Agent owner: evaluation_detail; human owner unassigned.
Base: df5556a. Owned paths: core engine.rs and this handoff. The model is unchanged.

`engine::evaluate_holdout` now returns aggregate metrics and every hidden prediction
alongside the reference answer. It keeps its existing fields, adding majority label
and accuracy, prediction coverage, correct/incorrect/unsure counts, elapsed time,
per-class precision/recall/F1/support, and `results` entries with `expected`, `correct`
and the complete `prediction`. Confusion rows are reference labels and columns are
predictions in true/false/unsure order. Correct includes a correctly predicted unsure;
coverage separately counts only true/false predictions.

The majority constant is chosen using training labels only, with stable class-order
ties. Its accuracy is measured on the held-out references. Every fifth source row is
held out; all matching normalized text is removed from training/evidence. Test inputs
have empty labels and forms, so results never receive known-label treatment. Full
source references make leakage checks inspectable.

This remains the previously tuned diagnostic split. Shared facts/templates remain,
so it is not independent validation. It does not measure accuracy for unknown real
rows with no reference labels. Scores remain uncalibrated estimates.

Acceptance: metrics agree with displayed rows/confusion, supplied answers/forms are
excluded, and a unique secret fact plus training-position duplicate cannot reveal a
hidden answer.

Verification in Docker `veridyct:dev` / Rust 1.90: `cargo fmt --all`,
`cargo test --locked -p veridyct-core engine::tests` (six passed, ten unrelated tests
filtered), and `cargo clippy --locked -p veridyct-core --all-targets -- -D warnings`
all passed. The parent owns full workspace/API/browser integration checks. No model
weights, thresholds, training data or organizer files changed.
