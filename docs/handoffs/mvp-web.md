# Live workbench browser delivery

Task: live-mvp / web. Agent: web; human owner unassigned. Base: e79e83c with shared interface 2d38ccd. Paths: apps/web/index.html, styles.css, app.js.

The local browser presents a real run button, CSV upload, completed-stage progress, an incremental activity feed, paginated known and unknown rows, model score bars, structured subject/attribute/value inspection, dated source evidence, MMR claims, and official CSV download. A compact functional pipeline stays visible with the live run. A dedicated architecture view shows the browser, Axum adapter, competition CLI, shared Rust core, processing stages, stack and runtime envelope.

The stack remains local HTML/CSS/JavaScript with system fonts and no added browser dependencies. All uploaded and API-provided content is inserted with textContent. The API owns parsing, inference, generation and validation. The browser does not classify rows. The page labels scores as model estimates and the familiar practice demo as an upper-bound demonstration rather than independent evaluation.

API agreement: [live MVP interfaces](live-mvp.md). Source preview uses GET /api/dataset; submission uses POST /api/runs; ongoing jobs poll GET /api/runs/current only while active; completed CSV uses GET /api/runs/current/output.csv. Poll errors are visible and retried. File input is bounded to 16 MiB before submission; server validation remains authoritative.

Validation: node --check apps/web/app.js passed. Real API/browser validation is performed by the integrator after combining the Rust engine and frontend. No claim is made here that organizer semantic judging or confidence calibration passed.
