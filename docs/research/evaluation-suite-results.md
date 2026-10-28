# Our solution on the evaluation suite (2026-10-28)

Measured the evening of 2026-10-28 on the teammate's synthetic evaluation suite (evaluation-data v3, factory 1.1.0,
89,897 rows; Mihai owns human review; generator code on `feat/evaluation-data`, not yet on main). Scripts, result logs
and per-worker reports: [labs/evaluation-suite-runs](../../labs/evaluation-suite-runs/README.md).

## Verdict

- **The suite is solved.** With gold forms the timeline engine scores 1.0000 on every main world. Our extractor trained
  only on the official practice file reaches 99.62% (calibration) and 99.45% (sealed) target label accuracy on worlds
  it never saw, against 83.35% always-true. An extractor that learns the suite's own training material reaches 1.0000.
- **The suite is easier than the competition in two measured ways.** Every known interval has a visible anchor that
  states its validity interval ("From 1 October 2025 through 31 January 2026, Pixel 10 comes with 130 GB of storage."),
  so truth is a lookup. Treating anchors as point statements on a random day of their interval, as practice rows are,
  drops gold-form accuracy to 0.72 to 0.76. And the prose is a finite template generator: C learned all of it.
- **The real-prose number is the one that matters for the competition.** Worker D measures B's extractor on the real
  practice file under page-grouped cross-validation and feeds it to V9; see "Real practice" below.

## Results on hidden targets (18,103 per main world)

| Pipeline | dev | cal | sealed | Notes |
|---|---:|---:|---:|---|
| Always true | 0.8335 | 0.8335 | 0.8335 | macro-F1 0.3031; our scorer reproduces the suite's numbers exactly |
| V9 on gold forms, trained on the world's anchors | 0.8410 | 0.8391 | 0.8385 | false recall 0.03 to 0.05; anchors sit on change points |
| Gold forms, point engine, jittered anchors | 0.7395 | 0.7246 | 0.7571 | competition-like evidence: stale previous values |
| Gold forms, point engine | 0.9795 | 0.9795 | 0.9795 | never unsure; anchors dated exactly at interval starts |
| **B: practice-trained extractor + interval engine** | 0.9982 | **0.9962** | **0.9945** | cal and sealed never inspected before the final run |
| C: suite-trained extractor + interval engine | 1.0000 | 1.0000 | 1.0000 | in distribution; 1 sealed row mis-extracted, label still right |
| Gold forms + interval engine (ceiling) | 1.0000 | 1.0000 | 1.0000 | also exact under alias, unit, version-format perturbations |

B in detail: macro-F1 0.9905 / 0.9830 / 0.9914, arena points per row 0.9972 / 0.9941 / 0.9891 (dev / cal / sealed).
Row-exact forms 99.83 / 99.81 / 99.44%; the Rust parser's pair recall on cal and sealed is 56.66% and 61.76%.
Diag 0.9985, synth 0.9946, the external worlds 1.0000. Pilot and prac stop at 0.39 for every pipeline, gold included:
those small worlds deliberately hide evidence (`oracle_only`).

Cost: B extracts a 20,000-row world in 7.6 s on one Apple M5 Pro core (1.0 s of it training on practice), C in 6 s
plus 39 s of training, and the engine adds 0.15 s. Everything fits the 30-minute box with a wide margin.

## What failed and why

- B's held-out errors (sealed, 112 rows): an entity used as a noun modifier ("Pixel 10 is on Android version 24.11."),
  two unseen value-first templates ("We're looking at V for S's A", "They gave V as the A for S"), "employs N
  employees" read as webcast viewers, a period after a one-letter capital blocking a clause split. Arity-3 rows are the
  weakest slice (97.24% row exact on sealed).
- V9 barely beats always-true here: it learns from labelled point anchors, and this suite's anchors sit on change
  points with only 127 to 146 single-fact false anchors per world.
- Bug found in V9: `decide()` at `labs/kb-experiments/v9.py:128` (same pattern at `v12.py:356`) writes `'unsure'` into
  a `<U5` numpy array, which stores `'unsur'`. All 22 published V9 runs chose band 0.0 and predicted no unsure, so
  their numbers stand; any run that abstains is scored wrong until the dtype is fixed. Worker D uses a fixed copy.

## Real practice (worker D)

Pending at the time of writing: B's extractor under page-grouped 5-fold cross-validation on `data/practice.csv` (every
practice-derived table restricted to the training folds), error classes, and V9 end to end with extracted forms
against gold forms under the R80 and R10 regimes. Results land in `labs/evaluation-suite-runs/D/` and
`results/D.jsonl`; the previous best on real practice was 0.807 to 0.834 exact form on single-fact rows.

## Caveats

- The suite is a controlled emulator, not a reconstruction of the organizer world (GUIDE.md). Its three main worlds share
  the lexicon, attribute phrases, value spelling and interval grammar, so held-out here means new values and template
  families, not new prose.
- The suite's own scorer (`bench.py`) was not available; `A/score.py` re-implements it and matches its published
  always-true baseline to four decimals.
- Confidence is uncalibrated for B (raw sigmoid); C is underconfident on held-out wording (ECE 0.06 to 0.07).
