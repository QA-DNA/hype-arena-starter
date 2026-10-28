# Truth discovery, conflict resolution and source reliability

Raw report from the 2026-10-28 knowledge base research, kept as written by the worker so nothing is lost. The curated version, with verdicts reconciled against the contract and the measured results, is [the knowledge base research](../knowledge-base.md).

- **Author:** W1, Claude Sonnet 5.5 research worker.
- **Scope:** S2 conflicts and source reliability, S3 change over time, S6 labelling.
- **Tools:** free tools only (WebSearch, WebFetch, GitHub, crates.io, arXiv); no paid research service.
- **Citations:** Citations the worker marked "not verified" were checked afterwards where possible; the verified URLs are listed in [the notes index](README.md#verified-citations).

## TLDR
- **Build a small Rust model of our own, not a ported classic.** No Rust crate for truth discovery, Dawid-Skene or label aggregation exists (crates.io searches were empty or noise). The core of any EM-style method is 150-300 lines of Rust with no dependencies.
- **Our setting differs from classic truth discovery.** Pages are time-stamped, values have lifespans, ~10% of rows carry labels, and almost every false fact has its key stated correctly elsewhere. That favours a temporal, anchored, per-page accuracy model: an Accu-style EM with a per-key value timeline, seeded and clamped by labelled rows.
- **Page reliability comes mainly from labelled rows.** With ~1,900 labelled rows over the pages, each page has some anchors. Use them as a Beta prior on page accuracy and let EM refine it on the unlabelled votes (the SLiMFast / Snorkel-style move).
- **A lie can look like a stale value, so treat staleness separately from falsehood.** A claim that matches an earlier value on the timeline but is dated after the change is stale-or-lie; a value matching no timeline entry is a plain lie; a claim with no evidence at its date is "unsure". Model copying and staleness explicitly instead of adding more voting rounds.
- **Calibrate separately.** EM posteriors are over-confident. Fit isotonic or Platt calibration on held-out labelled rows, then clip to [0.5, 1] (a symmetric true/false posterior maps to max(p, 1-p)).

## Entries

### Majority vote (algorithm, baseline)
- Link(s): none needed.
- What it does: the value with the most supporting sources wins.
- Steps: S1, S2.
- Pros: 5 lines; strong when every key is stated 2-12 times.
- Cons: ignores time (an old value gets the same votes as the current one) and ignores page quality; ties are common at 2 claims.
- Rust: trivial, ~20 lines. Python: pandas.
- Fit here: use it only as the floor to beat. Make it time-windowed: vote only among claims valid at the as-of date.
- Verdict: ADOPT as a baseline and fallback. Insanity 1.

### TruthFinder (Yin, Han, Yu, TKDE 2008)
- Link(s): not verified (survey covers it, https://arxiv.org/abs/1505.02463).
- What it does: iterates source trustworthiness against fact confidence, with an implication term between similar facts, damped through a logistic.
- Steps: S2, S4.
- Pros: the "similar values support each other" idea is relevant for inexact values; tiny to implement.
- Cons: confidences saturate near 1 and are badly calibrated; the damping factor needs tuning; no time model.
- Rust: port ~100 lines. Python: `truthdiscovery` implements it.
- Fit here: borrow the implication term only for S4 (numeric closeness between claims).
- Verdict: IDEA-ONLY. Insanity 1.

### Sums, Average-Log, Investment, PooledInvestment (Pasternack & Roth, COLING 2010)
- Link(s): not verified (survey).
- What it does: HITS-style iteration of source trust against claim belief, with variants of the trust normalisation.
- Steps: S2.
- Pros: simple and fast.
- Cons: scores are unnormalised and uncalibrated; no probabilistic semantics; no anchors.
- Rust: ~60 lines each. Python: `truthdiscovery` (verified: pypi 1.0.4, GitHub joesingo/truthdiscovery, 7 stars, last push 2023-03-29).
- Fit here: a quick lab comparison only.
- Verdict: REJECT for production (use Accu). Insanity 1.

### ACCU / AccuSim / AccuCopy and copy detection (Dong, Berti-Equille, Srivastava, VLDB 2009 "Integrating conflicting data: the role of source dependence")
- Link(s): not verified directly; the survey and arXiv 1503.00302 (verified title: "From Data Fusion to Knowledge Fusion", Dong et al., VLDB 2014) cover the lineage.
- What it does: Bayesian per-source accuracy. A value's vote count is the sum over its sources of log(n·A/(1-A)), where A is source accuracy and n the number of false values. AccuCopy discounts votes from sources that copy one another.
- Steps: S2, S6.
- Pros: probabilistic and principled; produces a posterior per claim; handles the "false value is rare, true is repeated" case; copy detection catches mirrored pages.
- Cons: assumes one static truth per key (needs the temporal extension); copy detection is O(pairs) and noisy with few shared keys.
- Rust: port ~200 lines for Accu, +150 for copy. Python: none maintained; a lab version is ~80 lines of numpy.
- Fit here: the best starting skeleton. Run it per (key, time window) with A set per page. Drop AccuCopy unless page pairs show clone-like agreement.
- Verdict: ADOPT (Accu core), TRY (copy). Insanity 2.

### Dynamic-world truth discovery and copy detection (Dong, Berti-Equille, Srivastava, VLDB 2009 "Truth discovery and copying detection in a dynamic world")
- Link(s): not verified.
- What it does: models each value's lifespan; scores sources by coverage, exactness and freshness (CEF); a Hidden Markov Model decides the truth path and copy relations over time.
- Steps: S1, S2, S3.
- Pros: matches our problem exactly (value transitions, stale sources, a source that lags counts as less fresh, not necessarily a liar).
- Cons: the full HMM with copy detection is heavy; needs enough history per key.
- Rust: a simplified version (per-key sequence decoding, ~250 lines) is feasible.
- Fit here: the conceptual template for "stale versus lie". Implement the lifespan idea without the copy HMM.
- Verdict: ADOPT the idea (simplified). Insanity 3.

### DynaTD / "On the discovery of evolving truth" (Li et al., KDD 2015)
- Link(s): not verified (DOI not checked).
- What it does: truth-discovery loss with a source-reliability term that evolves smoothly across time steps; truths change per step.
- Steps: S2, S3.
- Pros: handles reliability drift; streaming-friendly.
- Cons: designed for continuous sensor-style streams; our "pages" are each stamped at one date.
- Rust: ~150 lines.
- Fit here: only if page reliability visibly varies with page date (check on practice data).
- Verdict: IDEA-ONLY. Insanity 3.

### Pal et al., "Information integration over time in unreliable and uncertain environments" (WWW 2012)
- Link(s): not verified.
- What it does: fuses time-varying facts from sources of unknown reliability, with Bayesian temporal updates.
- Steps: S1, S3.
- Pros: the as-of query is natural in its formulation.
- Cons: a heavier model than we can validate in the time left.
- Rust: ~300 lines.
- Fit here: reference reading for how to represent a timeline.
- Verdict: IDEA-ONLY. Insanity 4.

### CRH (Li et al., SIGMOD 2014, "Resolving conflicts in heterogeneous data by truth discovery and source reliability estimation")
- Link(s): not verified; one GitHub reimplementation exists but is minor (kesavsivakumar/Resolving-Conflicts-in-Heterogeneous-Data--CRH_Framework, 4 stars, 2020).
- What it does: alternating minimisation: source weights by -log of normalised loss; truths by weighted vote (categorical) or weighted median/mean (numeric).
- Steps: S2, S4.
- Pros: handles typed values (we have quantity, money, date, percent); the loss per type is a clean place to put S4 tolerance.
- Cons: weights aren't probabilities; calibration is on us.
- Rust: ~200 lines.
- Fit here: the typed-loss idea is the most useful part for inexact values.
- Verdict: TRY (borrow the per-type loss). Insanity 2.

### CATD (Li et al., VLDB 2014, long-tail confidence-aware)
- Link(s): not verified.
- What it does: confidence interval on source weights so sources with few claims are not over- or under-trusted.
- Steps: S2.
- Pros: directly addresses pages with only a handful of rows.
- Cons: chi-squared interval needs enough data to matter.
- Rust: ~30 extra lines on CRH.
- Fit here: the idea is equivalent to a Beta prior on page accuracy; do it the Bayesian way.
- Verdict: IDEA-ONLY. Insanity 1.

### GTM and KDEm (numeric truth models)
- Link(s): not verified.
- What it does: Gaussian (GTM) or kernel-density (KDEm) estimate of the numeric truth with per-source variance.
- Steps: S4.
- Pros: gives a smooth score for numerically close values.
- Cons: our values are mostly discrete step functions; the noise isn't Gaussian.
- Rust: ~60 lines.
- Fit here: mostly irrelevant; a tolerance band per unit is simpler.
- Verdict: REJECT. Insanity 2.

### LTM, Latent Truth Model (Zhao et al., VLDB 2012)
- Link(s): not verified.
- What it does: collapsed Gibbs sampling over per-source sensitivity and specificity, for multi-valued attributes.
- Steps: S2, S5.
- Pros: separating false-positive from false-negative behaviour fits "lies versus omissions"; handles multi-truth keys (relation lists).
- Cons: Gibbs sampling is slower and fiddly; hard to calibrate.
- Rust: ~250 lines.
- Fit here: only if some attributes are multi-valued sets; otherwise skip.
- Verdict: IDEA-ONLY. Insanity 3.

### 3-Estimates, SimpleLCA, GuessLCA
- Link(s): not verified.
- What it does: also model claim "difficulty" (3-Estimates) or a latent credibility per assertion (LCA).
- Steps: S2.
- Pros: the difficulty term captures that some keys are inherently ambiguous.
- Cons: more parameters than data supports at 2-12 claims per key.
- Rust: ~150 lines.
- Fit here: little.
- Verdict: REJECT. Insanity 2.

### Dawid-Skene, GLAD, MACE (crowd aggregation)
- Link(s): https://github.com/Toloka/crowd-kit (verified: 255 stars, last push 2025-12-01, pypi crowd-kit 1.4.2).
- What it does: EM over per-annotator confusion matrices (DS), item difficulty (GLAD), spammer detection (MACE).
- Steps: S2, S6.
- Pros: a maintained Python implementation for labs; the binary confusion matrix (a page's sensitivity and specificity on true/false rows) is a direct model of "some pages lie".
- Cons: assumes every annotator labels every item with the same label space; our "labels" are claims about different values, so we must map claims to "supports value v".
- Rust: DS port ~120 lines. Python: crowd-kit for lab comparison.
- Fit here: use crowd-kit in the lab to sanity-check a Rust EM on the practice set.
- Verdict: TRY (as a lab baseline). Insanity 2.

### Semi-supervised truth discovery (Yin & Tan, WWW 2011)
- Link(s): not verified.
- What it does: graph-based propagation where labelled truths constrain the iteration.
- Steps: S2, S6.
- Pros: shows that even a few labels sharpen source trust.
- Cons: older graph formulation; the same effect is simpler in a Beta-prior EM.
- Rust: ~150 lines.
- Fit here: justification for anchoring, not a thing to port.
- Verdict: IDEA-ONLY. Insanity 2.

### SLiMFast (Rekatsinas et al., SIGMOD 2017)
- Link(s): not verified. The GitHub hit "HubSpot/SlimFast" is an unrelated project; do not confuse it.
- What it does: logistic regression with source features, trained on ground-truth labels when plentiful and EM when scarce, with guarantees on error.
- Steps: S2, S6.
- Pros: closest in spirit to ours (labels as anchors, features per source, discriminative); gives calibrated-looking probabilities from logistic output.
- Cons: needs useful source features; here the only per-page features are derived (labelled-row accuracy, date, row count, fraction of its claims contradicted).
- Rust: logistic regression is ~80 lines (or the `linfa-logistic` crate, not checked here).
- Fit here: build a final stacker: features per row (page accuracy, vote margin, timeline-match type, staleness distance, number of propositions) into a logistic model trained on the ~1,900 labelled rows.
- Verdict: ADOPT (as the final calibrated stacker). Insanity 2.

### Snorkel / data programming (Ratner et al., NeurIPS 2016)
- Link(s): https://github.com/snorkel-team/snorkel (verified: 6,025 stars, pushed 2026-10-13, pypi 0.10.0); skweak (pypi 0.3.3, Norwegian Computing Center).
- What it does: learns labelling-function accuracies and correlations without ground truth, then outputs probabilistic labels.
- Steps: S2, S6.
- Pros: the analogy is exact: labelling functions are our independent signals (timeline match, page accuracy, cross-page agreement); matrix-completion label model is closed form.
- Cons: the package is heavy and Python-only; its model assumes conditionally independent functions.
- Rust: port ~150 lines for a simplified generative label model.
- Fit here: as a framework for combining 4-6 heuristic signals. Prefer the logistic stacker (SLiMFast entry) because we do have labels.
- Verdict: IDEA-ONLY. Insanity 3.

### Knowledge-Based Trust (Dong et al., VLDB 2015)
- Link(s): not verified directly; see arXiv 1503.00302 for the same group's fusion work.
- What it does: a multi-layer model separating extraction errors from source errors, estimating page-level trust from the correctness of its extracted facts.
- Steps: S2, S5.
- Pros: the two-layer idea (is the proposition mis-normalised, versus does the page assert something wrong) matters because our rows were machine-normalised.
- Cons: full model is large; we have no extractor-confidence signal.
- Rust: ~300 lines in full.
- Fit here: only the idea: keep a small "extraction noise" term so a normalisation error does not condemn a page.
- Verdict: IDEA-ONLY. Insanity 4.

### Knowledge Vault fusion / "From Data Fusion to Knowledge Fusion"
- Link(s): https://arxiv.org/abs/1503.00302 (verified title).
- What it does: evaluates fusion methods (vote, Accu variants, Pooled) on extracted triples at scale; the finding is that accuracy modelling plus confidence from extractors gives the largest gain, and calibration needs a separate step.
- Steps: S2, S6.
- Pros: an empirical case for calibration as its own stage.
- Cons: web scale, different data.
- Rust: not applicable.
- Fit here: supports the plan above.
- Verdict: IDEA-ONLY. Insanity 1.

### Li et al., "A survey on truth discovery" (SIGKDD Explorations 2016)
- Link(s): https://arxiv.org/abs/1505.02463 (verified title).
- What it does: taxonomy of methods, input/output types, source-reliability assumptions, and the datasets used.
- Steps: all.
- Pros: one place to look up any method above.
- Cons: ends 2015.
- Verdict: ADOPT as the reference to read. Insanity 1.

### Waguih & Berti-Equille, "Truth discovery algorithms: an experimental evaluation" (2014)
- Link(s): not verified (arXiv id not checked). Related code: qcri/DAFNA-EA on GitHub (verified: 11 stars, last push 2018-08-26, unmaintained).
- What it does: compares twelve algorithms on real and synthetic data.
- Steps: S2.
- Pros: finding to remember: on data where one value dominates, simple methods and Accu-type models perform about as well as the complex ones; the complex ones lose on sparse data.
- Cons: stale code.
- Verdict: IDEA-ONLY (read for evidence that complexity does not pay). Insanity 1.

### 2025 survey: "A Survey on Truth Discovery: Concepts, Methods, Applications, and Opportunities" (Wang, Zhang, Sheng, Li, Sun, Cai, et al., 2025)
- Link(s): listed on bibbase and ResearchGate (search results only; venue and arXiv id not verified).
- What it does: updates the 2016 taxonomy, including deep and LLM-based approaches.
- Steps: all.
- Pros: the newest overview located.
- Cons: not read; claims here come from the title only.
- Verdict: IDEA-ONLY (skim if time). Insanity 1.

### LLM-era work ("Re-Search for the Truth", arXiv 2403.09747)
- Link(s): https://arxiv.org/abs/2403.09747 (title seen in search; content not read).
- What it does: multi-round retrieval-augmented fact checking with LLMs.
- Steps: none usable.
- Cons: the runtime may not be an LLM.
- Verdict: REJECT. Insanity 5.

### Python `truthdiscovery` (Joe Singleton)
- Link(s): https://github.com/joesingo/truthdiscovery (verified: 7 stars, last push 2023-03-29; pypi 1.0.4).
- What it does: Sums, Average-Log, Investment, PooledInvestment, TruthFinder, Cosine, 2-/3-Estimates, majority vote, with a CLI.
- Steps: S2.
- Pros: one install gives eight baselines to compare on practice data.
- Cons: unmaintained; categorical only; no time.
- Verdict: TRY for the lab only. Insanity 1.

### Rust crates
- Link(s): crates.io searches for "truth discovery", "dawid skene", "label aggregation", "crowdsourcing aggregation" and "data fusion" returned no relevant crate. The "dawid skene" hits were `quietset` (dataset filtering by label stability, 436 downloads, 2026-07-26) and `ljos-consensus` (DeGroot / Friedkin-Johnsen over a trust graph, 298 downloads, 2026-10-26), both unrelated to truth discovery and tiny. A GitHub search for "dawid-skene language:rust" returned nothing.
- Verdict: write it ourselves. About 200 lines for a temporal Accu-EM plus 80 for logistic calibration; `ndarray` is optional.

## Recommended design for this problem (S1-S6)
1. **Per-key timeline.** For each (subject, attribute) key, order the claims by date and form candidate segments: a value valid from the earliest claim date to the day before the next different value is seen (S1, S3).
2. **Per-page accuracy.** Accu-style EM: page accuracy A_p ~ Beta(prior from labelled rows); labelled rows are clamped to their label, unlabelled rows contribute soft votes. Cap iterations at ~20; it converges in milliseconds at 20,000 rows (S2).
3. **Stale versus lie.** Add a feature "claim equals a prior timeline value and the claim date is after the change date" (stale-or-lie) and "claim equals no timeline value" (lie) (S3, S5).
4. **Multi-fact rows.** A row is false if any proposition is false, so row score = product of per-proposition truth probabilities. For blame, the least-supported proposition is the candidate; labelled false rows then also lower the weight of the page (S5).
5. **Unsure.** Predict "unsure" when no claim in the key's timeline covers the row's date, or when the key has no other source (S6).
6. **Calibrate.** Logistic stacker (SLiMFast style) over these features, then isotonic calibration on held-out labelled rows; report max(p, 1-p) clipped to [0.5, 1] (S6).
7. **Claim generation** takes only timeline values with margin above a threshold and at least two independent sources (S7). Explanations cite the supporting pages (S8).

Do not skip an honest held-out check: practice has 1,897 labelled rows, so split by page or by key (not by row) to avoid leakage when you measure calibration.

## Not found / unverified
- Semantic Scholar was rate-limited (429) and arXiv's query API returned empty, so I could not confirm venue, DOI or page numbers for: TruthFinder, Pasternack & Roth, ACCU/AccuCopy, the dynamic-world paper, DynaTD, Pal et al., CRH, CATD, GTM/KDEm, LTM, 3-Estimates/LCA, Yin & Tan, SLiMFast, Knowledge-Based Trust, Waguih & Berti-Equille. Descriptions above are from my memory of the literature; treat the bibliographic details as unconfirmed.
- Verified: arXiv 1505.02463 (survey title), arXiv 1503.00302 (title), crowd-kit repo and pypi, `truthdiscovery` repo and pypi, Snorkel repo and pypi, skweak pypi, qcri/DAFNA-EA repo.
- Not found: any maintained GitHub repo for DynaTD, LTM or SLiMFast (the "SlimFast" hit is HubSpot's, unrelated); any 2024-2026 truth-discovery method I could read (only the 2025 survey title and an LLM paper title were seen); any Rust crate for truth discovery or label aggregation; AllegatorTrack (not searched beyond DAFNA).
- Not checked: whether `linfa` / `linfa-logistic` on crates.io is current, and graph-neural or multi-truth newer methods.
