# LAB-001: practice and lexicon exploration

- Status: implemented; local validation complete.
- Human owner: unassigned.
- Agent owner: Codex, primary agent; no delegated agents.
- Branch: `teodorbalan/practice-lexicon-lab`.
- Isolated checkout: `C:/Users/Teodor/orca/workspaces/QA-DNA-JEV/practice-lexicon-lab`.
- Base commit: `7c32449d878efde84aa1f38ce179778d1e2c4a48`.
- Delivery: new lab subtree copied into the user's parent workspace after implementation.
- Scope, interfaces and acceptance criteria: [LAB-001 decision](DECISION.md).

## Delivered behavior

[The lab](README.md) builds a standalone offline HTML from the organizer's two input files.
It displays 1,897 queries, 2,402 structured values, 62 subjects, 514 subject-attribute
pairs and 13 named events. All three source labels remain visible and are never predicted.

Relation/schema graph, node and edge selection, query inspection, chronology, filters,
monthly histogram, pair/value correlations and CSV export work without a frontend build
dependency. Browser JS and test code share [pure model helpers](core.mjs). No Rust
interface, competition dependency, API endpoint or checker behavior changed.

## Verification

- `node --test labs/practice-lexicon/tests/*.test.mjs`: 10 passed, including real-data
  validation, CSV round trip, chronology, aliases, filters and evidence provenance.
- `node labs/practice-lexicon/build.mjs`: emits a self-contained HTML; all source data
  are validated and SHA-256 fingerprints embedded.
- `node labs/practice-lexicon/tests/browser-smoke.mjs PAGE_ID`: 31 browser checks passed,
  covering all views, graph edge sources, attributes, pagination, sort directions,
  combined filters, invalid intervals, empty results, correlated rows and export contents.
- Desktop graph and layout visually reviewed in Orca's browser. Console had no messages
  at the inspected checkpoint.
- Standalone `file:///.../index.html`: all 31 browser checks also passed at a measured
  390 px viewport; stacked panels and no horizontal overflow confirmed and visually reviewed.
- In the integrated parent workspace, `cargo xtask check` passed (formatting, Clippy,
  71 documentation links, graph and upstream hashes); `cargo xtask test` passed all 6 tests.
  Executed in WSL Ubuntu-ASC after sourcing `/home/teodor/.cargo/env`; native Windows
  Cargo was not on PATH. No compiler installation was required.
- Original `data/`, `contracts/` and `scripts/` are not modified.

The official checker is not run: there is no competition solver or claim generator in
this task. This is data exploration, not an accuracy/generalization evaluation.

## Continue

### Fullscreen explorer refinement

User follow-up requested a more comfortable and efficient graph. Added a full-viewport
modal and native fullscreen, larger node labels, wheel/pointer/pinch navigation, search,
subject history, keyboard shortcuts and hideable source details. Query/source inspection
now stays inside the fullscreen graph. Camera movement batches one SVG transform per
animation frame and reuses graph nodes; layouts are cached. See [graph.js](graph.js).

Validation: 54 shared browser checks passed at 1440 and 390 px in local headless Chrome.
Trusted mouse dragging and two-finger pinch passed at both sizes; native fullscreen reported
the HTML element. Desktop/mobile captures were visually reviewed. The original 31 checks
also passed in Orca; its extended frame-awaiting run stalled when the embedded renderer
was not producing frames, so the completed verification used the independent Chrome runner.
The test tab was closed afterward. After integration, cargo xtask check passed (73 local links and upstream hashes) and cargo xtask test passed all 6 tests. Data-model tests and official input files are unchanged.

From repository root, run `node labs/practice-lexicon/serve.mjs`, then open
http://127.0.0.1:8790. Node 22+ is needed only for building, serving and tests. The generated
HTML can be copied and opened directly without Node or network access. Rebuild and reload
after edits. Generated HTML/screenshots remain under ignored `artifacts/`.

Read the interpretation limits in [README](README.md) before reusing the model. In
particular, page dates are not inferred effective dates, labels are row-level, structural
value differences are not contradictions, and unresolved name values do not become
lexicon nodes. No generated training data, external evidence or model knowledge is used.
