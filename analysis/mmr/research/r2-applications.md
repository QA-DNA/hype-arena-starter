# R2: MMR and diversity selection in fact verification, truth discovery, KG summarization, data selection

Scope note: research was time-boxed. Every number below was read from a fetched page unless marked **[memory]** (my background knowledge, not re-verified this session) or **[snippet]** (only seen in a search snippet). "Maps to VERIDYCT" lines are EXTRAPOLATION, not findings. Free tools only; no Perplexity.

Core formula used everywhere: MMR(D_i) = λ·Sim(D_i, Q) − (1−λ)·max_{D_j∈S} Sim(D_i, D_j), greedily add argmax (Carbonell & Goldstein, SIGIR 1998). Written out exactly this way in the AVeriTeC paper below.

---
## 1. Evidence retrieval for fact verification with diversity

**1.1 AIC CTU at AVeriTeC (3rd place), the only explicit MMR-in-fact-checking use I found.** Pipeline: BM25 prune to ω chunks (6000 dev / 2000 test), embed, fetch top |P|=40 by cosine to the whole claim, then MMR-rerank down to |S|=10 with **λ=0.75** ("favour relevancy rather than diversity"). Motivation stated: embedding the whole claim "is prone to redundancy among search results". Labels: Supported / Refuted / Not Enough Evidence / Conflicting Evidence-Cherrypicking. They justify MMR qualitatively; the page I could read gives **no ablation of MMR on/off** (I did not find one). https://arxiv.org/pdf/2410.11446
- Maps to VERIDYCT (extrapolation): same shape as our evidence step: over-fetch 40, MMR to ~10, λ≈0.75 as a starting point. But our "Sim" should be near-duplicate/template similarity, not semantic similarity (see 2.3, 3.1).

**1.2 Differentiable Greedy Networks (FEVER sentence selection, submodular diversity).** Argues conventional FEVER sentence selection scores sentences "on their individual merit"; instead optimizes informativeness of the *set* via a submodular function with an unrolled, differentiable greedy algorithm. Abstract claims better precision/recall than discrete optimizers and baselines; no numbers on the abstract page. A search snippet reports the RTE model dropping from 88.00% accuracy with oracle evidence to 50.37% with the baseline retrieval **[snippet]**, i.e. retrieval is the FEVER bottleneck. https://arxiv.org/abs/1810.12464 , https://arxiv.org/pdf/1810.12464
- Maps: greedy submodular set selection is the same family as MMR; supports "select a set, not a ranking".

**1.3 From Relevance to Utility (FER).** Evidence should be chosen by utility to the verifier (verifier feedback), not relevance. Alternative to MMR, FEVER. https://arxiv.org/pdf/2310.11675
**1.4 Mask-to-Correct+** reports a relevance/diversity parameter α=0.3 as best in an entity-masking fact-correction setup **[snippet]**; loosely related. https://arxiv.org/pdf/2605.18776

**1.5 Datasets and "enough evidence" (relevant to `unsure`).**
- FEVER: SUPPORTED / REFUTED / NOT ENOUGH INFO. https://arxiv.org/pdf/1803.05355
- HoVer: many-hop; REFUTED and NEI merged into NOT-SUPPORTED; best pipeline retrieved the full evidence set and verified correctly on only ~14.9% of dev vs ~81% human **[snippet]**. https://arxiv.org/pdf/2011.03088
- FEVEROUS: tables + text; NEI when Wikipedia lacks enough; annotators still record most relevant (insufficient) evidence. https://arxiv.org/pdf/2106.05707
- Evidence Sufficiency Prediction task (predict only when evidence sufficient; up to +17.8 F1 on that task) **[snippet]**, https://www.arxiv.org/pdf/2204.02007 (identity of this paper from snippet only; verify before citing).
- A FEVEROUS system treats "retriever still wants more hops" as an NEI signal **[snippet]** (Papelo). A 2026 preprint argues evidence *absence* is not evidence *insufficiency* and benchmarks conflate them **[snippet, unread]**, https://arxiv.org/pdf/2601.21387 is a related 2026 evidence-ranking paper.
- Maps: our `unsure` = "dataset gives no means to tell". Operational reading: after deduped/diversified evidence selection, no distinct *independent* observation of the (subject, attribute) at a compatible date exists. Count independent evidence, not rows. (Extrapolation.)

**Not found:** a controlled FEVER/HoVer/FEVEROUS experiment of plain MMR vs top-k with accuracy deltas.

---
## 2. Conflicting and temporal evidence

**2.1 Benchmarks of conflicts (these measure LLM behaviour, none uses MMR).**
- ConflictBank: 7,453,853 claim-evidence pairs, 553,117 QA pairs; conflicts from misinformation, temporal discrepancies, semantic divergences; 12 LLMs. https://arxiv.org/abs/2408.12076
- WikiContradict: 253 human-annotated instances, RAG with 1 vs 2 contradictory Wikipedia passages. https://arxiv.org/abs/2406.13805
- "DRAGged into Conflicts" (CONFLICTS benchmark, 458 queries): conflict type decides the right behaviour; for subjective questions present the range of views **[snippet]**. https://arxiv.org/abs/2504.13079v2 ; RAMDocs / MADAM-RAG https://arxiv.org/abs/2504.13079 family (Wang et al. 2025), check IDs, snippet-level; Conflict-driven summarization https://arxiv.org/abs/2507.01281v1
- I found **no paper applying MMR specifically to conflicting-source retrieval**.

**2.2 Temporal RAG.**
- HoH: outdated passages distract models and can push harmful outputs even when current info is present **[snippet]**. https://aclanthology.org/people/jie-ouyang/
- Re3 (ACL 2026): time-aware encoder + conflict-aware recency filter + listwise arbitration; up to +25.2% on dynamic tasks **[snippet]**. https://preview.aclanthology.org/ingest-acl/2026.acl-long.1180/
- T-GRAG: names three failure modes: time-specific facts merged into one node, retrieval ignoring query time, redundancy within a time point; time-stamped graphs, Time-LongQA. https://arxiv.org/pdf/2508.01680
- Takeaway of the literature: recency-aware filtering plus explicit arbitration, not similarity alone.

**2.3 Answer to "how to select evidence for a dated claim so the latest valid observation is not crowded out by near-duplicates" (EXTRAPOLATION, no paper tests it).**
1. Do not run MMR over raw rows. Collapse first: key = (subject, attribute, normalized value) and, per key, keep the *source-independent* count plus min/max date and last-seen date. Template near-duplicates then cost one slot.
2. Partition by (subject, attribute), then rank *values* (not rows) per partition. MMR operates across distinct values/intervals so a stale value repeated 30 times cannot occupy all k slots.
3. Time as a hard/soft feature in the relevance term: relevance = text sim × temporal validity (observation date ≤ claim date, closest preceding observation wins; an interval is [first_seen, next_different_value_date)). Reserve one slot for "latest observation at or before the claim date" regardless of MMR score (forced-inclusion, like the arbitration step in Re3).
4. If two distinct values appear within the same window from independent pages, that is a conflict signal, not redundancy; MMR's diversity term should *help* surface both, then truth-discovery (section 3) decides.
5. "Redundancy" similarity should be cheap and exact (shingle/Jaccard or template-id equality), which also fits 2 CPUs.

---
## 3. Truth discovery and copy detection

**3.1 Dong, Berti-Equille, Srivastava, VLDB 2009 (the key paper for us).** Read in full text. Claim: "a false value can be spread through copying and that makes truth discovery extremely tricky"; sharing *rare/false* values is strong evidence of dependence, because independent sources rarely share the same false value; sharing true values is weak evidence. Bayesian dependence probability per source pair, then a **discounted vote count**: a source's vote for v is scaled by the probability it did *not* copy (independent contribution ∝ (1−c)^{d}, c = copy probability). Worked example in the paper: naive count 3 vs dependence-adjusted ≈1.4–2.1 depending on dependence; estimated count within t0 ≤ t ≤ 1.5·t0. Also models source accuracy (ACCU) and value similarity (SIM). Warns that a heavily duplicated source "can dominate the vote results in the first round" so dependence must be handled from the start.
Results (book data set, precision): NAIVE .71, NAIVE+SIM .74, ACCU .79 (variants .83/.87), DEPEN/ACCUCOPY-style best **.89**; (table rows are garbled in extraction; the .71 baseline and ~.89 best are clear). Falsification study: 1 independent bad source plus copiers gets its false value accepted only when copiers behave like independents; falsifying 5 values needed >700 sophisticated falsifiers. https://lunadong.com/publication/dependence_vldb.pdf , DOI listed at https://mail.vldb.org/pvldb/volumes/2/paper/Integrating%20Conflicting%20Data%3A%20The%20Role%20of%20Source%20Dependence
- Maps: our "lying page can be repeated" is exactly this. De-duplicating evidence before voting = a crude, MMR-like special case of the discount; the paper's version is better because it keys on *shared rare values*, not on textual similarity. Cheap Rust analogue: pages (sources) that agree with each other on many values that few other pages state get a joint weight ~1, not N.

**3.2 Truth Finding on the Deep Web: Is the Problem Solved? (Li et al., VLDB 2013, arXiv 1503.00303).** Stock and Flight domains. Naive VOTE precision **0.908 (Stock), 0.864 (Flight)**. Flight is worse "mainly because of copying on wrong values". Of inconsistencies in Stock: about half ambiguity, a third out-of-date data, rest errors (Flight: 56% erroneous). They found copier groups (11 stock sources derived from one provider). Compares VOTE, HUB, AvgLog, Invest, PooledInvest, Cosine, 2/3-Estimates, TruthFinder, AccuPr, PopAccu, AccuCopy. https://arxiv.org/abs/1503.00303
- Maps: out-of-date data is a major conflict cause; our dataset is *about* that, so "latest valid" matters more than vote count.

**3.3 TruthFinder (Yin, Han, Yu; KDD 2007 / TKDE 20(6):796–808, 2008).** Mutual reinforcement: site trustworthiness = avg confidence of its facts; fact confidence rises with trustworthy providers; implication between similar facts. Reported to beat plain voting and to rank sites better than search engines. I could only confirm publication data and the core idea from snippets; it does **not** model copying (that gap is what Dong 2009 fills; the VLDB 2013 table lists TruthFinder without a "copying" mark in its feature matrix). https://research.ibm.com/publications/truth-discovery-with-multiple-conflicting-information-providers-on-the-web

**3.4 LTM, Latent Truth Model (Zhao et al., VLDB 2012).** Unsupervised generative model with separate false-positive and false-negative rates per source; multi-valued attributes; linear-time collapsed Gibbs sampling; outperforms prior methods on two real data sets. https://arxiv.org/abs/1203.0058
- Maps: false-positive vs false-negative per page fits our `false` = "states at least one false value" vs `unsure`.

**3.5 Knowledge-Based Trust (Dong et al., VLDB 2015).** Source trust = correctness of facts it states, via a multi-layer model separating extraction errors from source errors; 2.8B extracted facts, 119M webpages. https://arxiv.org/pdf/1502.03519 (Copy-detection is not part of KBT's headline; it is in 3.1 and in "Truth Discovery and Copying Detection in a Dynamic World" VLDB 2009, which also handles time **[snippet]**.)
- That last paper is directly about temporal data; I did not read it. Worth a follow-up.

**Not found:** an experiment where MMR (similarity-based) dedup before voting was compared to Dong's dependence discount. Treat "MMR before voting" as untested.

---
## 4. KG fact / entity summarization

**ESBM** (Liu et al., ESWC 2020): 175 entities (DBpedia + LinkedMDB), 2,100 ground-truth summaries by 30 experts, top-5 and top-10 triples; metric F1 = 2PR/(P+R) vs expert summaries; 9 systems compared plus a supervised one. https://arxiv.org/pdf/2003.03734
Average F1 (from search synthesis of ESBM Table 4, consistent across papers; treat as [snippet-level]): 
| System | DBpedia k5 | k10 | LinkedMDB k5 | k10 |
|---|---|---|---|---|
| RELIN | .242 | .455 | .203 | .258 |
| DIVERSUM | .249 | .507 | .207 | .358 |
| FACES | .270 | .428 | .169 | .263 |
| LinkSUM | .287 | .486 | .140 | .279 |
Newer: ESSTER .324/.521 (DBpedia), BAFREC .335 (k5). https://ceur-ws.org/Vol-2699/paper14.pdf , https://arxiv.org/pdf/2003.03736
Mechanisms:
- **RELIN**: PageRank-style random surfer mixing relatedness and informativeness; tends to pick redundant topically-related triples. 
- **DIVERSUM**: forbids two triples with the same property, so it can return fewer than k (confirmed in ESBM text). Best of the four at k=10 on both datasets.
- **FACES** (AAAI 2015): Cobweb-style incremental hierarchical conceptual clustering of facts, pick representatives per cluster; scores diversity, uniqueness, popularity. https://ojs.aaai.org/index.php/AAAI/article/view/9180
- **LinkSUM**: PageRank + backlink; picks globally frequent values; evaluations note redundant properties. https://www.uni-trier.de/fileadmin/fb2/LDV/Rettinger/publications/LinkSUM.pdf
- Survey: https://arxiv.org/pdf/1910.08252
Gist: "one triple per property" or "one per cluster" (hard diversity) is as good as, or better than, popularity ranking; the best published F1 is still far below expert agreement (ORACLE gap).
- Maps (extrapolation): for the 1,000 generated claims, treat each (subject, attribute) / (relation type) as the property; DIVERSUM-style cap per property/type plus a coverage term (entities touched, claim types balance) beats unconstrained top-scoring. Unknown whether the scorer rewards diversity at all: scoring formula unpublished. Referee-truth is the hard constraint; diversity only breaks ties.

I could not retrieve exact formulas for FACES/LinkSUM/RELIN in this session (only mechanisms).

---
## 5. Data selection with diversity

- **Core-set active learning (Sener & Savarese, ICLR 2018)**: batch selection as k-center cover; bound depends on data geometry; "significantly outperforms existing approaches by a large margin" on image classification. https://arxiv.org/abs/1708.00489
- **BADGE (Ash et al., ICLR 2020)**: embed unlabeled points as hallucinated gradient vectors (magnitude ~ uncertainty), pick batch with k-means++ seeding (diverse + high-magnitude), no tuned hyperparameter, at least as good as alternatives across batch sizes/architectures. https://arxiv.org/abs/1906.03671 (k-means++ detail **[memory]**)
- **ICL demonstration diversity** ("The Role of Diversity in In-Context Learning", 2025): TopK vs Div (diversity-reduced pool) vs **TopK-Div** = greedy MMR-form `α·Sim(x, q) + (1−α)·Diversity(x, S)`, first pick by similarity only. Findings: diversity helps on harder tasks (reading comprehension, math, code) and on out-of-distribution queries; on simple sentiment TopK wins in-distribution (SST-2) but TopK-Div wins when demos switch to Amazon reviews. https://arxiv.org/pdf/2505.19426v2 . Explicit MMR for demonstrations also in molecular ICL https://arxiv.org/pdf/2502.05414 [snippet]; RL learned alternative RDES https://arxiv.org/abs/2412.03966.
- **Self-Instruct** (Wang et al. 2022): new LLM-generated instruction added only if ROUGE-L with every existing one is below a threshold (0.7 **[memory]**; the page confirms the "ROUGE-L similarity with any existing instruction" rule, the cut text hid the number). 52,445 generated instructions analysed. https://arxiv.org/abs/2212.10560
- **SemDeDup** (Abbas et al. 2023): cluster embeddings, remove pairs above a cosine threshold; removed **50%** of a LAION subset with minimal loss, halving training; improved over prior dedup on C4. https://arxiv.org/abs/2303.09540
- **D4** (Tirumala et al. 2023): dedup then embedding-based selection/diversification; at 6.7B, ~20% faster training and up to ~2% average accuracy gain over 16 tasks; repeating selected data beat random repeats. https://arxiv.org/abs/2308.12284
- kNN with diverse neighbours and calibration-set selection: **not found** in this pass.
- Maps (extrapolation): (c) for synthetic LLM-generated rows use a Self-Instruct-style cheap gate (n-gram overlap against already-kept rows) plus SemDeDup-style template clustering; keep a held-out *calibration* set sampled by stratified template/attribute, NOT diversified, so calibration reflects the true row distribution (many near-duplicate templates are real mass in the 18k).

---
## 6. Summarization redundancy

- MMR originated for reordering documents and producing summaries (Carbonell & Goldstein 1998, citation as in AVeriTeC paper above).
- Lin & Bilmes, ACL 2011: monotone submodular objective = representativeness (coverage) term + diversity (cluster-reward) term, greedy with (1−1/e) guarantee **[memory]**; best known ROUGE on DUC-04 to DUC-07 at the time. MMR is a special greedy case without that guarantee. https://aclanthology.org/P11-1052/ , MMR table not retrieved.
- Maps: for the 1,000-claim pool use a coverage-plus-diversity objective (facility-location style: reward each entity/attribute/event covered) instead of pure pairwise MMR, because we want *coverage of the universe*, not just non-redundant pairs. Extrapolation.

---
## 7. Searched for and NOT found
- A direct FEVER/HoVer/FEVEROUS ablation of MMR vs top-k (accuracy deltas). Only the AVeriTeC system uses MMR and I saw no ablation.
- MMR applied specifically to conflicting-source / temporal-conflict retrieval.
- Any experiment pairing similarity-dedup (MMR-like) before voting against Dong's copy-detection discount.
- Exact FACES/LinkSUM/RELIN formulas; exact ESBM table (numbers above came via synthesis of snippets).
- kNN with diverse neighbours; calibration-set selection papers.
- Re3/HoH/Evidence-sufficiency details beyond abstracts; Dong "Truth Discovery and Copying Detection in a Dynamic World" (VLDB 2009, handles time + copying) unread: highest-value follow-up for us.
- Several arXiv IDs from snippets (2204.02007, 2504.13079, 2601.21387, 2605.18776) were not opened; verify before citing.

## Practical synthesis (extrapolation)
1. Dedup before MMR: exact/template collapse by (subject, attribute, value) with source-independence counts; MMR on what remains, λ≈0.75 start (AVeriTeC), tune on the 1,900 practice rows.
2. Reserve a forced slot for the latest observation at or before the claim date.
3. For vote weight use a Dong-style discount (shared rare values => copy) rather than row counts; this is the only part with measured evidence (naive .71 vs ~.89 precision on books; copying on wrong values hurt Flight to .864).
4. `unsure` when the deduped evidence has no independent, date-compatible observation.
5. Claim selection: DIVERSUM-style per-property cap + coverage objective; referee truth is the filter, diversity only a tiebreak since the score is unpublished.
