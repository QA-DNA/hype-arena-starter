# Benchmark results (practice.csv, 1,858 true/false rows, 5-fold CV)

Run: `./.venv/bin/python -m bench.run --split date|row --forms gold|parsed`. Raw numbers: `tasks/gold_*.json`, `tasks/parsed_*.json`.
`cw` is a proxy for the confidence-weighted score (the real formula is unpublished). Prior = everything true at 85.1%.

## Pass 1: gold facts (judging layer only)

| Judge | Date acc | Date logloss | Row acc | Row logloss |
|---|---|---|---|---|
| A bracketing + GBM | **0.920** | **0.222** | **0.921** | **0.214** |
| B truth discovery (feature GBM) | 0.908 | 0.253 | 0.906 | 0.244 |
| bracket_rule (reference) | 0.883 | 0.276 | 0.891 | 0.266 |
| C temporal rules | 0.882 | 0.313 | 0.878 | 0.313 |
| D retrieval (no parser) | 0.851 | 0.417 | 0.851 | 0.404 |
| E text cues | 0.851 | 0.411 | 0.851 | 0.409 |
| prior | 0.851 | 0.421 | 0.851 | 0.422 |

## Pass 2: facts from the real parser (out-of-fold)

| Judge | Date acc | Date logloss | Row acc | Row logloss |
|---|---|---|---|---|
| A bracketing + GBM | 0.868 | 0.361 | 0.872 | 0.347 |
| B truth discovery | 0.868 | 0.361 | 0.870 | 0.356 |
| bracket_rule | 0.866 | 0.408 | 0.860 | 0.406 |
| C temporal rules | 0.851 | 0.401 | 0.855 | 0.389 |
| D, E, prior | ~0.851 | ~0.41 | ~0.851 | ~0.41 |

Parser quality (hype/parse.py, first version, stopped by the user before it finished tuning):
- Fact precision 0.94, **recall 0.61**, F1 0.74; only 55-56% of rows have all their facts exactly right.
- Recall by value kind: version 0.86, money 0.73, duration 0.73, quantity 0.67, percent 0.64, date 0.59, **name 0.34, boolean 0.13**.
- Subject+attribute precision 0.94 but recall 0.62: most misses are rows where the parser emits no fact.

## Conclusions

1. **The parser is the bottleneck, not the judge.** Going from gold to parsed facts costs A about 5 points of accuracy (0.920 to 0.868) and 0.14 of log-loss; the gap between judges is far smaller than that.
2. **A and B are the top two judges** (A better on gold, tied on parsed; B keeps more high-confidence coverage 0.63 vs 0.31). D and E add nothing alone; C helps only as features.
3. Rows with no parsed fact fall back to the prior, so raising parser recall (booleans, names, dates, pronoun subjects) is the highest-value work.
4. Caveats: practice only (about 10% of the real input), so B and D, which gain from more rows, are probably understated; the pass-2 parser is a first version.

## Next

- Improve parser recall (target >= 85%): booleans, names, dates, neighbour-row subject context, attribute classifier abstention.
- Final judge: stack A + B + C features (+ E as a weak input), calibrated; re-run pass 2.

## Technique 1 (judge with gold evidence, parse-trust and soft hypotheses), parsed facts

`./.venv/bin/python -m bench.t1_experiment date|row` (judge: bench/judges/t1_soft.py; parser now also writes bench/hyps_*.json).
Noise guide at n=1,858: accuracy differences below ~0.015 and log-loss differences below ~0.018 are not significant.

| Split | Variant | Acc | Log-loss | Rows at conf>=0.9 | Acc there |
|---|---|---|---|---|---|
| date | A (parsed evidence, current) | 0.869 | 0.350 | 37% | 0.948 |
| date | + gold evidence | 0.878 | 0.317 | 44% | 0.969 |
| date | + gold evidence + trust features | 0.874 | 0.316 | 45% | 0.970 |
| date | + gold evidence + soft hypotheses | 0.882 | 0.315 | 46% | 0.966 |
| date | + gold evidence + trust + soft | 0.881 | 0.317 | 46% | 0.968 |
| row | A (current) | 0.877 | 0.331 | 39% | 0.965 |
| row | + gold evidence | 0.885 | 0.306 | 47% | 0.970 |
| row | + gold evidence + soft hypotheses | 0.888 | 0.307 | 52% | 0.962 |

Reading: the gain comes from building the timeline from the GOLD facts of labelled training rows (valid in the real run, where practice rows ship with forms) while judging rows keep parsed facts. Trust features alone (0.868/0.348) and soft hypotheses on top are within noise. Gold-fact ceiling is 0.920 / 0.222, so about 26% of the log-loss gap and 18-25% of the accuracy gap is closed.

## Technique 2 (parser acceptance stage), date split

Where gold facts were lost before the change (2,402 gold facts): correct 68.7%; right top guess withheld by the fixed threshold 11.0%; no subject/attribute option 6.0%; wrong/missing subject withheld 4.7%; right subject wrong attribute withheld 3.7%; emitted with wrong attribute 2.9%; emitted with wrong subject 2.7%; value not extracted 0.1%.
Change: a learned acceptance model (hype/parse.py: train_accept, trained on hypotheses from inner folds that never saw the row) replaces the fixed threshold.

| Parser | Fact P | Fact R | F1 | Rows all-exact |
|---|---|---|---|---|
| before (fixed threshold) | 0.910 | 0.688 | 0.783 | 63.2% |
| acceptance stage | 0.898 | 0.760 | 0.823 | 71.1% |

Recall by kind after: boolean 0.149 (was 0.20, worse), date 0.709, duration 0.830, money 0.832, name 0.679 (was 0.49), percent 0.801, quantity 0.832, version 0.867.

Judge (bench/judges/t1_soft.py, date split, parsed facts): gold-evidence 0.877 acc / 0.311 log-loss (was 0.878 / 0.317); with soft hypotheses 0.893 / 0.308. Within noise of before, so the recall gain barely moves the judge.

Oracle test (judge given GOLD facts for one kind only, rest parsed; baseline 0.877 / 0.311; all gold 0.920 / 0.222):
booleans 0.885 / 0.285; names 0.882 / 0.300; dates 0.878 / 0.308; quantities 0.890 / 0.284; money+duration+percent+version 0.895 / 0.296; booleans+names+dates 0.890 / 0.269.
Reading: booleans and quantities are worth about 0.026 log-loss each; dates almost nothing; names about 0.011.

## Booleans + numeric modules (hype/booleans.py, hype/numeric.py), date split

Evaluated leak-free with bench/eval_component.py; combined run: `python -m bench.combined_parse date` (writes bench/parsed_date_nb.json).

| Component | Fact P/R/F1 before -> after | Judge acc/log-loss before -> after |
|---|---|---|
| booleans (date) | 0.481/0.149/0.228 -> 0.924/0.770/0.840 | 0.877/0.311 -> 0.880/0.295 |
| booleans (row) | 0.456/0.207/0.285 -> 0.832/0.799/0.815 | 0.885/0.306 -> 0.886/0.291 |
| numeric (date) | 0.931/0.831/0.878 -> 0.974/0.913/0.942 | 0.877/0.311 -> 0.890/0.298 |
| numeric (row) | 0.951/0.768/0.850 -> 0.975/0.902/0.937 | 0.885/0.306 -> 0.897/0.287 |
| both merged (date, all kinds) | 0.898/0.760/0.823 -> 0.948/0.869/0.907 | 0.877/0.311 -> 0.892/0.293 |

Remaining gap (merged parse, judge t1_soft with gold evidence, date split, 1,858 rows; gold-fact ceiling 0.920 / 0.222):

| Group | Rows | Log-loss | Accuracy |
|---|---|---|---|
| all | 1,858 | 0.290 | 0.895 |
| true rows | 1,581 | 0.126 | 0.977 |
| false rows | 277 | 1.225 | 0.422 |
| parse exactly right | 1,557 | 0.238 | 0.912 |
| parse not exact | 301 | 0.558 | 0.804 |
| false rows, parse exact | 224 | 1.014 | 0.487 |
| false rows, parse not exact | 53 | 2.115 | 0.151 |

Parse recall is similar on true rows (0.875) and false rows (0.858). Reading: the remaining loss is concentrated in FALSE rows (15% of rows, log-loss 1.2, accuracy 42%), and even with an exactly right parse the judge catches only about half of them. The judge, not the parser, is now the main limit; the next gains should come from detecting stale vs invented values (timeline features, stacking, calibration against confident-wrong false rows).
