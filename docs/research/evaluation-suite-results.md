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
- **It does not transfer to the real practice prose.** The same practice-trained extractor gets 0.610 row-exact forms on
  the official practice file under page-grouped cross-validation (0.736 on single-fact rows, below our previous best
  0.807), and V9 fed with those forms scores fewer arena points than always-true at both label ratios. The suite tests
  rows that name their subject; 34% of real rows do not, and real multi-fact rows come out as one fact per clause.

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

B's extractor (v1) on the official `data/practice.csv`, page-grouped 5-fold cross-validation, every practice-derived
table (TF-IDF scorer, attribute kinds, unit sets) built from the training folds only. The w7 grammar and B's hand rules
were tuned with practice or the synthetic dev world visible, so cross-validation isolates only the learned parts.

| Slice | Rows | Pair P / R / F1 | Value F1 | Row exact |
|---|---:|---|---:|---:|
| All rows, CV | 1,897 | 0.802 / 0.657 / 0.722 | 0.705 | **0.610** |
| All rows, trained on all (upper bound) | 1,897 | 0.832 / 0.684 / 0.751 | 0.734 | 0.642 |
| Single-fact, subject named in the row | 923 | 0.933 / 0.944 / 0.938 | 0.923 | 0.914 |
| Single-fact, subject not named | 544 | 0.476 / 0.441 / 0.458 | 0.450 | 0.432 |
| Multi-fact, all subjects named | 323 | 0.955 / 0.576 / 0.719 | 0.689 | 0.245 |
| Multi-fact, a subject not named | 107 | 0.581 / 0.265 / 0.364 | 0.352 | 0.000 |

Single-fact exact: previous best (w7 + w11 resolver + classifier) 0.807 under CV; B v1 0.742; a post-hoc page-context
tweak (subject from any earlier row of the page, then later rows) 0.815.

Error classes (739 non-exact rows): 387 (52%) need the page (subject never named on the page, named on an earlier or
later row, multi-fact rows with an unnamed subject); 236 are multi-fact rows reduced to one fact although every subject
is named; the rest are small generic classes (wrong attribute of the same kind, a yes/no attribute beating a value,
yes/no facts from asides, "after 10 min" read as "more than").

V9 end to end under the R80 and R10 regimes of `labs/kb-experiments/exp.py` (points: +1 right, -1 wrong, 0 unsure):

| Forms | R80 accuracy | R80 false recall / precision | R80 points per row | R10 accuracy | R10 points per row |
|---|---:|---|---:|---:|---:|
| Always true | 0.833 | 0 / - | 0.667 | 0.831 | 0.662 |
| Gold, published `decide()` | 0.902 | 0.675 / 0.763 | 0.805 | 0.816 | 0.631 |
| Gold, unsure dtype fixed | 0.867 | 0.675 / 0.763 | 0.777 | 0.817 | 0.639 |
| **Extracted (CV), fixed** | **0.819** | 0.343 / 0.476 | **0.646** | **0.798** | **0.596** |
| Extracted, trained on all rows | 0.832 | 0.344 / 0.536 | 0.676 | 0.801 | 0.620 |
| Gold on labelled pages, extracted on hidden pages | 0.772 | 0.644 / 0.488 | 0.611 | 0.763 | 0.525 |

- Extracted forms put V9 below always-true at both ratios. Errors also hurt rows whose own form is right, because they
  spoil the evidence from other rows; false recall halves (0.675 to 0.343).
- Even with gold forms, V9 at R10 scores fewer points than always-true.
- Mixing clean gold forms with extracted ones is worst: the model reads extraction errors as contradictions.
- The unsure fix costs points as tuned: the macro-F1 threshold sends 79 rows to unsure and none of them is gold unsure.

Measured fixes (post-hoc, chosen after seeing these results):

| Change | R80 points per row | R10 points per row |
|---|---:|---|
| Extracted, baseline | 0.646 | 0.596 |
| Choose V9's threshold by arena points instead of macro-F1 (one line) | 0.680 | 0.661 |
| Plus page-context subject tweak | 0.693 | 0.660 |
| Gold forms for all subject errors (387 rows) | 0.740 | |
| Gold forms everywhere, points threshold | 0.809 | 0.674 |

The biggest single gain on offer is subject resolution with page context: the previous best resolver (w11, 0.909
subject accuracy on single-fact rows) plugged into the extractor, then the points-based threshold.

## Caveats

- The suite is a controlled emulator, not a reconstruction of the organizer world (GUIDE.md). Its three main worlds share
  the lexicon, attribute phrases, value spelling and interval grammar, so held-out here means new values and template
  families, not new prose.
- The suite's own scorer (`bench.py`) was not available; `A/score.py` re-implements it and matches its published
  always-true baseline to four decimals.
- Confidence is uncalibrated for B (raw sigmoid); C is underconfident on held-out wording (ECE 0.06 to 0.07).
