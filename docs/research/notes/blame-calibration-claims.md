# Blame, calibration, claim generation and explanation

Raw report from the 2026-10-28 knowledge base research, kept as written by the worker so nothing is lost. The curated version, with verdicts reconciled against the contract and the measured results, is [the knowledge base research](../knowledge-base.md).

- **Author:** W3, Claude Sonnet 5.5 research worker.
- **Scope:** S5 blame, S6 calibration, S7 claim generation, S8 explanation.
- **Tools:** free tools only (WebSearch, WebFetch, GitHub, crates.io, arXiv); no paid research service.
- **Citations:** Citations the worker marked "not verified" were checked afterwards where possible; the verified URLs are listed in [the notes index](README.md#verified-citations).

## TLDR
- **S5 blame:** use a noisy-OR/EM over a per-fact truth timeline. Most facts can be checked against other pages, so each fact gets a P(false) from the evidence. A row is false iff any fact is false. Blame is P(fact false | row false), and a short loop gives a nearly closed form. MaxSAT, ILP and Reiter hitting sets are overkill and are IDEA-ONLY for the demo.
- **S6 calibration:** write about 80 lines of Rust yourself: PAV isotonic with Platt as a fallback, ECE/Brier, and a page-grouped k-fold. Calibrate on out-of-fold scores grouped by page. Map the score to a confidence with `max(p, 1-p)` and put the unsure band where the calibrated confidence is below a threshold chosen on out-of-fold data. No mature Rust calibration crate exists, and `pav_regression` is the only usable PAV crate.
- **Fusion classifier:** start with hand-weighted log-odds of the evidence features, then fit logistic regression (`linfa-logistic`, or about 60 lines of Rust). Add `lightgbm3` only if it beats that on group-k-fold. Rust GBDT crates are thin and `treeshap` is a one-month-old, 21-download crate, so a linear model's per-feature contributions are the safest explanation.
- **S7 claim selection:** the 1,000 all-true claims are a precision-at-k problem. Rank by calibrated confidence, greedy with type quotas (ILP not needed), and discount claims that share a single fact (de-duplicate by root fact). The conformal-selection results below give a defensible FDR story for the jury; that is the only reason to read them.
- **S8 explanation:** keep a small provenance record per verdict, in the spirit of semiring why-provenance but as plain lists of supporting and contradicting facts with page IDs and weights. Do not take on Datalog or argumentation engines. Static embeddings (`model2vec-rs`) are low priority and risky for the "no LLM" optics.

Crate numbers below come from the crates.io API on 2026-10-28. GitHub numbers come from `gh api`. Anything marked "unverified" I could not confirm.

---

### Noisy-OR / EM over latent per-fact truth (algorithm, classic; Pearl 1988; Dawid-Skene 1979 for the EM)
- Link(s): none needed. Textbook method, nothing to cite verbatim.
- What it does: each fact i has a latent truth t_i with prior p_i from the evidence. A row is true iff all of its facts are true, so P(row true) = Π(1-p_i). Given the row label, the posterior blame is P(t_i = false | row false) = p_i / (1 - Π(1-p_j)).
- Steps: S5, S6, S8
- Pros:
  - About 20 lines of Rust.
  - Handles the 75 multi-fact false rows with no extra labels.
  - Explains itself: "fact X is blamed at 0.8 because page Y says otherwise".
- Cons:
  - Needs reasonable per-fact p_i.
  - Facts that cannot be checked get only the prior, so blame there is weak.
  - Independence is assumed between facts in a row, which is not true when one page lies.
- Rust: port ~20 lines, no crate needed. Python: numpy for labs.
- Fit here: the 75 rows with unknown wrong fact become soft labels (blame weights) for training the per-fact classifier. That is EM with one E step.
- Verdict: ADOPT. Insanity 1/5.

### Multiple-instance learning, standard MIL assumption (algorithm; Dietterich 1997, Maron 1998)
- Link(s): none verified here.
- What it does: a bag is positive (here false) iff at least one instance is positive. Learn instance labels from bag labels.
- Steps: S5, S6
- Pros: the right formal name for the problem, and it lets you say "MIL" in the demo.
- Cons:
  - Nearly all of the 2,402 propositions sit in single-fact rows, which already give instance labels, so MIL only matters for 75 rows.
  - MIL classifiers (mi-SVM, MI-Net) have no Rust implementations.
- Rust: none found; noisy-OR is the practical MIL here.
- Fit here: treat noisy-OR as the MIL instantiation. Skip a separate MIL library.
- Verdict: IDEA-ONLY (as vocabulary for noisy-OR). Insanity 1/5.

### Consistency-based diagnosis, Reiter minimal hitting sets (paper; Reiter, "A theory of diagnosis from first principles", 1987)
- Link(s): unverified (not re-fetched).
- What it does: find minimal sets of components (facts) whose being wrong explains an observed conflict.
- Steps: S5
- Pros: gives a clean "minimal explanation" story for the demo.
- Cons:
  - No scores, only sets; you would add weights anyway.
  - With 2.4 facts per false row on average, enumerating sets adds nothing over ranking.
  - No dedicated Rust crate found.
- Rust: port ~40 lines for tiny rows; or reuse a weighted hitting-set via the ILP/SAT crates.
- Fit here: only useful if rows have more than 4 facts and several are independently suspicious.
- Verdict: IDEA-ONLY. Insanity 2/5.

### Weighted MaxSAT / SAT crates (algorithm and crates)
- Link(s): rustsat 0.7.5 (112k downloads, updated 2026-01-30); splr 0.19.0 (51.6k, updated 2026-08-22); varisat 0.2.2 (7.8M but last updated 2020-09, effectively unmaintained); batsat 0.6.0 (126k, updated 2025-01-20); cadical 0.1.16 bindings (68k, 2025-04-24); rsmaxsat 0.x (1.6k, 2025-01-28, unverified quality). Python: python-sat.
- What it does: encode "row false iff some fact false" plus per-fact evidence as soft clauses, then find the minimum-cost assignment.
- Steps: S5
- Pros: exact, handles interacting constraints (a page that lies makes all of its facts suspect).
- Cons:
  - Heavy for 2,400 independent-ish facts.
  - Weights still need calibrated p_i, so you build the noisy-OR anyway.
  - Cost is learning an encoding, not solving.
- Rust: `rustsat` is the only one with a MaxSAT API; the rest are pure SAT.
- Fit here: only worth it if per-page liar variables create real cross-row coupling. That is a later idea, not for this deadline.
- Verdict: IDEA-ONLY. Insanity 3/5.

### ILP / MIP crates (good_lp, highs, microlp)
- Link(s): good_lp 1.15.3 (4.3M, updated 2026-08-06); highs 2.4.0 (1.2M, 2026-07-09); microlp 0.6.0 (1.7M, 2026-07-27, pure Rust); minilp 0.2.2 abandoned since 2020.
- What it does: general LP/MIP; good_lp is the front end and HiGHS or microlp is the backend.
- Steps: S5, S7
- Pros: the pure-Rust `microlp` backend avoids a C++ build, which matters for the offline 2-CPU container.
- Cons: `highs` needs a C++ toolchain at build time.
- Rust: `good_lp` with the `microlp` feature.
- Fit here: the 1,000-claim pick with five type quotas is a simple knapsack-with-quotas, which greedy solves exactly enough. ILP only adds value if you also want a "no two claims share a fact" constraint.
- Verdict: TRY for S7 if correlated-claims constraints matter, otherwise REJECT. Insanity 2/5.

### Partial-label learning (paper family; Cour et al. 2011, Feng et al. 2020 PRODEN)
- Link(s): unverified.
- What it does: train when each example has a candidate set of labels, one of them correct.
- Steps: S5
- Pros: same shape as "one of these facts is wrong".
- Cons: neural-net era methods, no Rust port; solves a problem noisy-OR already solves in closed form.
- Rust: none.
- Fit here: no.
- Verdict: REJECT. Insanity 4/5.

### Platt scaling and temperature scaling (algorithm; Platt 1999, Guo et al. 2017)
- Link(s): none verified.
- What it does: fit a sigmoid on scores (Platt, 2 parameters) or divide logits by T (temperature, 1 parameter).
- Steps: S6
- Pros: very few parameters, so safe at 1,900 rows and under distribution shift.
- Cons: assumes a sigmoid shape; wrong if the score is non-monotone in true probability.
- Rust: port ~40 lines (Newton on log loss); `argmin` 0.11.0 (5.5M downloads, 2025-09-28) works if you prefer a library. Python: scikit-learn `CalibratedClassifierCV`.
- Fit here: first choice with only 277 false rows. A 2-parameter fit is far more stable than isotonic.
- Verdict: ADOPT (Platt first). Insanity 1/5.

### Isotonic regression / PAV (algorithm; Zadrozny and Elkan 2002)
- Link(s): `pav_regression` 0.7.0 (91k downloads, updated 2026-03-25). Others: `sklears-isotonic` 599 downloads, `isodistrreg` 40 downloads. A crate literally named `isotonic` does not exist.
- What it does: monotone, non-parametric calibration.
- Steps: S6
- Pros: flexible; PAV itself is about 50 lines.
- Cons: needs more data than Platt (overfits with 277 false rows), and produces plateaus that make ties in confidence.
- Rust: `pav_regression`, or port ~50 lines.
- Fit here: use it only if the reliability diagram shows a non-sigmoid shape; compare to Platt with out-of-fold ECE and Brier.
- Verdict: TRY. Insanity 1/5.

### Beta calibration (paper; Kull, Silva Filho, Flach, AISTATS 2017)
- Link(s): unverified here. Python package `betacal` exists (unverified for this session).
- What it does: 3-parameter calibration map, more flexible than Platt and still smooth.
- Steps: S6
- Cons: little tooling; about 50 lines of Rust with logistic regression on `ln(s)` and `-ln(1-s)`.
- Fit here: a good middle ground if Platt underfits and isotonic overfits.
- Verdict: IDEA-ONLY (cheap upgrade). Insanity 1/5.

### Venn-Abers predictors (paper family; Vovk and Petej 2012, Inductive Venn-Abers 2015)
- Link(s): python `ip200/venn-abers` (208 stars, pushed 2026-09-02). arXiv: "Inductive Venn-Abers and related regressors" arXiv 2605.06646 (May 2026, per my search; I matched title to the ID from the API listing and did not open the paper). Rust: no crate found.
- What it does: runs isotonic regression twice (label assumed 0, then 1) to get a probability interval [p0, p1] with a validity guarantee. The width of the interval is an honest uncertainty signal.
- Steps: S6
- Pros: calibrated by construction in the validity sense; the interval width is a natural abstention trigger.
- Cons: still needs isotonic; with sparse data the interval is wide.
- Rust: port ~30 lines on top of PAV.
- Fit here: a good "defensible calibration" talking point. Use the interval width to widen the unsure band.
- Verdict: TRY if time remains. Insanity 2/5.

### Histogram binning (algorithm; Zadrozny and Elkan 2001)
- What it does: map score to the empirical true rate in its bin.
- Steps: S6
- Pros: trivial and transparent; the reliability diagram is the model.
- Cons: bin-edge noise at 1,900 rows; use few bins (5 to 10), or isotonic does it better.
- Rust: port ~20 lines.
- Verdict: IDEA-ONLY as a cross-check on isotonic. Insanity 1/5.

### Classifier calibration benchmarks (paper, 2026)
- Link(s): "Classifier Calibration at Scale: An Empirical Study of Model-Agnostic Post-Hoc Methods", arXiv 2601.19944 (Jan 2026; title confirmed in the API search, the ID attached from the same listing, content not read).
- What it does: compares post-hoc calibrators broadly.
- Steps: S6
- Fit here: supports picking Platt/isotonic/Venn-Abers by out-of-fold data rather than by prior belief. I did not verify its conclusions.
- Verdict: IDEA-ONLY (read the abstract before citing it). Insanity 1/5.

### Conformal prediction and selective classification (MAPIE, crepes)
- Link(s): MAPIE (1,654 stars, pushed 2026-10-28); `crepes` GitHub repo checked was valeman/crepes (1 star, last push 2021-11), which is probably not the main repo, so treat crepes status as unverified. Rust: `conformal-prediction` 2.0.0 (495 downloads, 2025-11-15), too obscure to trust; port is simple.
- What it does: split-conformal gives prediction sets (true, false, both), where "both" is a natural abstain.
- Steps: S6
- Pros: finite-sample coverage, no distribution assumptions beyond exchangeability.
- Cons: exchangeability breaks on unseen subjects at eval; calibrate by page groups, not rows.
- Rust: port ~30 lines (quantile of nonconformity scores).
- Fit here: use split-conformal with a page-grouped calibration split to decide the unsure band: "unsure" when the set has both labels.
- Verdict: TRY. Insanity 2/5.

### Conformal Risk Control and Learn-then-Test (papers, 2021 and 2022)
- Link(s): "Conformal Risk Control" arXiv 2208.02814; "Distribution-Free, Risk-Controlling Prediction Sets" arXiv 2101.02703 (titles confirmed). Learn then Test: GitHub `aangelopoulos/ltt` (74 stars, pushed 2024-11-17).
- What it does: choose a threshold so that expected loss (e.g., error rate among accepted rows) is bounded at level alpha with a stated guarantee.
- Steps: S6, S7
- Pros: lets you say "we chose the confidence cut so the error among labelled rows is at most X with probability Y", which speaks directly to the 15% self-evaluation score.
- Cons: the guarantee is only as good as exchangeability between practice and eval.
- Rust: port ~25 lines (threshold sweep with Hoeffding or Clopper-Pearson bound).
- Fit here: use for the unsure threshold and for the claim-confidence floor.
- Verdict: TRY. Insanity 2/5.

### Conformal selection (paper; Jin and Candes 2023, and 2026 follow-ups)
- Link(s): "Selection by Prediction with Conformal p-values", arXiv 2210.01408 (title confirmed). Follow-ups seen in the API search: "Beyond Fixed False Discovery Rates: Post-Hoc Conformal Selection with E-Variables" (arXiv 2604.11305, April 2026) and "Multivariate Conformal Selection" (no ID retrieved). I read only titles, not content. Reference code repo not found under the guessed name.
- What it does: turns a score into conformal p-values per candidate and applies Benjamini-Hochberg so that the expected FDR among selected items is at most alpha.
- Steps: S7
- Pros: the principled answer to "pick items that are all true with an FDR guarantee".
- Cons:
  - Controls expected FDR, not "all 1,000 true"; with 1,000 picks and a 1% FDR you still expect about 10 wrong.
  - Needs a calibration set from the same distribution as the candidates, and BH needs the p-values to be roughly independent or PRDS.
  - Correlated claims (many from one fact) break that assumption.
- Rust: port ~40 lines (rank, p-value, BH step-up).
- Fit here: generate far more than 1,000 candidates, keep the 1,000 with the best conformal p-values per type. A strong demo story but a modest accuracy gain over plain calibrated ranking.
- Verdict: TRY (as framing on top of greedy). Insanity 3/5.

### Claim selection under correlated errors (design idea)
- What it does: group claims by the root fact(s) they rest on, cap how many claims share one fact, and penalise by fact reliability: score = Π P(fact_i true) over the facts used.
- Steps: S7
- Pros: one wrong fact would otherwise sink many claims at once; the cap bounds that loss.
- Cons: fewer claims per reliable fact reduces diversity, which is exactly what the type quotas want anyway.
- Rust: port ~30 lines.
- Verdict: ADOPT. Insanity 2/5.

### Gradient boosting in Rust
- Link(s):
  - `lightgbm3` 1.0.11 (186k downloads, updated 2026-09-08), bindings that need a C++ build and `libgomp`.
  - `lightgbm` 0.2.3 (updated 2021), `xgboost` 0.1.4 (2019), `catboost-rs` 0.1.8 (2022): all stale.
  - `forust`: the crate name on crates.io is a Procfile tool (3k downloads, 2016), not the GBM; the real project (`forust-ml`) I did not confirm. Treat as unverified.
  - `perpetual` 3.0.0-rc.2 (56k downloads, updated 2026-10-24, release candidate; GitHub perpetual-ml/perpetual), a pure-Rust GBM that claims no hyperparameter tuning.
  - `gbdt` 0.1.3 (90k, 2024-01-24), pure Rust, stale.
  - `smartcore` 0.7.0 (587k, 2026-10-26) and `linfa` 0.8.1 (2.0M, 2025-12-23).
- What it does: non-linear fusion of evidence features.
- Steps: S6
- Pros: captures interactions (e.g., "volatile attribute and old page and low source reliability").
- Cons:
  - With 277 false rows, a boosted model can overfit.
  - A C++ bindings dependency makes the offline build brittle.
  - `perpetual` is an RC.
  - Explanations are harder.
- Rust: `perpetual` (pure Rust) is the first to try; fall back to `lightgbm3` only if the offline build tolerates C++. Python for labs: lightgbm.
- Fit here: only after logistic regression is working and measured; keep it only if it beats LR by a clear out-of-fold margin.
- Verdict: TRY (perpetual or lightgbm3). Insanity 3/5.

### Logistic regression (linfa-logistic, smartcore)
- Link(s): `linfa-logistic` 0.8.1 (207k downloads, updated 2025-12-23); `smartcore` 0.7.0.
- What it does: linear fusion with a calibrated-ish probability output.
- Steps: S6, S8
- Pros: per-feature contributions are the explanation (coefficient times value); stable at small n; outputs are already near-calibrated.
- Cons: no interactions unless you add them by hand.
- Rust: `linfa-logistic`, or hand-rolled IRLS about 60 lines to avoid the ndarray/BLAS dependency.
- Fit here: the primary model. Add a few hand-built interaction features instead of a tree model.
- Verdict: ADOPT. Insanity 1/5.

### Snorkel-style label model (paper and library; Ratner et al. 2017/2019)
- Link(s): snorkel-team/snorkel (6,025 stars, pushed 2026-10-13).
- What it does: combines noisy labelling functions without labels by estimating each function's accuracy.
- Steps: S2, S6
- Pros: principled way to combine heuristic detectors (a page contradicts, a source is unreliable, a value outlier) when labelled data is scarce, and it can use the 90% unlabelled eval rows.
- Cons: assumes conditionally independent functions; no Rust port; with 1,900 labels, supervised LR is probably better.
- Rust: port ~100 lines (EM over function accuracies).
- Fit here: only as a weak-supervision step to exploit unlabelled rows; not before LR is done.
- Verdict: IDEA-ONLY. Insanity 3/5.

### Group k-fold by page (evaluation practice)
- What it does: keeps all rows of one page in the same fold so that calibration and metrics are not inflated by page-level leakage; where subjects drive generalisation, group by subject too.
- Steps: S6
- Pros: gives an honest ECE/Brier estimate and honest calibration.
- Rust: port ~15 lines. Python: sklearn `GroupKFold`.
- Fit here: required, because at eval the subjects and pages are unseen.
- Verdict: ADOPT. Insanity 1/5.

### Mapping score to [0.5, 1] confidence and the unsure band (design)
- What it does: calibrated p = P(true). Predict true if p >= 0.5, confidence = max(p, 1-p). Declare unsure when confidence < tau, with tau chosen on out-of-fold data (via conformal/LTT above) to maximise the expected score under whatever metric is guessed.
- Cons: the label scoring metric is unpublished, so tau is a guess; reward-for-unsure versus penalty-for-wrong is unknown.
- Fit here: with 83% true, a trivial "always true" gets 83% accuracy, so judge calibration with Brier and per-class recall on false rows, not accuracy. Do not let a 0.5 floor flatter the numbers: report ECE on the final [0.5, 1] confidence.
- Verdict: ADOPT. Insanity 1/5.

### Provenance semirings (paper; Green, Karvounarakis, Tannen, PODS 2007)
- Link(s): unverified here (not fetched).
- What it does: annotates query results with a polynomial that says which source tuples produced them (why-provenance is the set of witnesses, how-provenance the polynomial).
- Steps: S8
- Pros: a direct vocabulary for "this verdict rests on facts A and B from pages P1, P2".
- Cons: a full semiring engine is far more than needed.
- Rust: port ~30 lines if each verdict carries `Vec<(fact_id, page_id, polarity)>`; that is why-provenance already.
- Fit here: record witness lists and call them why-provenance in the demo.
- Verdict: ADOPT (as plain witness lists). Insanity 1/5.

### Datalog engines with provenance (Soufflé, Scallop, ascent, crepe, datafrog)
- Link(s): Soufflé (1,191 stars, pushed 2026-10-02); Scallop (scallop-lang/scallop, 520 stars, pushed 2026-06-26, supports provenance semirings, Python/Rust); Rust crates `ascent` 0.8.1 (698k downloads, updated 2026-08-29), `crepe` 0.2.0 (838k, 2025-12-14), `datafrog` 2.0.1 (5.1M, 2026-10-12). The crate called `scallop` on crates.io is an unrelated "wrapper for bash" and is not the Scallop language.
- What it does: express rules like "fact holds at date d if a later page doesn't override it" declaratively.
- Steps: S1, S3, S8
- Pros: rules double as the explanation; ascent has BYODS (custom data structures) and lattices.
- Cons: Datalog is awkward for date-interval arithmetic and numeric tolerance; adds compile time and learning.
- Fit here: the as-of and change timeline logic is a plain sorted-vector scan; do not adopt a Datalog engine.
- Verdict: REJECT for this deadline (ascent is the one to look at if later desired). Insanity 3/5.

### Argumentation frameworks (Dung 1995; bipolar frameworks)
- Link(s): unverified (no Rust implementation found).
- What it does: models attack and support relations between arguments and computes accepted sets.
- Steps: S2, S8
- Pros: matches "supporting vs contradicting evidence" visually.
- Cons: the semantics (grounded, preferred) add nothing over weighted evidence; no Rust tooling.
- Rust: port ~60 lines for grounded semantics via `petgraph` (579M downloads, 0.8.3).
- Fit here: draw the evidence graph in the UI from the witness lists instead.
- Verdict: IDEA-ONLY. Insanity 3/5.

### SHAP / TreeSHAP in Rust
- Link(s): `treeshap` 0.1.0 (21 downloads, updated 2026-07-23; repo github.com/zabrodschiipavel-sketch/treeshap, which is a single-author unknown repo); `shap` crate 0.1.0 (2.2k downloads, 2024) not verified to be the ML library. Python: shap (25,836 stars, pushed 2026-10-26).
- What it does: attributes a tree model's prediction to features.
- Steps: S8
- Cons: `treeshap` is new and untested, and its compatibility with `perpetual` or `lightgbm3` trees is unverified. You would need to read it fully before relying on it.
- Fit here: with logistic regression the exact attribution is coefficient times feature value, which needs no crate.
- Verdict: REJECT (use LR contributions; reconsider if a tree model wins). Insanity 3/5.

### Static embeddings: model2vec / model2vec-rs / fastText
- Link(s): `model2vec-rs` 0.3.0 (329k downloads, updated 2026-09-19; MinishLab/model2vec-rs, 222 stars, pushed 2026-10-28); `fasttext` crate 0.8.0 (3.3M downloads, 2026-04-18, pure-Rust reimplementation).
- What it does: maps a new attribute name to the nearest known attribute names and borrows priors such as volatility or lie rate.
- Steps: S2, S4, S6
- Pros: could help for unseen attribute names.
- Cons:
  - It needs a pretrained model file bundled into the container (size and licence unchecked).
  - A learned embedding is a neural model; model2vec is distilled from a transformer, so a jury may read it as "LLM-derived" despite being static. The rules ban a generative model at runtime, and the optics are risky.
  - Attribute vocabularies in a synthetic company are probably small and regular; a handful of token-overlap rules (character n-gram Jaccard) would match most names.
- Rust: `model2vec-rs`, or character n-gram Jaccard in about 20 lines.
- Fit here: prefer a transparent n-gram or token similarity over embeddings; it is just as defensible and explainable.
- Verdict: REJECT embeddings, ADOPT n-gram similarity if unseen attributes show up. Insanity 1/5 (n-gram) / 3/5 (embeddings).

### ECE, Brier, reliability diagrams (metrics)
- What it does: ECE (binned gap between confidence and accuracy), Brier (squared error of probabilities), reliability diagram (the plot).
- Steps: S6
- Rust: port ~25 lines. The `ml-metrics` crate I searched for does not exist.
- Fit here: report Brier plus ECE with a bin count stated (10 bins on 1,900 rows is noisy, so show bootstrap intervals). The reliability plot is also a good demo slide for the 15% self-evaluation criterion.
- Verdict: ADOPT. Insanity 1/5.

---

## Not found / unverified
- A Rust crate for Venn-Abers, conformal selection, or calibration beyond `pav_regression`; crates named `isotonic`, `venn-abers`, `conformal`, `noisy-or`, `hitting-set`, `maxsat` and `calibration` do not exist (`rsmaxsat` and `solow-calibration` exist but I did not inspect them).
- The real `forust` GBM crate; `forust` on crates.io is an unrelated Procfile tool.
- Reference code for conformal selection (the repo name I guessed returned 404).
- Whether `treeshap` works with `perpetual` or `lightgbm3` models.
- Paper content for arXiv 2601.19944, 2605.06646 and 2604.11305: only titles, dates and IDs from arXiv API searches. I did not read them, so do not cite their findings.
- Original sources for Reiter 1987, Green/Karvounarakis/Tannen 2007, Dung 1995, Platt 1999, Kull 2017 and the MIL papers: cited from memory, links not fetched.
- The crepes repo's maintenance status (the repo I found is not the main one) and the exact `betacal` package state.
- Any 2024-2026 work on blame assignment specifically for multi-fact rows; I did not find any dedicated work, so the noisy-OR recommendation is my own reasoning, not a published result.
