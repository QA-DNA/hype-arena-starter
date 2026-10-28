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

## Verified against the live integrated server

Real Chrome/CDP at http://127.0.0.1:8787 passed on 2026-10-28:

- All four tabs load with no JavaScript exceptions.
- Hidden-label test runs the actual API and reports 80.3% accuracy, 305 correct of
  380, nine confusion matrix cells and three class metric rows. The headline uses
  the same measured report. The view explicitly shows its score below the 85.3%
  majority baseline. Filtering wrong predictions contains only incorrect rows.
- Reviewed demo loads 20 rows with all runtime labels empty; actual Run completes
  and shows 70% agreement (14/20) with separate LLM references. Per-row model and
  reference labels, review reasons, sources and model evidence are inspectable.
- All three CSV downloads return 20 data rows. Unlabelled CSV has exactly id,text,
  date,label with every label empty. Dynamic comparison includes real model labels,
  LLM references, agreement and all three score columns.
- Both PNGs load at natural size: stack 1536x1024; pipeline 1774x887. Both have alt
  descriptions, full-resolution links and download links. Screenshots were visually
  inspected; the diagrams and evaluation cards render cleanly.
- Desktop 1440 px and mobile 390 px have no horizontal page overflow across
  workbench, accuracy and architecture views.

Ignored QA artifacts under this isolated checkout's artifacts/presentation-qa/
include evaluation, error inspector, model/reference comparison, architecture,
mobile PNG screenshots and result.json. The API was left with a completed reviewed
20-row run and a completed measured evaluation so the presentation can show both.
