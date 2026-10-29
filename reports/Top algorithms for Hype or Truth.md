# Fix the parser first, then stack and calibrate

**Bottom line.** The ten techniques below are ranked by expected gain per hour. Almost everything that moves the Task 1 score runs through the parser, not through a cleverer judge. The measured facts are these. With gold facts the best judge (A, bracketing GBM) gets **92.0% accuracy and 0.222 log-loss**. With our parser's facts it gets about **87% and 0.35**. Parser precision is 0.91 and recall 0.69 (booleans 0.20, names 0.49, dates 0.64). A and B tie on parsed facts. Template mining failed (6% skeleton repeats). So the ranking is: (1) make the judge learn from the parser's real errors, (2) lift parser recall with a candidate-ranking scorer plus page-level subject carry-over, (3) add LLM-triaged rules for booleans, names and dates. In parallel, Task 2 gets (4) a corroboration-filtered fact base and (5) a strict "referee twin" validator that gates every claim. After that come the cheap polish steps: stacking, calibration and timeline features (6 to 8). The two expensive and uncertain ideas, transductive densification and large-scale LLM synthetic data, come last and sit behind decision gates (9 and 10).

**How much to trust the numbers.** The five research notes were written without access to their method file, and with little or no web verification. Most citations are from memory. Most gains are the researchers' estimates, not measurements. Every claim here carries one of three tags:
- **MEASURED**: measured in our repo (`tasks/results.md`, `tasks/algorithms.md`, `tasks/research-graph-and-augmentation.md`, or the numbers you gave me).
- **EST**: a researcher's estimate, or mine, with no experiment behind it.
- **LIT-MEM**: literature cited from memory, which may have wrong details.

No estimate here should be read as a fact. The ablations in the work plan are what decide. A caveat on the measured figures: `tasks/results.md` still shows the first parser version (precision 0.94, recall 0.61). I use your newer figures (0.91 and 0.69). The "subject not named" slice numbers (recall 0.75 vs 0.31) come from the older parser and will have moved.

## Summary table: the ten techniques

| # | Technique | Task | Expected gain (evidence tag) | Hours | Main risk |
|---|---|---|---|---|---|
| 1 | Train the judge on out-of-fold parsed facts, with parse-uncertainty features and soft top-2 hypotheses | 1 | Recovers part of the 5-point gap; about +1 acc, -0.02 log-loss (EST, my reconciliation; no note gives a number) | 1.5 to 2 | Leakage in the folds; confirm what pass 2 actually trained on |
| 2 | Candidate-ranking parser: rule value spans, lexicon-constrained (subject, attribute) scorer, page-level subject carry-over | 1 | Recall 0.69 to 0.75-0.80 (EST); diagnostic is MEASURED: recall 0.75 vs 0.31 with/without a named subject, 87% share a subject with the previous row | 4 to 5 | Wrong carried subject; precision drop |
| 3 | LLM-triaged error analysis, then hand-written rules for booleans, names and dates (relative dates, gazetteer, negation scope) | 1 | Booleans, names, dates up 10 to 25 points; fact recall +3 to 6 (EST) | 3 to 4 | Rules overfit 1,897 rows |
| 4 | Corroboration-filtered fact base with calibrated P(true on 29 Oct 2026) | 2 | About 85% to 97% true claims (EST, design reasoning); the largest Task 2 lever | 2 | Counting correlated parser output as independent evidence |
| 5 | Referee-twin validator plus controlled-grammar constructors for the 5 claim types, with quota selection | 2 | Prevents invalid claims, which still occupy slots (EST); guarantees compliance by construction | 5 to 6 | Validator drifts from the real referee |
| 6 | Stack judges A and B with a regularised logistic meta-learner on grouped OOF logits | 1 | Log-loss 0.35 to 0.32-0.335, accuracy +0.5 to 1.0 (EST) | 1.5 | Overfit or leakage; the gain may be noise |
| 7 | Calibration and output policy: Platt or beta, cap 0.99, subgroup offsets, structural "unsure" rule | 1 | Log-loss 0 to -0.01 over the current Platt step (EST); protective | 1 | Over-abstaining, or over-sharpening |
| 8 | Timeline features: hazard-rate gap, monotone-interval flags, stale vs invented vs pre-announcement | 1 | Accuracy +0.5 to 1.5, log-loss -0.01 to -0.03 (EST); attacks the 288 + 54 uncertain facts (MEASURED sizes) | 2 | The GBM already sees most of it |
| 9 | Transductive densification: unlabelled rows as soft observations (gated) | 1 | +1 to 3 accuracy on the real 18k (EST); the largest train/test mismatch risk | 3 | Pseudo-label feedback inflates confidence |
| 10 | Build-time LLM synthetic data: coverage generation plus context windows, two-model round-trip filter (gated) | 1 | Parser recall +2 to 5 (EST, two notes) | 4 to 8 | Circular filter; the paraphrase effect is unmeasured |

## What the notes agree on, and where they disagree

Four of the five notes independently arrive at the same idea: **stop feeding the judge hard, gold-trained facts, and let it see the parser's uncertainty**. The text-to-facts note says to train the judge on out-of-fold parser output and pass the candidate probability and margin as features. The temporal-judging note proposes "soft parse marginalisation" over K hypotheses. The calibration note proposes stacker features such as parse coverage and unparsed numeric tokens. The LLM-development note flags training the judge on parsed OOF facts as a no-LLM change that may beat any synthetic data. I merged all four into technique 1, implemented the cheap way (a feature route into the existing GBM, not an EM latent-variable model).

Where the notes conflict, I resolved it as follows.

- **Synthetic data rank.** The LLM-development note ranks forward synthetic generation first. The earlier graph report ranks it last, below rule changes, and says to run a learning-curve check first. I side with the earlier report. The rule-problem diagnosis (booleans, names, dates, subject carry-over) points at rules, and the 3,279 existing paraphrases have never been measured. Technique 10 is therefore gated on a 45-minute test.
- **Truth discovery.** The temporal note says TruthFinder and Dawid-Skene do not fit (single assertions, no source ids). The claim-generation note ranks "truth discovery" first. These are different things. The claim-generation version is dated agreement counting and a freshness decay, not iterative source-trust. I keep the second and drop the first.
- **Pseudo-labelling.** The temporal note proposes soft-observation self-training. The calibration note calls pseudo-labelling dangerous for a calibration-weighted metric. Both can hold only if the fold labels are masked everywhere and base predictions are cross-fitted. That is why technique 9 is gated.
- **Judge coverage at confidence 0.9 or higher.** `tasks/results.md` says B keeps 0.63 coverage vs A's 0.31. The calibration note quotes 56% vs 37%. I could not reconcile these. Recompute from the saved OOF predictions before using either.
- **Confidence cap.** The calibration note says 0.99, and only if the verified top bin is at least 0.975 accurate. The claim-generation note says 0.98 for Task 2. I use 0.99 for Task 1 (conditional) and 0.98 for Task 2.
- **Small neural encoder.** The text-to-facts note rates the legal risk "moderate". The LLM-development note says avoid it. No technique here ships one. It is an open question for the organizers.
- **Unsure rows.** The notes say 37 or 39. The practice file has 1,581 true, 277 false and 39 unsure (MEASURED in the claim-generation note).

## Detail on the ten techniques

### 1. Judge trained on out-of-fold parsed facts, with soft hypotheses

**What.** Today's judge is calibrated on gold facts but runs on parsed facts. Train and calibrate it on what the parser actually emits for held-out rows. Add features that describe parser trust: number of facts found, whether any fact was found, fraction of the sentence's numbers, dates and names that are covered, and the top-2 hypotheses' feature blocks with their posteriors.
**Gain.** The gap itself is MEASURED (0.920 to about 0.87 accuracy, about 0.13 log-loss). How much of it this recovers is EST. Foundations are LIT-MEM: Dempster, Laird and Rubin 1977 (EM); latent-variable models (Quattoni et al. 2007; Yu and Joachims 2009).
**Cost and risk.** 1.5 to 2 hours. The main risk is leakage: the parser's lexicon or rules must not have been built by looking at the test fold's rows. First check whether the pass-2 numbers already did this. The text-to-facts note says the gold-trained judge is over-confident on parsed input.
**Recipe.**
1. Fix date-grouped folds with `bench.common.fold_of`. For each fold, run the parser trained on the other four folds and save the facts.
2. Feed those facts to A and B in place of gold. Add the parse-trust features above.
3. Build row-level features from fact-level probabilities: minimum, product, count of facts below 0.5, and unparsed numeric tokens. Never fit per fact against the row label (a false row may have only one false fact).
4. Give rows with no parsed fact their own indicator and their own calibration group, not a flat 0.85.
5. Report the closed fraction of the gold-to-parsed gap.

### 2. Candidate-ranking parser with subject carry-over

**What.** Keep regex grammars for value spans (the value forms are a deterministic grammar). For each value, generate candidates (subject, attribute) from the lexicon, keeping only those whose kind matches. Score them with a GBM or logistic regression over window words, unit nouns, verbs, cue words and discourse state. Keep one attribute per value, and each (subject, attribute) at most once per sentence. Choose the subject jointly with the attribute: recency of the previous row's subject times attribute compatibility. When two subjects tie, emit a soft fact with a candidate list instead of a guess.
**Evidence.** MEASURED (first parser version): 635 of 1,897 rows (33%) never name their facts' subject. Subject+attribute recall is 0.75 where the subject is named and 0.31 where it is not. In 512 of 588 same-date cases (87%) a subject is shared with the previous row. The recall target 0.75 to 0.80 is EST (text-to-facts and LLM-development notes agree on the range, independently but without data). The design follows slot-filling pipelines and centering theory (Grosz, Joshi and Weinstein 1995; Barzilay and Lapata 2008; both LIT-MEM).
**Cost and risk.** 4 to 5 hours. Page ordering must hold at test time: verify that consecutive rows on one date really form a page in the unlabelled input. Evaluate only with date-block folds, since adjacent-row features inflate random-row splits.
**Recipe.**
1. Run an oracle test first (1 hour): substitute gold subject, gold attribute and gold value span one at a time to see which component costs the most.
2. Build candidate generation, features and scorer; calibrate the candidate probability on held-out folds.
3. Add the carry-over feature set: starts with a pronoun, "Our X", "He/She/It", date gap, previous subject's type, compatibility.
4. Pass the probability and margin on to technique 1.

### 3. LLM-triaged rules for booleans, names and dates

**What.** Dump the out-of-fold fact-level errors (about 600 to 1,000), have an LLM at build time cluster them and propose minimal cues, then **we** implement and test each rule on grouped CV. Accept a rule only if it improves fact F1 with a paired interval that excludes zero.
**Targets.**
- *Booleans* (recall 0.20): attribute-led candidates for every boolean attribute of every in-scope subject, plus a negation-scope rule. Read `contracts/value-forms.md` for the exact yes/no cue list and mirror it in the parser.
- *Names* (0.49): capitalised runs plus a gazetteer built from the lexicon, the practice facts and capitalised n-grams of frequency 2 or more in the input itself. The notes consider an input-derived gazetteer legal; it is the dataset, not outside knowledge.
- *Dates* (0.64): keep the precision tag (year, month or day) and resolve "today", "since", "last month" against the row date.

**Gain.** EST only (names to about 0.65, dates to about 0.80, fact recall +3 to 6). The per-dollar logic is plausible (about $0.2 per 1,000 errors triaged), but the LLM-proposed-rules literature is thin (LIT-MEM: Smith et al. 2022; Guan et al. 2023; Eyuboglu et al. 2022). Treat the LLM as brainstorming.
**Cost and risk.** 3 to 4 hours, mostly our time. Two or three rounds is the realistic limit. Do not accept every proposal.

### 4. Corroboration-filtered fact base with calibrated P(true on 29 Oct)

**What.** For each (subject, attribute) key build a dated observation list from gold forms on practice rows plus parser output on unlabelled rows. Estimate the current value and its probability. Keep only claims above a cutoff.
**Evidence.** The motivation is MEASURED: 14.6% of rows lie, 202 of 353 gold-form facts in false rows equal a value true on another date (stale), and 252 of 514 keys change at least once. The remaining design is the claim-generation researcher's reasoning, not an experiment.
**Cost and risk.** About 2 hours. The main risk is double-counting: the same sentence repeated across pages, or parsed rows confirming parsed rows with correlated errors.
**Recipe.**
1. Weight observations. A labelled-true row gets 0.97 and a labelled-false row 0 (use its other facts only if it has a single fact). An unlabelled row gets judge probability times parser precision (0.91), capped at 0.9.
2. Cluster by key and by exact normalised value. Keep different precisions separate (`2026-06` is not `2026-06-02`).
3. The current value is the latest cluster with total weight of at least 2, or one observation with trust of at least 0.95. Discard a lone latest observation that contradicts two earlier agreeing ones.
4. Multiply by a freshness factor from the key's mean time between changes. Drop keys last seen over 120 days ago or changed 3 or more times, or scale them down by 0.7.
5. Calibrate on practice with a backtest: pretend the as-of date is 15 August 2026, generate from earlier rows, and score against later gold rows. This also catches template bugs.
6. Choose the cutoff so expected false claims in 1,000 are below about 25. Exclude `op` values, plain four-digit counts, unsure rows, and booleans with a parsed negation unless two sources agree.

### 5. Referee-twin validator plus controlled-grammar constructors

**What.** Build the validator first. It parses each (type, form, text) with an independent, strict reimplementation of the referee rules in `contracts/`. Then write per-type constructors (fact, compare, change, at_event, relation) that emit text from a small grammar, a strict subset of the referee's phrase lists. Every claim must round-trip: re-read the text, and the value and subject must equal the form. The approach is classic controlled-language NLG (Reiter and Dale 2000; LIT-MEM). The claim-type typology borrows from TabFact and FEVEROUS (LIT-MEM), types only, not their models.
**Why it ranks this high.** Invalid claims still take slots, and the rules are full of traps (the claim-generation note lists about 15 families). Examples: a name inside a longer name refers to the longer entity, so "Hooly AI Pro" is a plan and not Hooly; banned time words and negations; one value per sentence; money needs its period on both sides of a change; four-digit counts read as years; booleans need the attribute words contiguous.
**Cost.** 1.5 hours for the validator (round-trip it first on the 1,581 true practice rows to find false rejects), then about 3 hours for constructors, plus 0.5 hour for selection. Selection is greedy with quotas and a per-key cap of 3, and it checks originality against **all** input rows at run time, not just practice. The suggested mix is EST: fact about 380, change 230, compare 220, at_event 90, relation 60; supply limits decide.
**Safe-margin rules.** Compare gt/lt only for relative gaps of 15% or more; change only when both clusters have weight of at least 2; at_event only for events whose date has stopped moving; relation only on constant facts such as `joined`. Do not paraphrase with an LLM; any wording outside the phrase lists breaks validity. Skip booleans for change.

### 6. Stack judges A and B

**What.** A logistic regression on the logits of A and B plus 6 to 8 cheap features (any_fact, log n_obs, parse coverage, the A-B difference). Keep it linear and below 10 features. Wolpert 1992, Breiman 1996 and Caruana et al. 2004 are the LIT-MEM sources.
**Gain.** EST: log-loss 0.350 to 0.32-0.335, accuracy +0.5 to 1.0. A and B tie on parsed facts, which suggests different errors. But both build on the same parsed facts, so they share the parser's errors. A text-only judge (E) is the most diverse input, and the notes mark its value as largest on empty-parse rows.
**Test for noise.** With 1,858 rows, a paired accuracy gap below about 0.012 to 0.015 or a log-loss gap below about 0.015 to 0.02 is noise (calibration note, EST from standard errors). So 0.868 vs 0.868 is a tie. Accept the stack only if the 95% interval of its gain excludes zero.
**Cost.** 1.5 hours. Every base logit given to the meta-learner must be out of fold.

### 7. Calibration and output policy

**What.** Fit a Platt or beta calibration on the stacked OOF score. These are 2 to 3 parameters, and the right size at 1,858 rows with about 280 minority rows. Skip isotonic (flat 1.0 plateaus; Niculescu-Mizil and Caruana 2005, LIT-MEM) and conformal sets (they give no printable confidence).
**Output rule (EST, from simulation on made-up Beta mixtures, not our predictions).** Report `conf = clip(p_cal, 0.5, 0.99)`. Never print 1.0. Answer true/false whenever p is at least 0.5. The notes' simulation showed that abstaining on merely low p lowered the score under the linear, log and Brier formulas. The official formula is unpublished, so this is the choice that is safe across formulas.
**Unsure.** Predict it only on structural evidence: no extracted fact and no observation for the key on either side. Enable it only if precision on the 39 practice unsure rows reaches about 0.5 to 0.6. The maximum gain is 0.005 to 0.02 per row (EST).
**Checks.**
- Look at subgroup calibration (any_fact, kind, n_facts), since a good global ECE of 0.014 (reported in the brief) can hide a 0.05 miss in the no-fact group.
- Compare mean predicted P(true) on the unlabelled input to the practice mean. Run the EM prior adjustment only if they differ by more than 0.03 (Saerens et al. 2002, LIT-MEM), since the shift is more likely covariate than label shift.
- Calibrate on parser-fact output, never on gold.

**Task 2 confidence.** Use the Wilson lower bound of measured accuracy per claim type, cap at 0.98, and avoid a flat 0.9 for every claim.

### 8. Timeline features: hazard gap, monotone interval, stale vs invented

**What.** Add a per-attribute change rate (empirical Bayes, from consecutive true observations), so that "did it change between the last observation and the row date" gets a probability. Add monotone flags for attributes that almost always rise (headcount, customers, versions): claim below the maximum earlier true value, claim above the minimum later true value, claim inside the bracket. Add stale vs invented vs pre-announcement flags (202 stale vs 158 invented false facts is MEASURED).
**Why this is aimed correctly.** The two uncertain buckets (288 "one side known, differs" with 174 true and 114 false, and 54 "both sides differ") are MEASURED. Everything else in the bracketing table is already 85% to 100% accurate.
**Gain.** EST only: accuracy +0.5 to 1.5, log-loss -0.01 to -0.03. The notes themselves say the GBM already sees nearest before/after and gaps. Full Bayesian online changepoint detection or Kalman models are not worth it with fewer than 5 observations per fact.
**Cost.** 2 hours.

### 9. Transductive densification (gated)

**What.** Treat every parsed fact in all ~20k rows as a noisy observation, weighted by the row's current P(true). Rebuild timelines, re-judge, and iterate with damping. The family is truth discovery over time (Dong et al. 2009; Pal et al. 2012; Li et al. 2015; all LIT-MEM).
**Why it is tempting.** Practice is about 10% of the real input, so timelines at test time are denser than anything we can test on. Judge B already gains from more rows.
**Why it is gated.** The mismatch risk is the biggest in the project, and it cannot be fully reproduced in CV. Correlated lies (the same invented value repeated across decks) defeat count-based methods. Self-training on one's own labels raises accuracy but worsens log-loss.
**Rules.** Mask the fold labels everywhere, including in the pool. Cross-fit. Exclude the row itself and its own document from its features. Count distinct dates, not raw repeats. Fix the iteration count and damping in advance. Ship only if the gain is above 1 point **and** log-loss improves, and trust the smaller of the real-CV and thinned-density-proxy results.

### 10. Build-time LLM synthetic data (gated)

**What.** Generate text from structured facts, so the label is right by construction. Three generators: coverage (every lexicon pair with 6 to 10 sampled values), paraphrase of real rows (already piloted: 3,279 outputs from 490 rows, 79% to 87% kept), and context windows of 3 to 6 consecutive rows where later rows drop the subject. The third matters most, because the 33% no-subject rows are exactly what single-sentence generators do not reproduce. The direction (structure to text) is supported by SynthIE (Josifoski et al.; the note fetched the abstract), though its huge-label-space setting overstates our gain. Counter-evidence on synthetic-only training is LIT-MEM (Li et al. 2023).
**Filter.** The existing `accept()` filter uses our own parser, which is circular for exactly the weak kinds (names, dates, booleans). Use agreement of two different LLM extractors there, and keep the gold value as the target.
**Gate.** First retrain the parser with the existing paraphrases attached to their source rows (45 minutes) and see if recall moves. Then do a learning curve at 25%, 50% and 100% of real data. If recall barely moves, stop. If it does, add context windows next.
**Cost.** About $5 to $6 for the full plan (EST from price anchors; spend so far is $0.14 of $100, hard-capped in code). Time is the real cost: 4 to 8 hours. Cap synthetic rows at about 70% of training, weight real rows 2 to 3 times, and use synthetic data for the parser only, never to calibrate the judge. In CV, assert that every synthetic row's source row is in the training fold.

## Recommended order of work, about 20 hours, two people

Dependencies are marked with arrows. Hours are counted from now. Reserve the last 3 hours for packaging.

**Hour 0 to 1 (both).**
1. Send the organizer questions below.
2. Person A: fix the folds, dump OOF parser output, and run the oracle ablation (gold subject, attribute, value span).
3. Person B: start the referee-twin validator (5a).
4. Either person: launch the 45-minute paraphrase-effect test in the background.

**Gate 1 (hour 1).** Which component costs the most points? If the oracle says subject/attribute assignment, go ahead as planned. If it says value spans, stop and look at the value grammar. If the paraphrase test shows a clear recall gain, move technique 10 up. If not, it stays gated.

**Hour 1 to 7 (Person A): parser.** Technique 2 (hours 1 to 5), then technique 3 (hours 4 to 7; start with the LLM triage dump, about $0.6, while 2 is still being built). Run the OOF parser again after each.

**Hour 1 to 8 (Person B): Task 2.** Validator, with every contract example as a test (hours 1 to 2.5). Fact base on gold forms only (2.5 to 4). Constructors (4 to 8). Gold-only is enough to start, so Task 2 does not wait for A.

**Gate 2 (hour 7).** Is parser fact recall at least 0.78? If yes, continue. If it is stuck around 0.70, spend the next 3 hours on technique 10's context windows instead of more rules.

**Hour 7 to 13 (Person A): judge.** Technique 1 (7 to 9) → technique 8 (9 to 11) → technique 6 (11 to 12.5) → technique 7 (12.5 to 13.5). Accept each step only if its paired interval excludes zero; otherwise keep the simpler model.

**Hour 8 to 13 (Person B).** Re-run the fact base on the improved parser output (depends on A's hour-7 parser). Selection, originality check against the full input, backtest at an earlier as-of date, then end-to-end checks with `check_output.py`.

**Gate 3 (hour 13).** Freeze the judge. Only now decide about technique 9, and only if there are 3 or more hours left. If densification fails the fold-masked test, skip it without regret.

**Hour 13 to 17.** Technique 9 or 10, whichever its gate allowed. Otherwise, extra error-triage rounds on the parser.

**Hour 17 to 20.** Docker offline run on 2 CPUs and 6 GiB, timed against the 30-minute limit with at least 2x headroom. Determinism check. Write output to a temporary file and rename. Exactly 1,000 claims with unique ids. Write the README and LLM-use log (provenance of generated material). The 20 sample rows at 09:00 on 29 October are a smoke test only; do not tune on them. Freeze by about 10:00.

## What not to do

- **Do not report confidence 1.0.** A wrong answer at 0.999 costs about 10 bits under log-type scoring (calibration note's simulation).
- **Do not abstain just because p is moderate.** Abstain only on structural evidence of "unsure".
- **Do not use an LLM, or LLM verdicts, at run time or as truth labels.** The rules forbid it, and the truth is defined by the Hooly universe.
- **Do not paraphrase Task 2 claims with an LLM.** Wording outside the phrase lists makes a claim invalid.
- **Do not trust random-row CV.** Same-date neighbours leak. Use date-grouped folds and a cluster bootstrap.
- **Do not chase tiny differences.** 0.869 vs 0.870 accuracy and 0.350 vs 0.351 log-loss are noise.
- **Do not pseudo-label and retrain without fold masking and cross-fitting.**
- **Do not build** temporal knowledge-graph embeddings, FactKG-style checkers, Allen interval algebra as a library, PSL or Markov logic, a Snorkel dependency, conformal sets, BiLSTM-CRF, or isotonic calibration at this sample size. The notes and the earlier graph report agree on all of these (LIT-MEM reasoning plus the measured fact that the judge gap between methods is under 1 point).
- **Do not scale synthetic data to tens of thousands of rows.** Returns flatten around 1 to 3 times the real data, and style homogenises (LIT-MEM).
- **Do not use `op` values as exact facts** (such as "over 10,000"), and do not use a lie-row's value as a confirmed falsehood.
- **Do not ship a small neural encoder or a CRF** before the organizers answer (see below). A CRF for names is safe legally but is a lower-priority extra, EST +0.05 to 0.10 recall on names and boolean cues.

## Questions to ask the organizers now

1. May a small encoder (MiniLM class, 22M parameters, ONNX int8) be part of the submitted system, or only classical models (rules, linear, gradient boosting, CRF)? The notes disagree on the risk and no ruling is known.
2. May the 1,000 Task 2 claims be **pre-generated at build time** by a script (with an LLM only for wording, if at all), or must the submitted system generate them at run time?
3. May the 20 sample rows released at 09:00 on 29 October be used as training or tuning data, or only as a smoke test?
4. Is a trained model or rule set whose training material and rules were written with LLM help acceptable, including LLM-written text committed in the repo and image? (The README quote the notes give is "LLMs may help you build your system, and make what it learns from, but the system itself may not be an LLM.")
5. What is the exact confidence-weighted scoring formula, and how is unsure scored? Without it the safe choice is `conf = p`, capped.
6. Do Task 2 claims need a stated confidence, and are they judged on truth, originality, or both? Does the original-text check use all input rows?

## What this changes

The most useful single takeaway is that the 5-point gap between gold and parsed facts cannot be closed by judging. It can only be narrowed by making the judge parser-aware (technique 1) and by raising recall (techniques 2 and 3), so those get the first half of the clock. The other lesson is that Task 2 is mostly a compliance problem, not a modelling one. A strict validator and corroboration-filtered facts matter more than any fancy generation, and Task 2 can proceed on gold facts in parallel with the parser work. Everything labelled EST here is a hypothesis to be tested by the gates, not a result.

## Sources

Primary inputs: the five notes in `research_notes/Top algorithms for Hype or Truth/` (calibration_stacking_abstention.md, claim_generation.md, llm_assisted_development.md, temporal_truth_judging.md, text_to_facts_extraction.md), `tasks/research-graph-and-augmentation.md`, `tasks/results.md`, `tasks/algorithms.md`, and the numbers supplied in the brief. Citations in the notes are from memory unless marked verified. URLs below come from the earlier graph report, which fetched them; I did not re-check them.

- FEVER mutation types: https://arxiv.org/abs/1803.05355
- Counterfactually augmented data (Kaushik et al.): https://arxiv.org/abs/1909.12434
- Data recombination (Jia and Liang): https://arxiv.org/abs/1606.03622
- Data programming (Ratner et al.): https://arxiv.org/abs/1605.07723
- Model-collapse warning (Shumailov et al.): https://arxiv.org/abs/2305.17493
- SynthIE (Josifoski et al.): https://www.arxiv.org/abs/2303.04132 (abstract fetched by the LLM-development researcher)
- Truth discovery survey (Li et al.): https://arxiv.org/abs/1505.02463
- Calibration, stacking, abstention references (Platt 1999; Niculescu-Mizil and Caruana 2005; Kull et al. 2017; Gneiting and Raftery 2007; Chow 1970; Wolpert 1992; Caruana et al. 2004; Saerens et al. 2002): from memory in the calibration note, unverified.
