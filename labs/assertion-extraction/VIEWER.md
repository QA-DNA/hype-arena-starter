# Assertion review viewer

- Task: `assertion-viewer`, 2026-10-28.
- Human owner: unassigned. Implementation: Codex; no delegated agents.
- Branch/checkout: `feat/assertion-viewer`, `/tmp/veridyct-assertion-viewer`.
- Base: `e79e83c` plus the existing uncommitted assertion-pipeline working state.
- Scope: local lab viewer, build/server scripts, tests and lab documentation only.
- Acceptance: inspect original/normalized text and separate extraction columns;
  compare practice annotations; search/filter/navigate; no parser changes or network
  dependencies; usable on desktop and mobile.

## Run

Node.js 22+; no npm packages or install step. From the repository root:

```sh
node labs/assertion-extraction/serve-viewer.mjs
```

Open `http://127.0.0.1:8791`. The server binds only to loopback. Set `LAB_PORT` to use
another port. It builds a snapshot on startup. Restart after regenerating the parser's
CSV output. If output is missing or inconsistent with the practice source, the build
fails with an actionable error rather than showing unrelated annotations.

For a portable HTML file with all data and assets embedded:

```sh
node labs/assertion-extraction/build-viewer.mjs
```

Open `artifacts/assertion-extraction-viewer/index.html` directly. This also works
offline without a server. Generated HTML and browser screenshots are ignored by Git.

## Review a row

Search by ID, text, subject or attribute. Filter by extraction status or pair agreement
with practice annotations. Select a row, use Previous/Next, or try the example buttons.
The row list is paginated; the inspector preserves input order.

1. Compare original and normalized text.
2. Read parser output as separate subject, attribute and assertion-text columns.
3. Click assertion text to highlight its source and subject. Original offsets are
   UTF-8 bytes; the viewer converts them without corrupting Unicode. The explanation
   says why an unresolved fragment failed. Rule/offset details are optional.
4. Compare with the separate practice annotation table. Its values come from `form`;
   they are not parser output. Pair matching uses multisets and preserves duplicates.

“Pair matches” checks only the canonical subject/attribute occurrence, not wording,
value correctness or truth. An extra pair can be an extraction error or an annotation
scope difference. “Fully paired” is the parser's `split` status, not verified success.
The source truth label belongs to the entire row. Nothing is written back to the CSV,
and no training or extraction code runs in the browser.

The viewer reads `data/practice.csv` and the generated
`labs/assertion-extraction/outputs/practice.assertions.csv`. Source hashes and build
time appear at the bottom of the page. Text is rendered with DOM text nodes; embedded
JSON escapes script delimiters. There are no external fonts, libraries or requests.

## Checks

```sh
node --test labs/assertion-extraction/tests/viewer.test.mjs
node labs/assertion-extraction/tests/viewer-browser.mjs /usr/bin/brave
```

The data test requires the delivered practice output. Its snapshot counts intentionally
change only after reviewing regenerated parser results. The browser check accepts an
installed Chromium-family executable, uses an isolated temporary profile, exercises
desktop/mobile layouts, and writes screenshots under `artifacts/assertion-extraction-viewer/`.

See [pipeline usage](README.md) and [viewer model](viewer-model.mjs).

Verification: all 4 model/data tests passed, including full-practice counts, duplicate
pair matching, stale-source rejection and UTF-8 highlights. Headless Brave passed
19 browser checks each at 1440 px and 390 px (38 total), covering selection, source
highlights, reference gaps, search, filters, pagination, examples and viewport overflow.
Desktop/mobile screenshots were inspected. `cargo xtask docs` and `git diff --check`
passed. Rust sources and parser output were unchanged, so Rust tests were not rerun.

Delivery: viewer source files and generated HTML were copied back into the original
working directory after isolated testing, preserving the existing pipeline changes.
The initial viewer delivery did not include a commit, push, deployment or dataset
modification.
