# Practice experiments: full worker report

Raw report from the 2026-10-28 knowledge base research, kept as written by the worker so nothing is lost. The curated version, with verdicts reconciled against the contract and the measured results, is [the knowledge base research](../knowledge-base.md).

- **Author:** E1, Claude Opus 5.5 experiment worker.
- **Scope:** measured variants V0 to V11 on data/practice.csv.
- **Tools:** free tools only (WebSearch, WebFetch, GitHub, crates.io, arXiv); no paid research service.
- **Caveat:** V9 and V11 features were designed after reading R80 error examples, so their numbers are optimistic until a holdout the features never saw confirms them.

## 1. Data facts (verified with all labels)

- **Pages:** grouping consecutive ids that share a date gives **291 pages** (1 to 15 rows each, median 7) over **159 distinct dates**, so one date can hold several pages. The facts cover **514 keys** (subject, attribute, kind, plus the unit dimension or currency/period). 439 keys appear on more than one page and 326 have more than one distinct value. Every (subject, attribute) is in the lexicon, so the lexicon gives no out-of-vocabulary signal.
- **False rows:** there are 277, of which 202 are single-fact. **All 202/202** single-fact false rows have their key stated on a true row of another page. **276/277** false rows have a fact that differs from some true anchor on another page. **250/277** are contradicted by the latest true anchor at or before their date (the V2 rule with every label visible).
- **A contradiction does not prove a row false.** Taking single-fact rows by whether they match the nearest anchor before / on the same day / after their date (Y = match, N = no match, - = no anchor on that side):

  | pattern | true | false | unsure |
  |---|---|---|---|
  | Y-Y | 275 | 0 | 0 |
  | Y-- | 179 | 0 | 7 |
  | --Y | 171 | 0 | 8 |
  | N-Y (new value, confirmed later) | 150 | 18 | 0 |
  | Y-N | 130 | 23 | 2 |
  | --N | 91 | 43 | 9 |
  | N-- | 53 | 40 | 2 |
  | N-N | 30 | 68 | 0 |
  | --- (no other true anchor) | 79 | 0 | 7 |

  Stale values (true earlier but not at the nearest bracketing anchors) are 22 false against 2 true.
- **Lying pages cluster:** 186/277 false rows sit on pages with at least 2 false rows, and 128/291 pages have no false row.
- **Unsure rows (39):** 33 have every fact key stated on another page. "No key elsewhere" explains none of them, and rows with no other true anchor are 79 true against 7 unsure. The only weak signal is distance: 29/39 unsure rows have their nearest same-key observation more than 90 days away, but so do 204 true rows.
- **As-of precision** (labels hidden for the last 20% of dates, cut at 2026-09-03, 438 rows): over 233 keys whose last hidden observation is true, the latest earlier anchor value gives **coverage 75.5%, precision 53.4%**. Adding the unlabelled votes gives coverage 79.4% and precision 50.8%. Keys that held one value before the cut score 49/99, keys that held several score 45/77. Carrying the last value forward is not a safe way to generate claims: about half the keys change in the final two months.

## 2. Results

Metrics are on hidden pages only. R80 is 5-fold GroupKFold by page. R10 is the mean of 10 seeded splits with 10% of pages labelled. Confusion matrices are in the result files. "cov" is the share of rows not predicted unsure; ECE and Brier score only those rows.

| variant | reg | acc | mF1 | F-rec | F-prec | U-rec | cov | ECE | Brier |
|---|---|---|---|---|---|---|---|---|---|
| V0 always true | R80 | .833 | .303 | 0 | 0 | 0 | 1 | .012 | .139 |
| | R10 | .831 | .303 | 0 | 0 | 0 | 1 | .029 | .142 |
| V1 exact vote | R80 | .756 | .467 | .500 | .397 | .178 | .955 | .259 | .235 |
| | R10 | .760 | .450 | .427 | .358 | .136 | .965 | .259 | .238 |
| V2 latest anchor | R80 | .657 | .455 | .869 | .357 | .274 | .910 | .286 | .286 |
| | R10 | .234 | .223 | .391 | .240 | .798 | .415 | .476 | .476 |
| V2b (+next anchor) | R80 | .740 | .505 | .789 | .464 | .274 | .910 | .195 | .194 |
| | R10 | .241 | .228 | .377 | .245 | .798 | .414 | .456 | .456 |
| V3 fwd, tau 30 | R80 | .690 | .469 | .891 | .360 | .178 | .955 | .272 | .279 |
| | R10 | .663 | .447 | .899 | .319 | .136 | .968 | .261 | .300 |
| V3 sym | R80 | .731 | .498 | .942 | .400 | .178 | .956 | .161 | .210 |
| | R10 | .697 | .470 | .932 | .351 | .136 | .968 | .164 | .237 |
| V3 asym (future x0.5) | R80 | .737 | .502 | .942 | .409 | .178 | .955 | .171 | .209 |
| | R10 | .692 | .467 | .928 | .347 | .136 | .967 | .164 | .238 |
| V3sel (tau, window by train LOPO) | R80 | .747 | .508 | .942 | .419 | .178 | .955 | .205 | .212 |
| | R10 | .696 | .468 | .914 | .348 | .136 | .968 | .228 | .255 |
| V4 page reliability | R80 | .737 | .502 | .942 | .408 | .178 | .955 | .171 | .209 |
| | R10 | .697 | .469 | .921 | .350 | .136 | .967 | .170 | .237 |
| V5 intervals | R80 | .746 | .508 | .942 | .420 | .178 | .955 | .166 | .201 |
| | R10 | .699 | .470 | .923 | .353 | .136 | .967 | .157 | .231 |
| V5+V4 | R80 | .745 | .507 | .942 | .418 | .178 | .955 | .163 | .201 |
| | R10 | .703 | .472 | .915 | .356 | .136 | .967 | .163 | .230 |
| V6 neg (single-fact false) | R80 | .741 | .505 | .942 | .414 | .178 | .955 | .167 | .203 |
| | R10 | .699 | .470 | .924 | .352 | .136 | .967 | .158 | .231 |
| V6 blame | R80 | .740 | .504 | .942 | .413 | .178 | .955 | .166 | .204 |
| V6 weak neg per fact | R80 | .731 | .499 | .942 | .400 | .178 | .956 | .168 | .211 |
| V7 isotonic + threshold | R80 | .826 | .498 | .813 | .484 | 0 | 1 | .044 | .100 |
| | R10 | .799 | .471 | .739 | .423 | 0 | 1 | .050 | .112 |
| V8 HGB fusion | R80 | .886 | .513 | .490 | .790 | 0 | 1 | .030 | .086 |
| | R10 | .840 | .421 | .284 | .597 | 0 | 1 | .051 | .118 |
| V8 LR fusion | R80 | .881 | .488 | .395 | .875 | 0 | 1 | .034 | .092 |
| | R10 | **.851** | .463 | .365 | .682 | .025 | .993 | .039 | .107 |
| V9 LR fact-level bracket | R80 | .902 | .553 | .675 | .763 | 0 | 1 | .038 | .077 |
| | R10 | .816 | .443 | .465 | .502 | 0 | 1 | .067 | .122 |
| V9 HGB | R80 | .876 | .518 | .602 | .665 | 0 | 1 | .039 | .088 |
| | R10 | .807 | .433 | .462 | .481 | 0 | 1 | .047 | .123 |
| V11 = V9 LR + 1 round self-training | R80 | **.907** | **.560** | .695 | .793 | 0 | 1 | .038 | .073 |
| | R10 | .809 | .438 | .461 | .499 | 0 | 1 | .061 | .124 |

Extra variants I added beyond the brief:
- **V2b:** a fact also counts as true when it matches the first anchor after its date (change-point reading).
- **V9:** a model of P(fact true) over bracket features: match with the nearest anchor before, on the same day and after, the gaps, stale and premature flags, single-fact negatives, kernel votes, a bracket over anchors plus votes, and log ratios to neighbouring values (between-neighbours flag, power-of-ten flag). Row P(true) is the product over facts. Isotonic calibration is fitted on inner GroupKFold out-of-fold predictions, and the threshold is chosen on the labelled rows.
- **V10:** a smoothed category table. It was worse: .842/.481 (R80), .768/.360 (R10).
- **V9 variants that were neutral or worse:** LR with C chosen by inner CV (.900/.547, R10 .822/.447), one-hot categories plus stage-2 page suspicion (.891/.535), and a gap-based unsure rule. Inner selection rejected the gap rule in every split.

Selections made on training data: V3sel chose tau 7 days with a symmetric window in 5/5 R80 folds and 8/10 R10 splits. Calibration on the same rule: raw-margin ECE was .167 (R80) and .158 (R10); after isotonic (V7) it is .044 and .050. V9 HGB went from .066/.126 uncalibrated to .039/.047.

**Leakage you should know about:**
- The shared settings for V4 to V8 (tau 30, symmetric, future evidence x0.5) were fixed after I had seen the V3 R80 numbers.
- The V9 and V11 features were designed after reading error examples drawn from R80 folds and the all-label category analysis. Treat the V9/V11 numbers as optimistic.
- Everything else (tau/window, thresholds, unsure bands, LR C, isotonic fits) was chosen on labelled pages only. Because a row's own page is always excluded from its evidence, predictions on labelled rows are leave-one-page-out.

## 3. What worked, what did not, why

**Worked**
- **Future evidence and change-point semantics.** V2 to V2b gains 8.3 points of accuracy (R80), and V3 forward-only to symmetric gains 4.1. Many true rows are the first statement of a new value. p-1886 says Gmail attachments are 40 MB after five anchors at 20 MB. p-1270 says Android 17.1 is current after 17.0. A "latest earlier anchor wins" rule calls these false.
- **The learned fact model over bracket and magnitude features (V9/V11).** This is the biggest lever: R80 accuracy goes from about .75 (rules) to **.90 to .91**, false-precision from .42 to .76 to .79, and Brier to .073.
- **Isotonic calibration on leave-one-page-out scores.** ECE drops from about .16 to .04 on every rule and model it was applied to.
- **Intervals (V5):** +0.9 points accuracy on V3 and +0.7 on V2b. It fixes cases such as p-168, which says "2026" while the anchor says 2026-03-24.

**Did not work**
- **V4 (reliability reweighting of votes):** no measurable effect. In R80 the anchors dominate. In R10, reliability estimated from noisy votes adds little. The page-level clustering of lies (186/277) gave only +0.4 points even when used as a stage-2 feature.
- **V6 negative evidence:** neutral (-0.5 points). Treating every fact of a false row as weak negative evidence hurts (-1.5 points in R80).
- **Unsure:** no variant predicts it usefully. Unsure rows match the anchors as often as true rows do. p-1032 (Chrome bug bounty €50,000, every later anchor €50,000) and p-1519 (60 help guides, four earlier anchors at 60) are both labelled unsure.
- **R10:** no variant gains much over always-true on accuracy. Best accuracy is V8 LR at .851 (+2.0 points); best macro-F1 is V5+V4 at .472 and V7 at .471. About 190 labelled rows, roughly 28 of them false, are too few for the fact model, and self-training did not help.

**Failure modes**
1. **When a value changed is unobservable between bracketing anchors.** p-499: 80 templates on 05-20, with anchors at 30 on 03-20 and 80 on 08-25, is false. p-985: Lisbon rent €39,000 on 07-09, with €27,000 on 05-06 and €39,000 on 08-20, is false. Both are predicted true, and the same pattern holds 150 true rows.
2. **Restatements invert the time prior.** p-466 (1,800 customers) and p-455 (€6.9M revenue) are true restatements of Q1 2026 made on 10-27. The earlier p-1126 (18,000 customers) is false and p-1123 (€68M) is unsure. The power-of-ten feature penalises the true later value, so both are predicted false with confidence 1.00.
3. **The learner misses easy cases.** p-365 states Pixel Watch €399 with €349 anchors on both sides, yet is predicted true at 0.81. p-1196 has a stale MAU of 58M and is predicted true at 0.66.

## 4. Scripts and how to rerun

The scripts were written in a session scratchpad and are now in the repository:

- [`labs/kb-experiments/exp.py`](../../../labs/kb-experiments/exp.py): data facts, the as-of measurement, V0 to V8 and the metrics. A full run takes about 1 to 2 minutes; recorded output is [`results_v0_v8.txt`](../../../labs/kb-experiments/results_v0_v8.txt).
- [`labs/kb-experiments/v9.py`](../../../labs/kb-experiments/v9.py): V9 to V11, about 80 seconds; recorded output is [`results_v9.txt`](../../../labs/kb-experiments/results_v9.txt).
- [`labs/kb-experiments/diagnostics/`](../../../labs/kb-experiments/diagnostics/): `cat.py` (bracket category table), `ana.py`, `asof2.py` (as-of split by stable and volatile keys) and `fail.py`, `fail2.py`, `fail3.py` (error examples).
- Environment: `uv` venv with Python 3.12, numpy, scipy and scikit-learn 1.9.1. Commands are in [the lab README](../../../labs/kb-experiments/README.md).
