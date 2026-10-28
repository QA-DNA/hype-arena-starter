# LAB-001: exploratory practice and lexicon browser

- Status: accepted within the user's request, 2026-10-28.
- Task owner: Codex, primary implementation agent. Human owner: unassigned.
- Branch: `teodorbalan/practice-lexicon-lab`.
- Implementation checkout: `C:/Users/Teodor/orca/workspaces/QA-DNA-JEV/practice-lexicon-lab`.
- Base: `7c32449d878efde84aa1f38ce179778d1e2c4a48`.
- Authorized scope: a separate lab/tests folder and local HTML web app exploring practice
  queries, lexicon graphs, chronology and explainable correlations.
- Paths: `labs/practice-lexicon/`; generated output in `artifacts/practice-lexicon-lab/`;
  documentation index link when integrated into the parent workspace.

Use dependency-free JavaScript for browser exploration and Node's built-in test runner
and build script. The build validates both inputs and emits one self-contained HTML.
This keeps the lab easy to open locally without modifying the Rust runtime or adding
Node to its dependency graph. The standalone Rust CPU competition boundary is unchanged.

Model helpers have no DOM or HTTP dependency. Browser state uses canonical subjects;
original `form` values remain available and are preserved on export. Relation edges
are keyed by subject, attribute, target and source row label, with explicit row IDs.
Only `name` values resolved into lexicon subjects are graph targets. Schema attributes
are separate from observed relations. Statistics and histories do not infer truth.

Acceptance criteria:

1. Load all 1,897 practice rows and 62 lexicon subjects without modifying source files.
2. Make all queries reachable in chronological order with date/ID/text/label/form.
3. Show subject/alias/attribute structure and navigable, source-backed name relations.
4. Explain correlations using the same subject and attribute; retain row-level labels.
5. Support filters, monthly selection, empty states, responsive layout and CSV export.
6. Produce an offline HTML and runnable lab tests, with documented limitations.

No network retrieval, generated training data, solver implementation, inference API,
claim submission, external publishing or deployment is included. This decision supersedes
the foundation's deferred data work only for this explicitly requested development lab.

## Explorer refinement (user-requested follow-up)

Scope: graph presentation and navigation in `graph.js`, `app.js`, HTML/CSS and browser
checks. Same owner and implementation branch; no data/model/competition interfaces change.

Use one graph DOM tree moved into a modal for fullscreen. Request native fullscreen on
the document when a trusted activation permits it; preserve the viewport modal as fallback.
Native dialog focus handling, Escape and restoration keep keyboard navigation contained.
Evidence and individual query forms are inspectable inside the graph. Only an explicit
timeline action leaves the explorer. Layouts are cached; camera transforms are batched to
animation frames, without rebuilding graph nodes during gestures. Pointer coordinates use
the SVG screen transform, with wheel zoom anchored at the cursor and two-pointer pinch.

Acceptance: fill the viewport, readable labels, search/aliases, back navigation, camera
preservation on global selection, pan/zoom/fit, source inspection, Escape/focus restoration,
and desktop/mobile browser validation. No throughput or latency benchmark is claimed.
