# Worker C: extractor learned from the suite's generator

Copied from worker C's final message (2026-10-28 evening); the harness blocked subagents from writing report files.
`REPORT-draft.md` is C's incremental draft (method, dev error analysis, robustness table).

**Bottom line.** Learning the generator from the allowed material gives exact extraction on every in-sample world and
on all four held-out worlds; one held-out row out of about 41,000 came out wrong. With worker A's interval engine, label
accuracy is 1.0000 on dev, cal, sealed, extcal and extsealed. This is a ceiling **in distribution only**: GUIDE.md says
the held-out worlds share the lexicon, attribute phrases, value spelling and interval grammar.

## Training data used

`realistic-training-mmr-20000/training.jsonl` (20,000 examples) and `gold/rows.jsonl` of development-20000,
synthetic-20000, diagnostic-6000, pilot-500, practice-1897 and external-development. Not used: practice.csv, the Rust
assertions.csv, MiniLM. train.py never read cal, sealed, extcal or extsealed; measure.py read their gold once, in the
final run, and nothing changed afterwards.

## Method

Measured on the training material: the only text between two gold spans is `; `, `, and ` or `. `; asides only follow
the last assertion; a context row is always the previous row; with two fallbacks (negative percentages, versions after
comparison words) the w7 grammar reads the gold value in 100% of spans.

1. Interval: optional `From <date> through <date>, ` prefix -> half-open interval; split the rest on the three separators.
2. Aside cut by rule: after the first piece, a piece is an assertion only if it names a lexicon subject, or has a strong
   pronoun plus at least 25% known attribute words or a typed value, or any pronoun plus at least 50% known words
   ("known" = seen in some training assertion piece; asides never feed that vocabulary).
3. Subject and attribute chosen together: TF-IDF LinearSVC over 321 attributes and over 62 subjects plus PRON; only
   attributes legal for the subject are scored, with penalties when the expected value kind is absent; the best pair
   whose value is readable wins.
4. Value: grammar reading of the attribute's kind, `op` from a learned (attribute, preceding words) table, unit from a
   learned (attribute, grammar unit) map, polarity from negation words (3,102 of 3,102 training booleans right).

## Extraction (results/C.jsonl, tag `final`)

| World | Split | Pair F1 | Triple F1 | Row exact | Interval exact |
|---|---|---:|---:|---:|---:|
| dev, synth, diag, pilot, prac, extdev, clean | in-sample | 100% | 100% | 100% | 100% |
| cal | HELD-OUT | 100% | 100% | 100% | 100% |
| sealed | HELD-OUT | 100% | 100% | 99.995% (1 row) | 100% |
| extcal, extsealed | HELD-OUT | 100% | 100% | 100% | 100% |

A model trained with dev excluded got all 20,000 dev rows exact.

## End to end (accuracy / macro-F1 / points per row / ECE)

| World | Split | Interval engine | Point engine |
|---|---|---|---|
| dev, synth, clean | in-sample | 1.0000 / 1.0000 / 1.0000 / 0.010-0.020 | 0.9795 / 0.653 / 0.9589 |
| diag, extdev | in-sample | 1.0000 / 1.0000 / 1.0000 / 0.021-0.023 | 0.667 / 0.533 / 0.334 |
| pilot | in-sample | 0.3922 / 0.2838 / 0.3922 | 0.3922 / 0.3524 / 0.2395 |
| prac | in-sample | 0.3866 / 0.3999 / 0.3866 | 0.5368 / 0.3342 / 0.0735 |
| cal | HELD-OUT | 1.0000 / 1.0000 / 1.0000 / 0.060 | 0.9795 / 0.6531 / 0.9589 |
| sealed | HELD-OUT | 1.0000 / 1.0000 / 1.0000 / 0.064 | 0.9795 / 0.6529 / 0.9589 |
| extcal | HELD-OUT | 1.0000 / 1.0000 / 1.0000 / 0.071 | 0.6677 / 0.5369 / 0.3353 |
| extsealed | HELD-OUT | 1.0000 / 1.0000 / 1.0000 / 0.068 | 0.6677 / 0.5352 / 0.3353 |

Pilot and prac are capped by their deliberately missing evidence (`oracle_only`), not by extraction. Higher held-out ECE
with every label right means the confidences are underconfident on unseen wording.

## Runtime (Apple M5 Pro)

Extraction 6.0 to 6.3 s wall per 20,000-row world, one process, about 0.63 GB peak; full training 39 s on 2 threads.

## Error analysis

Dev during development (dev held out of training), first version 17 of 20,000 wrong: 11 subject wrong (`Hooly I/O 2026`
read as `2027` because digits were masked; fix: drop a predicted subject that differs from a named one only in digits),
4 missed assertion (`. ` after a single capital read as an initial; fix: abbreviation guard), 2 boolean polarity
("has not raised Series A"; fix: negation rule). After the fixes 0 of 20,000 wrong.

Robustness probe (leave one family out, dev also out): one unseen aside family ("my coffee alone cost €9, ...") scored
0.88% row exact before the general fixes (pronoun plus price looked like a price assertion); unseen template families
99.85 to 99.97%. After the fixes all 8 aside families and all 3 template families scored 100%.

Held-out: cal no wrong rows; sealed one wrong subject ("They gave 57 minutes as the call length for Hooly's Q4
results." -> Q3 2026 Results instead of Q4 2025 Results; masking digits erases Q3/Q4), label still correct.

## What would push further

Keep quarter and year digits in the subject features or learn a partial-name alias table (not applied: it would be
tuning after seeing held-out results); calibrate confidence on a harder proxy; the real remaining test is out of
distribution (human prose, another generator, the practice-file wording), where the rule-based aside cut and pronoun
rules are the most likely to break. Not done: embeddings, Rust parser output, practice.csv, independent code review.
