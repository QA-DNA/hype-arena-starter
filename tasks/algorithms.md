# Candidate algorithms for the labelling task (Task 1)

All five share the same front end: parse each row into facts `(subject, attribute, value, date)` (plan T4-T6).
They differ in **how a parsed fact is judged** and how confident we are. Claim writing (Task 2) uses the
same timeline for every option and is not part of this comparison.

## Evidence we measured (practice.csv, 1,858 non-unsure rows)

Judging with the **gold** `form` (so parsing is perfect), leave-one-row-out, using only the other practice rows
as truth (practice is ~10% of the real input, so the real timeline will be denser):

| Method | Accuracy |
|---|---|
| Prior (everything true) | 85.1% (83.3% counting the 39 unsure rows) |
| Nearest-in-time true value, exact match | 78.8% (worse than prior) |
| Latest-before-date step function | 73.4% (worse) |
| **Bracketing** (value before and after the row's date, compat. match) | **~90%** |

Why exact lookup fails: values appear at different precision (`2026-01` vs `2026-01-12`), as inequalities
(`over 100` with `op: gt`), as aliases (`Nimbus` vs `Nimbus Cloud`), and truth changes between sparse observations.

Bracketing buckets (before/after = nearest true observation of the same fact on an earlier/later date):

| Evidence | Rows | True | False | Verdict |
|---|---|---|---|---|
| value matches both sides | 398 | 396 | 2 | true, ~99.5% |
| before = after, claim differs | 76 | 2 | 74 | **false, ~97%** |
| true observation on same date matches | 134 | 133 | 1 | true, ~99% |
| true observation on same date differs | 27 | 4 | 23 | false, ~85% |
| matches exactly one side | 357 | 317 | 40 | true, ~89% |
| only one side known, matches | 441 | 441 | 0 | true, 100% |
| no observation of the fact | 83 | 82 | 1 | true (prior) |
| only one side known, differs | 288 | 174 | 114 | **uncertain** |
| both sides known, differ from each other and the claim | 54 | 32 | 22 | **uncertain** |

Also: of the facts stated in false rows, 202 equal a value that was true on another date (stale) and 158 were never
true (invented). 75 of 514 facts appear only once; 342 appear 3+ times.

The two uncertain buckets (342 rows, 18%) are where the algorithms below compete.

## The five candidates

### A. Bracketing evidence + gradient-boosted calibrated classifier
Per fact, build a timeline of true observations; for each row compute features: match on same date / before / after,
distance in days to each side, whether before = after, number of corroborating rows, value-kind, precision/op
compatibility, parse confidence. Train a small GBM (or logistic regression) on practice labels, isotonic-calibrate.
- Strength: directly encodes the measured ~90%; fast; explainable.
- Weakness: uses only labelled rows as truth; the uncertain buckets need change-point timing.
- Cost: low (about 1 day-part). Libraries: scikit-learn.

### B. Truth discovery over all rows (per-fact change-point model + source reliability, EM)
Treat the true value of each (subject, attribute) as a piecewise-constant hidden timeline. Every row, labelled or not,
is a noisy observation (labelled rows are near-certain, unlabelled ones weighted by a learned reliability per page
type / source). Fit with EM or a small HMM/segmentation per fact; judge a row by the posterior that its value holds at its date.
Related ideas: TruthFinder, Dawid-Skene, Bayesian change-point detection.
- Strength: uses the ~18k unlabelled rows to fill gaps and to date change points (attacks the uncertain buckets); gives a principled probability.
- Weakness: most complex; noisy sources with correlated errors (many pages repeating the same stale value) can fool it.
- Cost: medium-high.

### C. Temporal-consistency rules and constraints
Hand-written checks that need no timeline: "today / starts today / ships today" must match the page date; "last quarter" figures
vs quarter results events; monotone attributes (versions, cumulative counts, device counts) cannot go back; an event's date vs
dates mentioned in its rows; precision-aware dates; `compare` relations among facts; relation links (CTO joined date).
Rules emit hard verdicts or features for A/B.
- Strength: catches false rows even when the fact has no timeline (the 83 "none" rows and one-sided cases); cheap and auditable; there are visible examples (`Android 17 beta starts today, 3 September 2025` on a 2026 page).
- Weakness: manual work; covers specific patterns only.
- Cost: low per rule; do the top few.

### D. Near-duplicate retrieval and label propagation
Universe pages restate the same facts across docs, posts, decks and press releases. Normalise numbers/entities and find the nearest labelled
rows by text (BM25 / TF-IDF cosine) within a date window; copy the label discounted by similarity and time gap. Needs no parser.
- Strength: parse-independent safety net; handles rows the parser cannot read.
- Weakness: a near-duplicate with a changed number is exactly a false row, so numbers must be compared, not ignored; weak for new facts.
- Cost: low.

### E. Supervised text-cue model (TF-IDF / char n-grams + logistic regression or NB) as a stacking input
Learn lexical cues of hype and staleness ("still", "now", "already", "remains", "ships today", superlatives) plus subject/attribute priors.
Alone it should sit near the 83% prior, so it is useful only as a feature or tie-breaker.
- Strength: trivial; independent signal for the uncertain buckets.
- Weakness: unmeasured here (scikit-learn is not installed locally); expected to be weak alone.
- Cost: very low.

## Comparison

| | Uses unlabelled rows | Needs parser | Attacks uncertain buckets | Complexity | Expected role |
|---|---|---|---|---|---|
| A bracketing + GBM | no | yes | partly | low | **core** |
| B truth discovery | yes | yes | yes | high | upgrade of A's timeline |
| C rules | no | partly | partly | low | feature/override layer |
| D retrieval | yes | no | partly | low | fallback |
| E text cues | no | no | weakly | very low | stacking feature |

## Recommendation

1. Build **A** first: it is the measured ~90% and a submittable result.
2. Add **C** for the cheapest wins, then **B** to replace A's timeline if the benchmark shows gain; **D** and **E** as stacked features and fallbacks.
3. Do not pick on opinion: run the benchmark below. A final stacked model (A+B+C+D+E features -> calibrated GBM) is the likely winner.

## Benchmark protocol (to pick the winner)

- Same inputs for all: gold `form` for practice rows (isolates the judging layer from the parser), grouped-by-date 5-fold, truth only from training folds.
- Metrics: accuracy, log-loss, calibration table, coverage of true/false/unsure, and a confidence-weighted score (the real formula is unpublished, so also report accuracy among high-confidence rows).
- Second pass: replace gold forms with the real parser's output and report the drop; a method that collapses here is not viable.
- Pick the best by log-loss on the second pass; break ties by simplicity.

## Caveats

- The ~90% is an oracle-parse, practice-only figure. Real accuracy depends on the parser and on how dense the full universe's timeline is.
- B, C, D and E are not measured yet.
- The unlabelled input is unknown until the run; the practice split might not mimic it. The sample (20 rows, 29 Oct 09:00) is only a smoke test.
