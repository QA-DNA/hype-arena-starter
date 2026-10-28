# R3: MMR improvements, variants and untested ideas for selecting k claims under correlated failure

Scope note. Time-boxed web pass (about a dozen searches). Search snippets and abstracts were read; full papers were NOT read, so details beyond abstracts are marked "unverified". "DERIVATION" marks my own math; "EXTRAPOLATION" marks transfer to VERIDYCT. Nothing here is a claim about the hidden scoring formula.

## Executive summary

1. Under pure linear precision (score = mean of correct claims) the expected score of a size-k set is sum p_i / k, whatever the correlation. Diversification changes only variance. Correlation is irrelevant to the mean. So MMR-style diversification cannot raise expected precision; the PRP (rank by p) is optimal there. (DERIVATION, section 1.2; the IR literature states the same: Wang & Zhu frame diversification as risk reduction, Chen & Karger show PRP is optimal only for the expected-count objective.)
2. Diversification raises EXPECTED score only if the score is nonlinear in the number correct: thresholds, concave utility, per-base-fact penalties, coverage/at-least-one terms, or a duplicate penalty. Chen & Karger (SIGIR 2006) is the cleanest published statement: change the objective to "at least one relevant" (k-call) and PRP is no longer optimal; the greedy that conditions on already-chosen items beats PRP.
3. Because the scoring formula is unknown, the sound plan is a robust one: pick the set that does well across a menu of plausible scorers (SATURATE / maximin, or a mean-minus-risk compromise). The top candidate design is a type-quota, base-fact-capped, p-ordered greedy with a small structural redundancy penalty (all with lambda near 1). It is close to PRP, loses almost nothing under precision, and gains under every nonlinear hypothesis.
4. Best-supported algorithmic spine: greedy on a monotone-submodular objective under a partition matroid (1/2 guarantee, simple, fast), with lazy/stochastic greedy for scale. At k=1000 and 10^5 candidates, plain lazy greedy on 2 CPUs is fine; no streaming or distributed machinery is needed.
5. Literature gaps: I found no published work on dependency-aware MMR using shared source facts, on confidence-shaped lambda, or on Monte Carlo tuning of lambda under correlated failures. These are UNTESTED in section 8.

---

## 1. Risk-aware selection

### 1.1 Literature (empirical/theoretical findings from sources)

- Probability Ranking Principle (Robertson 1977): ranking by probability of relevance maximizes expected effectiveness when relevances are independent. Failure cases (multiple intents, correlated documents) are listed in a course summary of Wang & Zhu: https://www.cs.umd.edu/class/fall2010/cmsc828e/jian2.pdf
- Chen & Karger, "Less is more", SIGIR 2006: when only one (or a few) relevant item is needed, maximizing expected number relevant (what PRP does) can lower the chance of getting any. They optimize "1-call" (probability of at least one relevant) and a greedy that conditions each pick on the previously selected items beat the PRP baseline, with the largest gains on difficult queries. Abstract-level only; k-call details unverified. https://ir.webis.de/anthology/2006.sigirconf_conference-2006.57/
- Wang & Zhu, "Portfolio theory of information retrieval", SIGIR 2009: rank list as portfolio; objective is expected relevance minus b times variance (mean-variance); derives a greedy rule that generalizes PRP; diversification motivated as risk reduction; reported gains over PRP and MMR on ad hoc and subtopic retrieval. https://ir.webis.de/anthology/2009.sigirconf_conference-2009.16 ; summary https://liner.com/review/portfolio-theory-information-retrieval
- Collins-Thompson, robust query models by convex optimization, NIPS 2008 and CIKM 2009: choose terms with high expected relevance and low risk, using portfolio-style covariance; risk-reward curves; large reduction in failures while keeping average gain. https://papers.neurips.cc/paper/2008/hash/e0cf1f47118daebc5b16269099ad7347-Abstract.html ; https://ir.webis.de/anthology/2009.cikm_conference-2009.88
- Dincer, Macdonald, Ounis, TRisk/URisk, SIGIR 2014: risk-reward measures for evaluating systems relative to a baseline (downside weighted by alpha); TRisk is a linear transform of the t statistic. Follow-ups ZRisk/GeoRisk (2016) use multiple baselines and are also used for risk-averse learning to rank. https://www.dcs.gla.ac.uk/~craigm/publications/dincer2014hypothesis.pdf ; https://archive.cps-vo.org/node/39077
- CVaR-style selection: I did not find an IR paper that applies CVaR to set selection (see section 9). CVaR is standard in finance and stochastic programming; transfer is EXTRAPOLATION.

### 1.2 Math for our case (DERIVATION)

Set S of size k. X_i = 1 if claim i is correct. Base facts B_j are independent Bernoulli(q_j); claim i depends on set D(i) of base facts and is correct iff all D(i) are correct (plus possibly its own derivation noise). Then p_i = prod_{j in D(i)} q_j (times own reliability), and Cov(X_i, X_l) = prod_{j in D(i) U D(l)} q_j - p_i p_l >= 0, positive exactly when D(i) and D(l) intersect.

- Linear precision: score = (1/k) sum X_i. E = (1/k) sum p_i. Correlation does not appear. Optimal = top-k by p (PRP). Var = (1/k^2) sum_{i,l} Cov(X_i, X_l); diversification (spreading over base facts) lowers variance only.
- Mean-variance (Wang & Zhu form): maximize sum p_i - b * Var. Variance term is sum_{i,l} Cov, so the marginal penalty for adding i given S is b * 2 * sum_{l in S} Cov(i,l) + b * p_i(1-p_i). Cov is large when D sets overlap and q is high-ish. This is MMR with similarity := covariance of failure indicators (idea 8.1).
- Nonlinear score g(N), N = number correct: E g(N) differs from g(E N) by Jensen. Concave g (threshold-reward saturating, or a penalty that grows faster than the reward) makes variance costly, so diversification raises E g. Example: g = 1[N/k >= tau] (pass a precision bar). If E N/k > tau, you want LOW variance (spread). If E N/k < tau you want HIGH variance (concentrate, e.g. gamble on few shared base facts). Direction depends on which side of the threshold you sit on, which is exactly what is unknown here.
- Per-fact penalty: if each wrong base fact costs c once regardless of how many claims use it, expected penalty = c * sum_j (1-q_j) * 1[B_j used]. This favors concentrating on few highly reliable facts (fewer exposures), the OPPOSITE of diversification. If instead each wrong claim costs (linear), correlation is irrelevant. So "diversify" is not universally right; the cap should be tuned to the hypothesis.
- Coverage reward (the "connect what the universe says" hypothesis): reward = number of distinct entities/attributes/types touched by correct claims. This is monotone submodular (in expectation, sum over elements of P(covered by some correct chosen claim) = 1 - prod(1-p_i) for independent cover paths, which is noisy-OR). Diversification raises expected score here. With correlated failure the coverage probability is lower than the independent noisy-OR, so use P(covered) = 1 - P(all covering claims fail), computed over base facts.
- Duplicate penalty: if claims sharing a base fact or identical canonical form are penalized, the marginal gain of a duplicate is negative, same effect as a hard cap.

Literature that states "diversification does not raise expected relevance, only the objective changes": Chen & Karger (objective change from E[count] to P(>=1)); Wang & Zhu (diversity as risk reduction, trade-off parameter b). I did not find a paper stating the Jensen argument in these exact words for precision-type scores; the direction above is my derivation.

### 1.3 Recommendation
Treat variance reduction as insurance, not as expected-score gain. Use a small risk weight b and a cap on per-base-fact exposure; do not push lambda low.

---

## 2. Constrained diversity

Findings from sources:
- Greedy is a 1/2-approximation for monotone submodular maximization under a matroid (Fisher, Nemhauser, Wolsey 1978); continuous greedy gives 1-1/e (Calinescu, Chekuri, Pal, Vondrak; Vondrak 2008), tight (Feige); continuous greedy is impractically slow; Filmus & Ward give a combinatorial 1-1/e (greedy then local search). Source (secondary summaries): https://arxiv.org/pdf/1811.03093 ; https://www.research.ibm.com/publications/maximizing-a-monotone-submodular-function-subject-to-a-matroid-constraint ; https://arxiv.org/pdf/1703.06053
- Max-sum diversification (relevance submodular + dispersion of pairwise distances) under a matroid: 1/2-approx by local search (Borodin, Lee, Ye; Abbassi, Mirrokni, Thakur); cardinality case has a simple greedy 2-approx. https://arxiv.org/pdf/1203.6397 ; https://arxiv.org/pdf/1511.02402 ; local search variants https://ar5iv.arxiv.org/html/1607.04557
- Fairness as partition matroid (group i gets at most k_i): "Diverse Data Selection under Fairness Constraints", fair Max-Min diversification. https://arxiv.org/pdf/2010.09141
- MMR itself is the greedy for a max-sum-like objective; with per-type quotas it is greedy on a partition matroid. The explicit statement of its constrained guarantee is my inference (not found as a single published statement).

Practical mapping (EXTRAPOLATION):
- Per-type quota: partition matroid. If the quota is an EXACT count (need exactly 1000 total with fixed type mix), use a base-of-matroid version; greedy still returns a maximal independent set, which is a base when all quotas fill.
- Per-base-fact cap (at most c claims using base fact j): this is a partition-like constraint when each claim uses ONE base fact (matroid), but a claim using TWO base facts (compare, relation, change) makes it an intersection of constraints (a b-matching-type / k-extendable system), not a matroid. Greedy then gets 1/(k+1)-style guarantees for k-systems (Fisher et al. 1978; unverified here) but in practice is near-best. Say this honestly in any write-up.
- Knapsack/exposure caps: budgeted submodular needs cost-benefit greedy plus best singleton (Khuller et al. 1999; Sviridenko 2004). Not searched; cite from memory only.

---

## 3. Quality x diversity: DPP

- Kulesza & Taskar monograph: L_ij = q_i phi_i^T phi_j q_j; P(S) proportional to det(L_S) = prod q_i^2 * det(S_S). Quality and diversity decouple; k-DPP conditions on |S| = k. https://arxiv.org/abs/1207.6083
- Chen, Zhang, Zhou (Hulu), NeurIPS 2018: exact greedy MAP via incremental Cholesky; O(k^2 M) after kernel, i.e. fast enough for ~1000 picks from large pools; sliding-window variant. Tunable kernel L = Diag(exp(alpha r)) S Diag(exp(alpha r)), with alpha = theta/(2(1-theta)) in the paper; some follow-ups write alpha = beta/(1-beta) (factor of 2 differs; check convention). Secondary summary says theta about 0.7 was typically best (unverified). https://arxiv.org/pdf/1709.05135 ; https://arxiv.org/pdf/2509.10392v1
- Greedy MAP for DPP: log det is submodular but NOT monotone in general, so greedy guarantees are weaker than MMR-style monotone cases (known result from Kulesza-Taskar / Chen; my recollection, unverified).

Mapping calibrated p to quality (EXTRAPOLATION):
- q = exp(alpha * logit p) = (p/(1-p))^alpha. For alpha=1/2, q^2 = odds. Then det(L_S) = prod odds_i * det(S_S)^: the set weight is the product of odds, i.e. a likelihood ratio of "all correct", a principled reading. Choose alpha by validation (see 4 and 8.5), not by feel.
- Alternative: q = p^gamma. Matches the product-of-probabilities meaning of "all k correct" at gamma=1/2 (since q^2 = p), which is the natural joint-correctness weight under independence.
- The DPP repulsion with S built from dependency sets (Jaccard of D(i)) directly encodes "shared base fact => repel". S must be PSD: Jaccard kernel on sets is PSD (it is a known PSD kernel); cosine on indicator vectors is also PSD. Both safe.
- Learned kernels: Kulesza & Taskar learning of DPPs (UAI 2011) https://proceedings.mlr.press/r9/kulesza11a.html . Not useful here without labels on "good sets".

---

## 4. Learning / adapting lambda

Findings (abstract-level, verified existence only):
- R-LTR (Zhu et al., SIGIR 2014): sequential ranking with learned relevance and diversity weights from training data. https://dmice.ohsu.edu/bedricks/courses/cs635_spring_2017/pdf/zhu_2014.pdf
- PAMM (Xia et al., SIGIR 2015): structural learning of diverse ranking by optimizing a diversity metric directly. https://arxiv.org/pdf/1504.04596
- Neural variants (NTN, DESA, MDP-based) exist; I only confirmed an MDP paper: https://arxiv.org/pdf/1802.08401 . I did not verify NTN (Xia 2016) or DESA details.
- MMR lambda is generally hand-tuned; 2024 paper notes the unpredictability of lambda in high-dimension and its dependence on the parameters: https://arxiv.org/pdf/2407.04573 . Vendor guidance of lambda 0.5 to 0.8 is heuristics only.
- I found no source on Bayesian optimization of MMR lambda or query-ambiguity-based adaptive lambda (section 9).

Relevance for us: these methods need supervised diversity labels, which we do not have. The practical analogue is tuning lambda against a SIMULATED objective suite (8.5), since we can generate correlated failures from our own dependency model and the practice labels.

---

## 5. Robust selection under an unknown objective

- SATURATE (Krause, McMahan, Guestrin, Gupta, JMLR 2008): maximize min_i F_i(S) over several monotone submodular F_i; bicriterion approximation (needs slightly more than k items or relaxes the level), tight unless P=NP; can trade off average vs worst case. https://www.jmlr.org/papers/v9/krause08b.html ; NIPS version https://proceedings.neurips.cc/paper/2007/hash/eae27d77ca20db309e056e3d2dcd7d69-Abstract.html
- Orlin, Schulz, Udwani: robust monotone submodular maximization against removal of up to tau elements; max-min of submodular functions is inapproximable in general, only bicriteria. https://arxiv.org/pdf/1507.06616 . Bogunovic et al. partitioned robust (PRo): https://ar5iv.arxiv.org/html/1706.04918 . The adversarial-removal model is a decent proxy for "adversary corrupts a few base facts": remove tau base facts, each takes out all its dependent claims. (EXTRAPOLATION; removal of a base fact removes a SET of items, a slight generalization.)
- Distributionally robust submodular maximization exists (title seen at https://par.nsf.gov/biblio/10100048 ; authors/guarantees unverified).

Design (EXTRAPOLATION): define scoring hypotheses H1 precision, H2 precision minus duplicate penalty, H3 type/entity coverage, H4 calibration (Brier/log score with our confidences), H5 threshold-precision, H6 base-fact-exposure penalty. Evaluate candidate selectors (PRP, MMR at several lambda, capped greedy, DPP) by simulated score under each hypothesis, normalized by the best achievable per hypothesis, and pick the selector with the best worst-case ratio (maximin regret). That is SATURATE's idea applied at the selector level, which is cheap (no submodular solver needed). Pareto view: keep selectors not dominated across H1..H6; choose the knee.

---

## 6. Similarity for structured items

No literature specific to claims-with-base-facts was found. Standard tools:
- Dependency-set similarity: sim(i,l) = Jaccard(D(i), D(l)), or probability-weighted overlap sum_{j in D(i) inter D(l)} w_j. Better for our purpose is the failure-correlation corr(X_i, X_l) (section 1.2): it directly equals what we want to penalize, is computed from q_j, and is PSD as a covariance/correlation matrix.
- Type/attribute kernel: k_type = 1 if same claim type (and same attribute), blended with the dependency kernel (product or sum of PSD kernels is PSD). Hybrid text+structure kernels are common in recommendation; no specific source retrieved.
- Near-duplicate prefilter: canonicalize the claim (type, subject(s), attribute, value, date) and hash exactly; for fuzzy, MinHash (Broder) or SimHash (Charikar) over (entity, attribute, date) tokens. For structured claims an exact canonical key is cheaper and exact; MinHash only if we compare soft token sets. (Not searched; standard knowledge, no URL verified.)
- Cheap tip: indexing by base fact turns similarity into an inverted index, so neighbour lookups cost O(deg) rather than O(n).

---

## 7. Scaling (k=1000, n up to ~10^5, 2 CPUs)

- Lazy greedy (Minoux 1978): exploits diminishing returns with a priority queue; typically 10-1000x fewer evaluations. Works for MMR-like objectives that are monotone submodular (marginal gain upper bounds only decrease). Plain MMR with max-similarity penalty is NOT submodular in general, but lazy evaluation remains a valid heuristic only if gains are non-increasing, which holds for max-sim penalties (the penalty can only grow as S grows, so stale scores are valid upper bounds). Good news: stale = upper bound => lazy MMR is EXACT for the MMR rule. (DERIVATION.)
- Stochastic greedy (Mirzasoleiman et al., AAAI 2015): sample (n/k) log(1/eps) candidates per step, (1-1/e-eps) in expectation, O(n log 1/eps) total evaluations independent of k. https://arxiv.org/pdf/1409.7938 ; https://ojs.aaai.org/index.php/AAAI/article/view/9486
- Sieve-streaming (Badanidiyuru et al., KDD 2014): one pass, (1/2 - eps), memory O(k log k / eps); Sieve-Streaming++ with O(k) memory. Not needed unless candidates cannot be held in memory. https://arxiv.org/pdf/1905.00948 (follow-up citing KDD'14)
- Budget: 10^5 candidates, k=1000, naive MMR with a dense similarity check is 10^5 * 10^3 * 1000 = 10^11 pair evals if done naively; with inverted-index dependency similarity and lazy greedy it is a few million ops. Chen et al. greedy DPP is O(n k^2) = 10^5 * 10^6 = 10^11 flops without structure; too heavy for 2 CPUs in naive form, but fine at n = 10^4 after a pre-filter by p (keep the top 2-5x k per type). So: prefilter by p and by exact-duplicate key, then lazy greedy.
- Distributed greedy: unnecessary at this scale.

---

## 8. Untested ideas

"UNTESTED" = I did not find published testing; absence of evidence in a short search, not proof.

**8.1 Failure-correlation MMR (sim = estimated P(joint failure) or correlation of failure indicators).** UNTESTED (closest: Wang & Zhu use covariance of relevance estimates, Collins-Thompson uses term covariance; both are portfolio, not claim-structure).
- Mechanism: score(i|S) = p_i - lambda * max_{l in S} corr_fail(i,l) or - b * sum_{l in S} Cov(X_i,X_l). Cov computed from shared base facts and their q_j.
- Why: it penalizes exactly the risk that diversification is supposed to cut; text/type similarity is a poor proxy.
- Cheap test: simulate base-fact truth by Bernoulli(q_j) from practice data (or use practice labels for a hold-out), compare mean and 5th-percentile precision of PRP vs this vs text-MMR over 10^4 draws.
- Risk: q_j mis-estimated; wins only on variance under linear score. Needs the nonlinear hypotheses to show mean gain.

**8.2 Dependency-aware MMR with per-base-fact exposure caps.** UNTESTED. Mechanism: hard cap c_j on claims per base fact (or per entity), implemented as a constraint inside lazy greedy. Why: bounds the loss from any single lying page to c_j claims, a worst-case guarantee akin to Orlin-Schulz-Udwani with tau removals. Cost under precision: choose c to be loose (for example top 2-3% of the set per fact) so the p-ordering loses little. Test: sweep c, plot expected precision loss vs worst-case (tau=5 base-fact removal) precision. Risk: if scoring penalizes per-wrong-fact (1.2 per-fact penalty) the cap helps; if scoring rewards coverage the cap helps; if pure precision costs a small mean loss.

**8.3 Two-stage coverage-then-MMR.** UNTESTED as such (coverage objectives S-recall/alpha-nDCG exist: https://arxiv.org/pdf/1805.02334). Stage 1: greedily cover entities/attributes/types with highest-p representative per cell (covering ~300-500 slots). Stage 2: fill the remaining slots with plain p-ordered MMR under caps. Why: guarantees coverage under the "connected universe" hypothesis while keeping most of the set precision-optimal. Test: coverage and precision of resulting sets vs one-stage MMR. Risk: stage 1 forces lower-p items; limit its share (for example 30%).

**8.4 Confidence-shaped lambda (lambda depends on p).** UNTESTED (no source). Idea: items with p near 1 are safe, so no need to diversify them (lambda_i near 1); items of mid p get higher diversity pressure. Equivalent to penalizing variance contribution p(1-p) rather than just similarity. Formal link: in mean-variance, marginal variance penalty is proportional to p_i(1-p_i) + 2 sum Cov, so lambda(p) = lambda0 * sqrt(p(1-p)) type shape falls out of the math (DERIVATION). Cheap test: compare constant-lambda with p(1-p)-scaled penalty under 8.1 simulation.

**8.5 Lambda tuned by Monte Carlo of correlated failures.** UNTESTED for MMR (search found none: section 9). Mechanism: sample base-fact truth from q, evaluate selector under hypothesis suite H1..H6, take lambda from the maximin-regret choice (section 5). Cheap: 1000 draws x a few lambdas x 6 hypotheses; each eval is a bitset op. Risk: the simulation inherits the q_j model's errors; validate q calibration on practice labels first. Note that grid search is enough; Bayesian optimization is overkill for one parameter.

**8.6 MMR in probability space (maximize E[correct] minus b Var).** Exists in IR as Wang & Zhu (TESTED, SIGIR 2009) for documents; UNTESTED for claims with set-based dependency structure and for a coupling with quotas. Mechanism: as 1.2. Adds nothing over 8.1 if b and correlation are the same; it is the same idea in standard notation.

**8.7 Type-stratified MMR with quotas proportional to per-type reliability.** UNTESTED. Mechanism: allocate quota_t proportional to (sum of the top-p mass of type t) or to reliability r_t = mean p in type t, then MMR inside each type. Why: automatically shifts slots to types with reliable base facts (for example fact/compare more than change/at_event if those are noisier), while still covering all types. A principled alternative is water-filling: increase each type's quota until marginal p equalizes, which equals unconstrained PRP; quotas then are a deliberate departure whose price you can compute (loss = sum of p gap). Test: compute that price on practice data; if a floor quota costs under 0.5% expected precision it is cheap insurance for coverage hypotheses.

**8.8 Anti-MMR for verification (pick redundant evidence).** UNTESTED. For the 18,000-row labelling: select rows that AGREE or overlap on a base fact (negative lambda) so cross-checks detect liars, then spend the saved budget on diversity elsewhere. Related: active learning picks informative items, the opposite of diversity in some regimes. Test: on practice data, measure whether claims whose base facts are corroborated by a second page have higher precision than singletons. If yes, corroboration count is a feature in q_j. Risk: correlated sources (copying) look like corroboration; use source independence.

**8.9 Noisy-OR/coverage objective with correlation (new objective, not a new rule).** Related theory exists (submodular coverage; Chen & Karger's k-call), but not for base-fact structure. Objective: f(S) = sum over targets t of P(at least one correct claim in S covers t), computed with base-fact sharing. Greedy with lazy evaluation gets 1-1/e under cardinality, 1/2 under partition matroid (section 2). UNTESTED here.

**8.10 Adversarial-removal robustification (tau liar pages).** Orlin-Schulz-Udwani style, UNTESTED with set-valued removals. Choose S to maximize the worst-case score after removing the tau base facts with the greatest dependent mass in S. Cheap greedy approximation: iterative reweighting of base fact "exposure" (minimax by multiplicative weights). Directly covers the stated failure mode (we trusted a lying page).

**8.11 Hedged portfolio of selectors.** UNTESTED: build the final set as a union of top slices from two selectors (for example 700 from PRP+caps and 300 from coverage-first). Simple hedge across scoring hypotheses; gives bounded regret under both.

Priority for a 25-minute-class experiment: 8.2 (cap sweep), 8.1 and 8.5 sharing the same simulator, 8.7 price calculation.

---

## 9. What I searched for and did NOT find

- Any paper applying CVaR to selecting a set/ranking of items under correlated item failures. (Risk-sensitive IR is about evaluation and query expansion.)
- Published statement of the exact Jensen/linearity argument "diversification leaves expected precision unchanged under linear scoring" in IR terms; Chen & Karger and Wang & Zhu imply it but I did not read the full text for an explicit theorem.
- Bayesian optimization of MMR lambda; query-ambiguity-based adaptive lambda (the 2024 vector-retrieval paper only complains about tuning). Xia 2016 NTN and DESA: not verified.
- Confidence-dependent lambda; similarity defined as probability of correlated failure; per-source exposure caps in MMR.
- Noisy-OR / redundancy-reliability literature linked to subset selection (second search returned only generic diversified top-k).
- Sieve-streaming original paper PDF (only citing papers fetched); original MMR paper (Carbonell & Goldstein 1998) not fetched in this pass; its definition is standard: MMR = argmax_i [lambda * Rel(i) - (1-lambda) * max_{l in S} Sim(i,l)].
- Knapsack-constrained submodular (Khuller et al., Sviridenko), k-system greedy bounds, MinHash/SimHash: cited from memory, no URL verified.
- Whether greedy DPP MAP is non-monotone and its exact guarantee: recalled, not verified in this pass.

## References (URLs)

- Wang & Zhu, Portfolio theory of IR, SIGIR 2009: https://ir.webis.de/anthology/2009.sigirconf_conference-2009.16
- Chen & Karger, Less is more, SIGIR 2006: https://ir.webis.de/anthology/2006.sigirconf_conference-2006.57/
- Course notes on PRP failures, portfolio, Chen-Karger: https://www.cs.umd.edu/class/fall2010/cmsc828e/jian2.pdf
- Collins-Thompson NIPS 2008: https://papers.neurips.cc/paper/2008/hash/e0cf1f47118daebc5b16269099ad7347-Abstract.html ; CIKM 2009: https://ir.webis.de/anthology/2009.cikm_conference-2009.88
- Dincer et al. TRisk: https://www.dcs.gla.ac.uk/~craigm/publications/dincer2014hypothesis.pdf ; ZRisk/GeoRisk: https://archive.cps-vo.org/node/39077
- Matroid greedy/continuous greedy summaries: https://arxiv.org/pdf/1811.03093 ; https://www.research.ibm.com/publications/maximizing-a-monotone-submodular-function-subject-to-a-matroid-constraint ; https://arxiv.org/pdf/1703.06053
- Borodin et al. max-sum diversification: https://arxiv.org/pdf/1203.6397 ; https://arxiv.org/pdf/1511.02402 ; https://ar5iv.arxiv.org/html/1607.04557
- Fair diversification (partition matroid): https://arxiv.org/pdf/2010.09141
- Kulesza & Taskar DPP: https://arxiv.org/abs/1207.6083 ; Learning DPPs: https://proceedings.mlr.press/r9/kulesza11a.html
- Chen et al. fast greedy DPP: https://arxiv.org/pdf/1709.05135 ; tunable kernel reuse: https://arxiv.org/pdf/2509.10392v1
- R-LTR: https://dmice.ohsu.edu/bedricks/courses/cs635_spring_2017/pdf/zhu_2014.pdf ; PAMM: https://arxiv.org/pdf/1504.04596 ; MDP diversification: https://arxiv.org/pdf/1802.08401 ; MMR lambda tuning problem: https://arxiv.org/pdf/2407.04573
- SATURATE: https://www.jmlr.org/papers/v9/krause08b.html ; https://proceedings.neurips.cc/paper/2007/hash/eae27d77ca20db309e056e3d2dcd7d69-Abstract.html
- Robust submodular: https://arxiv.org/pdf/1507.06616 ; https://ar5iv.arxiv.org/html/1706.04918 ; DR submodular listing https://par.nsf.gov/biblio/10100048
- Stochastic greedy: https://arxiv.org/pdf/1409.7938 ; Sieve-streaming follow-up: https://arxiv.org/pdf/1905.00948
- Diversity metrics (alpha-nDCG, S-recall, axiomatics): https://arxiv.org/pdf/1805.02334
- Diversity survey: https://arxiv.org/pdf/1807.01477
