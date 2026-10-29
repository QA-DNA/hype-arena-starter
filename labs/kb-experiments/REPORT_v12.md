# X3: independent-evidence (MMR) features on V11, and a copied-lie stress test

Date 2026-10-28. Run from `labs/kb-experiments`: `python v12.py` (about 80 s; numpy, scipy,
scikit-learn 1.9.1). Every number below is in [`results_v12.txt`](results_v12.txt), which the
script regenerates. Background: [the MMR research](../../docs/research/mmr.md) section 4 and
[the knowledge base research](../../docs/research/knowledge-base.md).

## Question

V11lr-self1 counts evidence by rows. A lie copied onto three pages then weighs like three
independent confirmations. Does counting independent evidence instead, the MMR idea of
discounting what is redundant with evidence already counted, improve V11?

## Variants (fixed before any result)

All keep V11lr-self1's pipeline (LR, stage-2 page suspicion, isotonic, one self-training round,
same threshold search); only the fact feature matrix changes. New columns are appended.

| Variant | Change to the V11 features |
| --- | --- |
| V12pages | add distinct-page counts of consistent and inconsistent anchors, unlabelled votes and (single-fact) negatives |
| V12mmr | add four MMR-discounted masses (anchors and votes, consistent and inconsistent): observations ordered by `exp(-abs(dt)/30)`, each weighted `rel * (1 - max sim to already counted)`, `sim` = 1 on the same page, else TF-IDF char_wb 3-5 cosine of the row texts (fitted label-free) |
| V12mmr-replace | the four masses replace `sum(vs), sum(vd), len(vs), len(vd)`; raw anchor features stay |

Two deviations from the brief are declared in the results header: the discount also covers the
anchor pools, and replace keeps the raw anchor features.

## Practice result: no gain beyond noise

Means over splits; paired against V11lr-self1 on identical splits, t cutoffs 2.26 (n=10) and
2.78 (n=5), no multiplicity correction.

| Variant | Regime | Acc | False rec | False prec | Brier |
| --- | --- | --- | --- | --- | --- |
| V11lr-self1 | R80 | 0.907 | 0.695 | 0.793 | 0.073 |
| V12pages | R80 | 0.903 | 0.724 | 0.756 | 0.074 |
| V12mmr | R80 | 0.905 | 0.723 | 0.766 | 0.073 |
| V12mmr-replace | R80 | 0.902 | 0.741 | 0.737 | 0.074 |
| V11lr-self1 | R10 | 0.809 | 0.461 | 0.499 | 0.124 |
| V12pages | R10 | 0.805 | 0.459 | 0.451 | 0.127 |
| V12mmr | R10 | 0.803 | 0.523 | 0.475 | 0.124 |
| V12mmr-replace | R10 | 0.822 | 0.459 | 0.535 | 0.125 |

- The only paired differences beyond noise are R80 false precision, all worse: V12pages -0.037,
  V12mmr -0.027, V12mmr-replace -0.056, each 0 of 5 folds better.
- In R10 nothing passes the t cutoff. V12mmr's false-recall gain (+0.062, 8 of 10) comes with
  lower false precision and accuracy, so it is a threshold shift, not a better model.

## Stress result: V11 is exposed to copied lies, and the MMR features do not protect it

Tell-free design (`hlie`, `hctrl`, built per R10 split): three copies of every false row on a
page hidden in that split, each on its own new page at +1, +7 and +30 days. Copies are never
labelled and never evaluated; metrics are on the original hidden rows only, on the same split.
The control copies the same number of hidden true rows (seed 12345).

| Variant | Scenario | False rec | False prec | Acc | Brier |
| --- | --- | --- | --- | --- | --- |
| V9lr | clean | 0.465 | 0.502 | 0.816 | 0.122 |
| V9lr | copied lies | 0.120 (-0.345) | 0.247 (-0.255) | 0.766 (-0.049) | 0.151 (+0.030) |
| V11lr-self1 | clean | 0.461 | 0.499 | 0.809 | 0.124 |
| V11lr-self1 | copied lies | 0.204 (-0.257) | 0.182 (-0.317) | 0.725 (-0.084) | 0.161 (+0.037) |
| V11lr-self1 | copied truths | 0.467 (+0.006) | 0.517 (+0.018) | 0.826 (+0.017) | 0.121 (-0.002) |
| V12mmr | copied lies | 0.201 (-0.322) | 0.269 (-0.207) | 0.763 (-0.040) | 0.160 (+0.035) |
| V12mmr-replace | copied lies | 0.179 (-0.280) | 0.235 (-0.299) | 0.762 (-0.061) | 0.166 (+0.041) |

- V11 loses more than half its false recall, worse in 10 of 10 splits on false recall, Brier and
  accuracy. Copying true rows changes nothing, so the damage comes from copied lies, not from
  more votes.
- Against V11's own degradation, V12mmr degrades 0.065 more on false recall (better in 4 of 10)
  and V12mmr-replace 0.023 more (5 of 10). Neither is beyond noise; neither protects.
- Why: the discount touches only the new columns. Copies still reach the model at full weight
  through `bracket(an + vo)` (a +1-day copy becomes the nearest-after match), `numeric`, the
  `marg` vote (which also feeds stage-2 page suspicion), and self-training, which turns about
  185 to 238 of roughly 760 lie copies into pseudo-true anchors (counted by the reviewer's probe,
  not in `results_v12.txt`). V9lr, without self-training,
  degrades even more, so self-training is not the main channel.
- MMR's best case: the copies are exact text (similarity 1), and it still did not help, so a
  paraphrase test would add nothing.

## Confounded scenarios kept for the record

`lie`, `control` and `mixed` in the results file copy rows from labelled pages too. In training
"has a duplicate" then predicts the class (every copied row in `lie` is false; 50% of copied rows
in `mixed` against 8.6% elsewhere), so V11 appears to improve under copying (acc +0.064 in
`lie`). The independent Opus review caught this; `hlie` and `hctrl` replace them as the headline.

## Verdict

- Do not adopt any V12 variant into V11.
- The copy vulnerability is real and untouched. The fix to test is source-level deduplication:
  merge near-duplicate rows across pages (TF-IDF cosine 0.9 or more) into one source before any
  feature is computed (bracket, numeric, `marg`, page suspicion, self-training), not an extra
  feature.
- Cheap runtime diagnostic: count near-duplicate cross-page texts in the real input. If they are
  common, source-level dedup becomes a priority.

## Limitations and leakage

- New features read only text, pages, dates and the labels of pages labelled in that split; a
  row's own page never counts as evidence. Copy rows carry no label (`YF = -1`), never enter
  training, isotonic or the threshold search, and are never evaluated. All asserted in code.
- R10 splits draw the labelled pages from the original 291 pages with the original seeds and pad
  copy pages as unlabelled, so stress and clean runs are paired.
- The five R80 folds and ten R10 seeds share rows; the noise rule is a heuristic and many cells
  were read. Practice is about a tenth of the run, and real copying may be paraphrased or partial.
- The tell-free scenarios and the paired degradation tables were added after the first results,
  at the reviewer's request; the variants, kernel and TF-IDF settings were not changed.

## Provenance

Implementation: Claude Sonnet 5.5 worker. Adversarial review: Claude Opus 5.5, which reproduced
the baseline and the clean and stress numbers independently and designed the tell-free scenarios.
The worker then reproduced the reviewer's numbers exactly.
