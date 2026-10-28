# Live workbench browser delivery

Task: live-mvp / web. Agent: web; human owner unassigned. Base: e79e83c with shared interface 2d38ccd. Paths: apps/web/index.html, styles.css, app.js.

The local browser presents a real run button, CSV upload, completed-stage progress, an incremental activity feed, paginated known and unknown rows, model score bars, structured subject/attribute/value inspection, dated source evidence, MMR claims, and official CSV download. A compact functional pipeline stays visible with the live run. A dedicated architecture view shows the browser, Axum adapter, competition CLI, shared Rust core, processing stages, stack and runtime envelope.

The stack remains local HTML/CSS/JavaScript with system fonts and no added browser dependencies. All uploaded and API-provided content is inserted with textContent. The API owns parsing, inference, generation and validation. The browser does not classify rows. The page labels scores as model estimates and the familiar practice demo as an upper-bound demonstration rather than independent evaluation.

API agreement: [live MVP interfaces](live-mvp.md). Source preview uses GET /api/dataset; submission uses POST /api/runs; ongoing jobs poll GET /api/runs/current only while active; completed CSV uses GET /api/runs/current/output.csv. Poll errors are visible and retried. File input is bounded to 16 MiB before submission; server validation remains authoritative.

Validation: node --check apps/web/app.js passed. Headless Chrome against the real API at 127.0.0.1:8787 passed the complete practice run: 100% progress, five actual processing log events, 1,000 generated claims, source fact and evidence inspection, claim JSON inspection, and a 270,144-byte CSV download. Screenshots were inspected at 1440 pixels; workbench, claims and architecture views had no horizontal overflow at 390 pixels. No JavaScript exceptions occurred.

A second browser run uploaded a real three-row CSV through the file input, preserved a known false label, classified the unknown rows, rendered a hostile HTML string as literal text with no injected image or script execution, and downloaded output. Malformed CSV was rejected with HTTP 422. Ignored QA artifacts are in artifacts/web-live-qa and artifacts/web-upload-qa in the isolated checkout. No claim is made here that organizer semantic judging or confidence calibration passed.

Follow-up display corrections: money uses the contract's per billing period, and score percentages retain one decimal when needed so small nonzero probabilities remain visible. Successful polling clears transient connectivity errors.
