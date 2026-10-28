# Presentation, accuracy and reviewed demo UI

Task: presentation-design; agent: presentation_web; human owner unassigned.
Branch: teodorbalan/presentation-design. Base: df5556a.
Owned paths: apps/web/index.html, apps/web/styles.css, apps/web/app.js and this handoff.

The workbench now exposes a prominent measured-accuracy callout and a fourth
Accuracy test view. It calls POST/GET /api/evaluation, displays the actual report's
accuracy, class metrics, confusion matrix, majority baseline, coverage, runtime,
and paginated per-row comparisons. Users can filter incorrect, correct or unsure
predictions and inspect each row's model scores, assertions, reason and evidence.
No accuracy number is hardcoded. Completely unlabelled input is explicitly marked
as having unknown accuracy without reference labels.

The Architecture view includes two full-resolution PNG figures served locally at
/assets/stack.png and /assets/pipeline.png, each with accessible explanations,
fullsize links and downloads. The original layer diagram remains available in a
collapsible view. Typography and spacing are more readable across the workbench.
The integrator owns the generated PNG assets and their API routes.

A download and Load reviewed demo action use /api/demo-comparison and
/downloads/demo-unlabelled.csv. Runtime labels remain blank. After prediction, the
engine's labels are compared with separate development-time LLM review references.
Agreement is labelled separately from measured ground-truth accuracy, with review
reasons and source IDs inspectable. Review labels are never sent to /api/runs.
Refresh recognizes a completed reviewed demo by matching all IDs and source texts.

Verification before initial integration: node --check apps/web/app.js passes;
static HTML parsing confirms unique IDs and all literal JS DOM references resolve.
Real API/browser verification will follow once the integrator serves updated
endpoints and PNG assets. No runtime or model code was changed.
