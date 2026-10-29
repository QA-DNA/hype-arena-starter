# Presentation, hidden-label accuracy and reviewed CSV

Task: presentation-evaluation; authorized by Teodor on 2026-10-28. Human owner
unassigned. Base df5556a. Primary branch mvp/presentation-evaluation. Isolated agent
owners: evaluation_detail (core metrics), presentation_web (browser), llm_demo_review
(cited demonstration dataset). Root owns HTTP integration, PNG generation and checks.

The page now has an explicit Accuracy test tab, a measured headline, per-class metrics,
confusion matrix and every tested row beside its withheld reference. POST and GET
`/api/evaluation` run/read a fresh diagnostic using the same core. The test removes
all matching normalized test text from training, including duplicates, and passes no
labels or forms to prediction. One CPU job at a time is shared with ordinary runs;
the completed ordinary run and evaluation are retained separately.

Measured result: 305/380 correct, 80.26% accuracy, macro-F1 0.335, coverage 93.95%.
The majority baseline is 85.26%. This is the existing tuned diagnostic split, not an
independent final evaluation; shared facts and templates remain. The page shows the
baseline and errors rather than implying that aggregate accuracy proves quality.

GET `/api/demo-comparison` provides the blank-label CSV and separate development-time
LLM annotations. `/downloads/demo-unlabelled.csv` is the upload-ready file;
`/downloads/demo-reference.csv` is its cited reference review; after running the demo,
`/downloads/demo-comparison.csv` exports actual model labels, LLM labels, agreement,
three scores, explanations and source IDs. The references never enter the predictor.
The first observed comparison is 14/20 agreement, 70%; it is not certified truth or
independent generalization accuracy. Provenance is in [demo documentation](../../demos/README.md).

Two actual PNGs are bundled and served locally as `/assets/stack.png` and
`/assets/pipeline.png`, with full-resolution viewing, download, prose and accessible
alt descriptions. They were generated with built-in ImageGen; prompts and paths are
in [diagram provenance](../assets/diagram-prompts.md). No runtime generation service
or external font/CDN dependency was added.

The terminal guide [explain.ps1](../../tools/explain.ps1) explains the actual system in
Romanian, including examples, evidence boundaries, the model, MMR, CSV, evaluation,
Docker and reproducible commands. A visible Orca terminal was opened with the guide.

Verification: `cargo xtask check` and `cargo xtask test` passed; 23 tests total.
Chrome actual API flow passed at 1440 and 390 pixels, with no overflow or JavaScript
exceptions. Verified 380 report rows, 9 confusion cells, 3 class rows, error filtering,
20 demo rows, 14 reference matches, three correct CSV downloads and both PNG loads.
API checks additionally recomputed accuracy/agreement from exported rows and checked
blank runtime labels/forms. Ignored evidence is under `artifacts/presentation-final/`
and `artifacts/presentation-qa/`. Organizer files and classification behavior unchanged.
