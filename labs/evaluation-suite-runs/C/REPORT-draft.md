# Worker C: learned extractor on the evaluation suite (in progress)

## Training data used (allowed material only)
- `realistic-training-mmr-20000/training.jsonl` (20,000 examples: text, previous-row text, gold spans and forms).
- `gold/rows.jsonl` of development-20000, realistic-synthetic-20000, diagnostic-6000, pilot-500, practice-1897, external-development.
- Not used: `/Users/mogaeduard/VERIDYCT/data/practice.csv` (the suite's practice-1897 gold already covers that shape), Rust `assertions.csv`, MiniLM.
- Held out, never read by train.py: calibration-20000, sealed-20000, external-calibration, external-sealed.

## Method (what was learned from the generator)
Measured on the training material: gaps between gold assertion spans are exactly `; `, `, and ` or `. `; asides only trail the
last assertion; a context row is always the previous file row (single-subject); the typed-value grammar (w7 values.py) reads the
gold value in 100% of deduplicated spans once two fallbacks are added (negative percentages, versions after comparison words).
1. Segment: optional `From <date> through <date>, ` prefix -> half-open interval; split the rest on the three separators (`Inc. ` guarded).
2. Aside cut: LinearSVC on TF-IDF (word 1-2 + char_wb 2-5, digits masked) plus mention/pronoun flags; first aside piece ends the row.
3. Joint subject/attribute: LinearSVC attribute model (321 classes) + subject model (62 subjects + PRON); candidates = lexicon
   mentions (+1 bonus), top-3 subject predictions (digit-blind twins of a mention dropped), previous subject when a pronoun is present
   (previous piece, else previous row's last subject); pick max score over attributes legal for the subject, -1 if the attribute's
   value kind is absent from the piece.
4. Value: grammar candidates of the attribute's kind (learned attribute->kind), first non-alternative reading; `op` from a learned
   table keyed by (attribute, three words before the value) with backoff; unit from a learned (attribute, grammar unit) map;
   boolean polarity = no negation word in the piece (3,102/3,102 training booleans).
Train: 45 s (full) on 2 threads. Extraction: 6-7 s per 20,000-row world, single process.

## Development error analysis (dev excluded from training; dev = development-20000)
v1 (dev-held-out model): 17 of 20,000 rows wrong (row-exact 99.91%, triple F1 99.93%):
- subject wrong, 11: `Hooly I/O 2026` read as `Hooly I/O 2027` (digit-masked features cannot tell the years apart).
  e.g. "Hooly I/O 2026's date is April 14, 2026." / "The date for Hooly I/O 2026 is April 14, 2026."
  Fix: drop a predicted subject that is a digit-blind twin of a lexicon mention in the piece.
- missed assertion, 4: `. ` after a single capital was taken for an initial ("...51 W. Hooly Pixel 10 Pro has...",
  "...raised Series A. Bertram Gilfoil is..."). Fix: abbreviation guard only for words (training spans only hold `Inc. `).
- boolean polarity, 2: "Hooly AI has not raised Series A" read true by a learned polarity model. Fix: negation-word rule.
v2: 0 of 20,000 dev rows wrong with the dev-held-out model.

Robustness probe (leave one family out of training, dev also out, scored on dev rows of that family):
template families recollection 99.95%, conversation 100%, possessive 99.92% row-exact; aside families 0/3/5/7 100%,
aside family 4 (`my coffee alone cost €9, which annoyed me more than it should`) 0.88%: the pronoun `it` and `cost €9` made it a
price assertion. Fix (measured: every non-first assertion piece has a lexicon mention or a pronoun; no aside has a mention):
past the first piece, keep a piece only if it names a subject, or has a pronoun and at least half of its content words occur in
training assertion pieces (asides never feed that vocabulary). Same probe after the fix: see table below.

| Left out of training (dev also out) | Before rule fixes (row-exact) | After (row-exact) |
| --- | ---: | ---: |
| aside family 4 (coffee price + `it`) | 0.88% | 100% |
| aside families 0, 1, 2, 3, 5, 6, 7 | 100% (0,3,5,7 measured) | 100% each |
| template family recollection | 99.95% | 100% |
| template family conversation | 99.97% | 100% |
| template family possessive | 99.85% | 100% |
| dev-held-out model on all of dev | 99.91% (v1) | 100% (20,000/20,000) |

Fixes after the family probe, all general: past the first piece the aside decision is a rule (the learned aside model only sets
confidence); a capitalised or piece-initial pronoun (`You pay €787 for It`) counts as a strong back-reference; the best
(subject, attribute) whose value is readable wins instead of the top pair; boolean attributes get -1 when the piece holds a
money/percent/date/duration/version value (0 of 3,102 training booleans do); number words no longer match inside words
(`alone` read as `one`).
