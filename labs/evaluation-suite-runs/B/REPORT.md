# Worker B: practice-trained form extraction on the evaluation suite

Copied from worker B's final message (2026-10-28 evening); the harness blocked subagents from writing report files.

**Verdict.** Our current components transfer to this suite. The official practice file, the lexicon and the w7 value
grammar, combined with a TF-IDF + LinearSVC attribute scorer and about a dozen generic English rules, reach **99.81%
(cal) and 99.44% (sealed)** row-exact forms on the held-out worlds. Through worker A's interval engine that gives
**99.62% (cal) and 99.45% (sealed)** target label accuracy, against 100.00% with gold forms. The Rust parser reaches
56.66% (cal) and 61.76% (sealed) pair recall on the same worlds (PROSE-REVISION.md); B scores 99.85% and 99.55%.

## How it works (v1, the official run)

`extract.py --world <key>` reads only `public/universe.csv`, the lexicon and `data/practice.csv`.

1. Parse the interval prefix `From <date> through <date>,` in four spellings, with a half-open end.
2. Split clauses at sentence ends, `;`, `, and/but/while`, and ` and <subject|it>`.
3. Drop narrator asides: subject-less first-person clauses, and subject-less clauses beside real ones.
4. Candidate subjects: lexicon names and aliases, multi-word names without `Hooly`, singular pronouns resolved to
   earlier subjects in the row and then the previous row, priors by order of reference.
5. Score each (subject, attribute) pair jointly: practice-trained TF-IDF + LinearSVC (harness recipe, candidate mention
   masked), attribute-word overlap, and the attribute's value kind from practice (one kind per attribute, all 514 slots).
6. Typed value from w7 `values.py` (unmodified copy) for that kind.

No neural model: TF-IDF was already at ceiling and needs about 6 s per 20k rows. The Rust `assertions.csv` pairs as a
+3 bonus HURT on dev (99.52% vs 99.83% row exact), so they are off by default (`--rust`).

## Extraction per world (v1, `measure.py`, percentages)

| World | Pair P | Pair R | Pair F1 | Value F1 | Row exact | Anchors | Targets | Interval acc | v2 post-hoc row exact |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dev | 99.89 | 99.86 | 99.88 | 99.88 | 99.83 | 99.84 | 99.83 | 100.00 | 99.99 |
| **cal (held-out)** | 99.89 | 99.85 | 99.87 | 99.86 | **99.81** | 99.74 | 99.82 | 100.00 | 99.99 |
| **sealed (held-out)** | 99.58 | 99.55 | 99.57 | 99.53 | **99.44** | 99.63 | 99.42 | 100.00 | 99.70 |
| diag | 99.92 | 99.86 | 99.89 | 99.79 | 99.63 | 99.84 | 99.54 | 100.00 | 99.75 |
| pilot | 99.87 | 99.62 | 99.75 | 99.62 | 99.40 | 100.00 | 99.10 | 100.00 | 99.80 |
| prac | 99.78 | 99.73 | 99.75 | 99.75 | 99.68 | 99.53 | 99.76 | 100.00 | 99.84 |
| extdev / extcal / extsealed | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 |
| synth | 99.78 | 99.69 | 99.73 | 99.73 | 99.62 | 99.74 | 99.61 | 100.00 | 99.90 |
| clean (dev without asides) | 99.89 | 99.87 | 99.88 | 99.88 | 99.84 | 99.84 | 99.84 | 100.00 | 99.99 |

Target slices (value F1 / row exact, %): arity 3 is the weakest (dev 99.49, cal 98.38, sealed 97.24 row exact);
distractors cost almost nothing (sealed 99.47 without, 99.33 with); external-transfer track 100% everywhere.
Narrator asides are handled: removing them (clean) moves dev row exact only from 99.83 to 99.84.

## End to end (worker A `e2e.py`, targets only; accuracy / macro-F1 / points per row, %)

| World (n targets) | Interval engine | Point engine | Gold forms, interval | v2 post-hoc, interval |
|---|---|---|---:|---:|
| dev (18,103) | 99.82 / 99.05 / 99.72 | 97.78 / 65.17 / 95.64 | 100.00 | 99.96 |
| **cal (18,103)** | **99.62 / 98.30 / 99.41** | 97.60 / 64.90 / 95.20 | 100.00 | 99.99 |
| **sealed (18,103)** | **99.45 / 99.14 / 98.91** | 97.40 / 65.30 / 94.81 | 100.00 | 99.52 |
| diag (4,103) | 99.85 / 99.85 / 99.71 | 66.56 / 53.25 / 33.12 | 100.00 | 99.93 |
| pilot (334) | 39.22 / 28.38 / 39.22 | 39.22 / 35.24 / 23.95 | 39.22 | 39.22 |
| prac (1,265) | 38.58 / 39.75 / 38.34 | 53.60 / 33.36 / 7.27 | 38.66 | 38.58 |
| extdev / extcal / extsealed (334 each) | 100 / 100 / 100 | 66.77 / about 53.5 / 33.53 | 100.00 | 100.00 |
| synth (18,103) | 99.46 / 98.46 / 99.03 | 97.38 / 64.66 / 94.85 | 100.00 | 99.72 |
| clean (18,103) | 99.82 / 99.09 / 99.72 | 97.78 / 65.17 / 95.65 | 100.00 | 99.96 |

Always-true scores 83.35% on dev, cal and sealed. Pilot and prac are capped by their deliberately incomplete evidence
(gold-forms ceiling 39.22% and 38.66%), and B matches the cap.

## Runtime (20k-row world, OMP/BLAS threads = 2, Apple M5 Pro)

About 7.6 s wall per world (1.0 s training on practice plus 5.9 s extraction), peak RSS 0.83 GB, one core in practice;
A's engine adds 0.16 s. Expect 1.5x to 3x slower on the organizers' x86 box.

## Rules added after inspecting dev, pilot, prac and diag (never cal, sealed, extcal, extsealed or synth before v1)

1. Interval phrase regex (three date spellings plus ISO, end + 1 day).
2. Aside dropping: a clause with no subject mention, first-person or narrator words (I, my, me, someone, anyway) and no
   "down for/as" is dropped; subject-less clauses beside real ones are dropped.
3. Only singular pronouns are references ("They have X on version Y" is generic).
4. Pronoun antecedents: earlier subjects in the same row before the previous row; priors 1.0 first reference, 0.5 later.
5. Value-first constructions: in "I have V down for/as ... S" and "V is the <role> at/for/of S", S ranks first.
6. A lower-case one-word alias after a/an/any/no/major ("a major outage") is not the named entity.
7. Attribute-word overlap: 4-character prefix stems, exact short tokens (Series A vs B), +0.2 per matched word, and four
   paraphrases (yearly/annually/a year/per year -> annual; lasts -> life; starts at -> minimum; up to -> maximum).
8. Per-candidate masking in the TF-IDF input.
9. "up to" on a max/limit/cap attribute drops the `le` op.
10. A counted noun outside the practice unit set of a one-unit attribute takes the practice unit (meetings -> sitting).
11. Comparatives values.py ignores (older/newer/earlier/later than, no newer than, at least, at most) apply to any kind
    (from diag).
12. A bare decimal no rule reads becomes a version candidate (from diag).
13. Negative numbers such as `-29.58%` (from diag).

v2 (`extract_v2.py`) is post-hoc, written after reading held-out error buckets: a period after a one-letter capital ends
a sentence; costs / pay -> price; a lexicon mention used as a noun adjunct after an earlier reference is not a candidate.
The official numbers are v1.

## Top error classes (v1)

Dev, all 34 error rows: 22 an entity used as a noun modifier ("Pixel 10 is on Android version 24.11." read as Hooly
Android version); 7 a period after a one-letter capital blocked the clause split ("charging power of 51 W. Hooly Pixel
10 Pro has ..."); 5 a boolean sibling beat the money attribute (ad_free_option instead of ad_free_price).

Held-out sealed (inspected only after the final run), 112 error rows: 39 Android-version modifier; 25 unseen
value-first template "We're looking at V for S's A"; 20 unseen template "They gave V as the A for S"; 20 "employs N
employees" read as webcast_viewers instead of headcount; 6 one-letter-capital split; 2 other. Synth adds 17 rows of
"announcement date" read as date instead of announced.

Not done: confidence calibration (assertion conf is a raw sigmoid), sentence-transformers, a Rust port. The suite text
comes from a finite template generator; 99%+ here does not show how B does on unrestricted organizer prose.
