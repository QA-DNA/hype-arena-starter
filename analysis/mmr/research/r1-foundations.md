# MMR and the diversity-selection family: literature report (r1-foundations)

Date of research: 2026-10-28. Free tools only (WebFetch, WebSearch, jina, exa via mcporter, gh, crates.io API). No Perplexity. Nothing in the repository touched.

Convention: [SRC] = a source stated or measured this. [EXT] = my own extrapolation, not from a source. [UNVERIFIED] = I could not read the primary text.

---

## 1. Original MMR (Carbonell & Goldstein, SIGIR 1998)

Primary text read in full (2-page poster paper, CMU PDF): https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf (also ACM DOI 10.1145/290941.291025, https://doi.org/10.1145/290941.291025). Longer TIPSTER workshop version: Goldstein & Carbonell 1998, "Summarization: (1) Using MMR for Diversity-Based Reranking and (2) Evaluating Summaries", https://aclanthology.org/X98-1025/.

**Formula [SRC, paper section 2]** (the OCR of the PDF mangles it; the symbols are defined in the text):

    MMR = argmax_{D_i in R \ S} [ lambda * Sim1(D_i, Q) - (1 - lambda) * max_{D_j in S} Sim2(D_i, D_j) ]

- C = collection, Q = query or user profile, R = IR(C, Q, theta) = ranked list from a base retriever with relevance threshold theta, S = already selected subset, R\S = unselected remainder.
- Sim1 = document-query similarity; Sim2 = document-document similarity, "can be the same as Sim1 or a different metric". The penalty is the MAX over selected items (nearest-neighbour redundancy), not a sum or mean.
- The algorithm is incremental/greedy: each step takes the argmax and appends it to S.

**Lambda semantics [SRC]:** lambda = 1 gives "the standard relevance-ranked list"; lambda = 0 gives "a maximal diversity ranking among the documents in R"; in between, "a linear combination of both criteria is optimized". Advice in the paper: users sampling the information space should use a smaller lambda; users wanting to focus on reinforcing documents should use a larger one. They recommend starting at lambda = 0.3 to understand the region, then reformulating the query and using lambda = 0.7.

**Uses [SRC]:**
1. Document reordering in retrieval (rerank top of R).
2. Query-relevant single-document summarization: segment into sentences, MMR with cosine similarity to rerank sentences against a query, present top passages in original document order.
3. Multi-document summarization (news clusters with heavy repetition of background): the paper says this is where "the clearest advantage is demonstrated", "MMR results are clearly superior to non-MMR passage selection".

**Evaluation [SRC] (small and preliminary, the paper says so):**
- Pilot user study, 5 undergraduates: majority preferred the MMR ordering for "broad and interesting topics"; 80% chose MMR for a search task; users preferred MMR for navigation and finding candidates quickly, pure relevance for exploring within a relevant band.
- SUMMAC (May 1998, 15 summarizers): the MMR summarizer got the highest utility among query-relevant summaries (F = 0.73) and highest on informative summaries (70% accuracy). The paper cautions parameters like summary length varied across systems, so results are "indicative but not definitive".
- Relevance loss for diversity gain: 3 assessors, 50 of 200 articles of one TIPSTER topic, sentence precision at compression 0.25 and 0.1. Result: "no significant statistical difference" between lambda = 1, 0.7 and 0.3 (Table 1). I.e. in single-document summarization MMR cost no measurable precision.
- No large-scale quantitative retrieval benchmark in the SIGIR paper. [SRC] The multi-document claim is supported by observation (top 10 passages in news clusters are heavily duplicated, MMR "reduces or eliminates" that), not by a metric.

---

## 2. Theory

### 2.1 What greedy MMR optimizes
- Greedy MMR is a sequential rule; it is not defined by a set objective in the original paper. Lin & Bilmes (ACL 2011, https://aclanthology.org/P11-1052.pdf) define F_MMR as any set function whose marginal gain F(S+k) - F(S) equals the MMR score (their Eq. 1, with the max-penalty). Their **Theorem 2** [SRC]: F_MMR "is non-monotone submodular". Submodularity follows because max_{i in S} Sim2(s_i, s_k) can only grow as S grows (diminishing returns). Non-monotone because marginal gains turn negative once the penalty exceeds lambda * relevance. Their conclusion, quoted: "the greedy algorithm's constant-factor approximation guarantee does not apply in this case".
- The 2026 paper "Principled and Scalable Diversity-Aware Retrieval via Cardinality-Constrained Binary Quadratic Programming" (https://arxiv.org/html/2604.02554v1) restates it: "MMR maximizes a non-monotone submodular function (Lin and Bilmes, 2011), for which the greedy algorithm provides no approximation guarantee in general", and cost is O(k n d). It proposes a CCBQP formulation (Frank-Wolfe) that "consistently dominates MMR and DPP on the relevance-diversity Pareto frontier" on ASQA and QAMPARI with up to 22.9x speedup over MMR. [SRC, abstract-level; I did not audit the experiments.]
- Equivalent view [EXT]: the penalty is nearest-neighbour redundancy, so the implied set objective is "relevance sum minus a nearest-selected-neighbour penalty per item". It is not a coverage objective: nothing rewards covering a region of the pool, only avoiding closeness to what is already chosen.

### 2.2 Max-sum, max-min, and the axiomatic framework (Gollapudi & Sharma, WWW 2009)
Paper: https://dl.acm.org/doi/10.1145/1526709.1526761 ; text via https://theory.stanford.edu/~aneeshs/papers/diversification.pdf (read through exa excerpts) and https://archives.iw3c2.org/www2009/proceedings/pdf/p381.pdf.
- Setting [SRC]: relevance w(u), metric distance d(u,v), choose k. They state 8 axioms: scale invariance, consistency, richness, stability (S*_k subset S*_{k+1}), independence of irrelevant attributes, monotonicity, strength of relevance, strength of similarity.
- **Impossibility [SRC]:** "no diversification function can satisfy all the axioms simultaneously", and any proper subset is satisfiable ("maximal").
- Objectives [SRC]:
  - Max-sum: f(S) = (k-1) * sum_{u in S} w(u) + 2*lambda * sum_{u,v in S} d(u,v). Satisfies all axioms except **stability** (Remark 1). Equivalent to MAXSUMDISPERSION on d'(u,v) = w(u) + w(v) + 2*lambda*d(u,v).
  - Max-min (Remark 2): satisfies all axioms except **consistency and stability**; linked to MAXMINDISPERSION.
  - A third "mono-objective" (global importance w') objective fails only consistency (the two excerpts I saw disagree on remark numbering, so treat as approximate).
- Dispersion link gives 2-approximations: max-sum dispersion reduces to a metric problem solved by Hassin-Rubinstein-Tamir greedy-edges (ratio 2); max-min dispersion with triangle inequality has a 2-approx greedy (farthest-point, "GMM"; see Sydow, http://users.pja.edu.pl/~msyd/papers/sydow-bigTriangle-ma14.pdf, which also says both are NP-hard even with triangle inequality). [SRC]
- [EXT] Greedy MMR produces nested prefixes by construction, so it is stable in the Gollapudi-Sharma sense; max-sum optimal sets are not. For a fixed 1000-claim list that may be truncated or reordered, nesting is a practical plus.

### 2.3 Borodin, Lee, Ye (PODS 2012)
https://arxiv.org/abs/1203.6397 ; full text https://arxiv.org/pdf/1203.6397 (read). "Max-Sum Diversification, Monotone Submodular Functions and Dynamic Updates."
- Objective: f(S) + lambda * sum of pairwise distances over S (metric d), f monotone submodular, cardinality or matroid constraint. NP-hard "even with the triangle inequality" (reduction from Max-Clique; hard to beat 2-eps under a planted-clique style assumption, citing Alon). [SRC]
- **Theorem 1:** a simple greedy gives a **2-approximation** for cardinality-constrained monotone submodular quality plus max-sum dispersion; Theorem 2: single-swap local search gives 2-approx under any matroid. The greedy "does not try to optimize the objective in each iteration but rather optimizes a closely related potential function". Corollary 1 re-derives the Ravi-Rosenkrantz-Tayi greedy as 2-approx (Birnbaum & Goldman showed tightness). [SRC]
- On MMR directly [SRC, their text]: "The MMR heuristic has been widely used, but to the best of our knowledge, it has not been theoretically justified. Our paper provides some theoretical evidence why MMR is a legitimate approach... The greedy algorithm we propose can be viewed as a natural extension of MMR." Important nuance [EXT]: their guarantee is for sum-of-pairwise-distance diversity and their own potential-function greedy, NOT for MMR's max-penalty greedy.
- Dynamic updates: with modular weights, one swap maintains ratio 3 after a weight or distance perturbation; useful if candidates change. [SRC]

### 2.4 Does MMR have an approximation guarantee?
- Short answer [SRC + EXT]: no known worst-case guarantee for the exact MMR rule. Reasons: (a) the implied set function is non-monotone submodular, so Nemhauser-Wolsey-Fisher (1 - 1/e) does not apply (Lin & Bilmes); (b) the max-penalty is not a metric dispersion sum, so Borodin et al. do not apply; (c) the first pick is pure relevance, and greedy can lock in. Related positive results exist for variants: sum-penalty greedy 2-approx (Borodin), (1-1/e) for coverage-type objectives (IA-Select, facility location with monotone gain), 1/2 - eps for max-min with submodular utility (GIST, NeurIPS 2025: https://proceedings.neurips.cc/paper_files/paper/2025/file/41febbd2bd4bd1f268ada869cee28e44-Paper-Conference.pdf).
- NP-hardness [SRC]: max-sum/max-min diversification NP-hard (Borodin; Gollapudi-Sharma; Sydow). DPP MAP NP-hard (Kulesza & Taskar Theorem 2.9, https://arxiv.org/pdf/1207.6083), even to approximate within a constant, even with fixed cardinality.

### 2.5 Known failure modes
| Failure | Evidence |
|---|---|
| **Scale mismatch** between relevance and similarity: lambda*rel - (1-lambda)*maxsim mixes two unnormalized scales; lambda=0.5 means different things per embedding model / score distribution | [EXT] from formula; LangChain's implementation uses raw cosine on both sides (https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/vectorstores/utils.py lines ~112-160); Qdrant issue about negative MMR-era scores with Euclidean (https://github.com/qdrant/qdrant/issues/5390, tangential, unresolved) |
| **Lambda sensitivity** | Section 4.3: LocalLens #34 (lambda 0.5 evicts the best chunk, 0.7 recovers it); arXiv 2610.09412 (HotpotQA S-Recall@5 78.7 k-NN vs 48.1/58.6/72.8 for lambda 0.3/0.5/0.7) |
| **Only max-similarity penalized, no coverage notion** | Lin & Bilmes: sum-similarity coverage objective gives ROUGE-1 F 32.44% vs 38.65% with the saturated (alpha < 1) form; diversity reward alone matches best DUC-04 system. Dang & Croft: MMR "helps and hurts about the same number of queries" (Section 3.3) |
| **Candidate-pool dependence** (MMR only reorders/chooses within R) | BERTopic #1142; Qdrant `candidates_limit` defaults to `limit` (Section 4.1) |
| **Ties / first pick** | [EXT] first pick is argmax relevance; ties in maxsim (duplicates) break arbitrarily; not documented in sources |
| **Normalization / lambda direction conventions differ per product** | Section 4.1 table; LangChain-Qdrant inversion bug #39052 |
| **Quadratic-ish cost** | O(k n d) per query (arXiv 2604.02554); OpenSearch +247% p50 latency at k=50, 100 candidates (Section 4.1) |
| **Hurts on clean pools** | arXiv 2610.09412 BEIR NDCG@10 drops, e.g. ArguAna 38.3 -> 0.2 at lambda 0.5 |

---

## 3. The family

Notation: R = candidate pool, n = |R|, k = picks, S = selected.

### 3.1 xQuAD (Santos, Macdonald, Ounis)
- Sources: WWW 2010 "Exploiting query reformulations for web search result diversification", https://archives.iw3c2.org/www2010/proceedings/www/p881.pdf (read); original xQuAD: "Explicit search result diversification through sub-queries", ECIR 2010, LNCS 5993, https://eprints.gla.ac.uk/44352. (The WWW paper is where I read the formula; the search tool flagged the ECIR paper as first introduction.)
- Formula [SRC, Eq. 1-4]: d* = argmax_{d in R\S} (1 - lambda) P(d|q) + lambda * P(d, not-S | q), with P(d, not-S|q) = sum_i P(q_i|q) P(d|q_i) prod_{d_j in S} (1 - P(d_j|q_i)). Sub-queries q_i come from search-engine query suggestions.
- Guarantee: none stated; it is the probabilistic cousin of IA-Select's greedy but with a lambda mixture. Complexity O(k * n * |aspects|) with the product cached per aspect. [EXT on cache]
- Beats MMR when aspects are known/estimable: Dang & Croft Table (TREC WT-2010, sub-topics): alpha-NDCG MMR 0.3349 vs xQuAD 0.4074 vs QL 0.3236; WT-2009 MMR 0.2963 is below the query-likelihood baseline 0.2979. [SRC, https://ciir-publications.cs.umass.edu/getpdf.php?id=1050]

### 3.2 IA-Select (Agrawal, Gollapudi, Halverson, Ieong, WSDM 2009)
- https://www.microsoft.com/en-us/research/publication/diversifying-search-results/ ; PDF read: https://khoury.northeastern.edu/home/vip/teach/IRcourse/5_eval_userstudy/other_notes/diversifying-wsdm09.pdf
- Objective [SRC]: P(S|q) = sum_c P(c|q) * (1 - prod_{d in S} (1 - V(d|q,c))), "probability the average user finds at least one useful result" over a category taxonomy c. Greedy picks the document with max marginal gain, with category weights U(c|q,S) decayed by (1 - V(d|q,c)) after each pick.
- Guarantee [SRC]: Diversify(k) is NP-hard (Lemma 1); P(S|q) is submodular and monotone (Lemma 2); greedy is a **(1 - 1/e)-approximation** (Corollary 2), provably optimal when each document has a single category.
- When it beats MMR: when you have categories/intents and care about "at least one good result per intent", i.e. coverage. Needs reliable V(d|q,c). Complexity O(k * n * |C|).

### 3.3 PM-2 (Dang & Croft, SIGIR 2012)
- https://ciir-publications.cs.umass.edu/getpdf.php?id=1050 (read). "Diversity by proportionality: an election-based approach."
- Mechanism [SRC]: Sainte-Lague apportionment. Per step: quotient qt[i] = v_i / (2 s_i + 1); pick the aspect i* with the largest quotient; pick d* = argmax lambda * qt[i*] * P(d|t_i*) + (1 - lambda) * sum_{i != i*} qt[i] * P(d|t_i); update seats s_i += P(d*|t_i) / sum_j P(d*|t_j).
- Guarantee: none; heuristic.
- Evidence [SRC, Table 1, sub-topics aspects]: Cumulative Proportionality (CPR) QL 0.4012, MMR 0.4018, xQuAD 0.4534, PM-1 0.4462, PM-2 0.4771. With search-engine suggestions: MMR 0.4016, xQuAD 0.4242, PM-2 0.4696. Also: MMR "helps and hurts about the same number of queries (35/33), MMR can only provide slight improvement"; MMR's CPR gain does not grow with aspect-model accuracy because it ignores aspects.
- When it beats MMR: you want counts proportional to a known distribution over aspects (e.g. keep claim types or subjects proportional to a target mix).

### 3.4 DPP and fast greedy MAP (Kulesza & Taskar 2012; Chen, Zhang, Zhou NeurIPS 2018)
- Monograph: https://arxiv.org/abs/1207.6083 (read via https://arxiv.org/pdf/1207.6083). P(Y) proportional to det(L_Y); quality-diversity decomposition L_ij = q_i * phi_i^T phi_j * q_j. det(L_Y) = squared volume of the parallelepiped, so near-duplicates (linearly dependent rows) get ~0 probability: diversity is global in the span, not just nearest-neighbour. [SRC]
- MAP is NP-hard, hard to approximate; log det is submodular but **non-monotone**; the monograph's DUC experiment uses greedy "which seems to work well" despite no monotone guarantee, and reports dpp-greedy ROUGE-1F 38.96 vs a trained MMR-style baseline lower (Table 4; exact baseline number not extracted). [SRC]
- k-DPP (monograph Section 5): conditions on |Y| = k, giving exact sampling with fixed size; useful for randomized selection (many diverse sets), not MAP. [SRC]
- Chen et al.: https://arxiv.org/abs/1709.05135 (full text read). Greedy step: j = argmax log det(L_{S+j}) - log det(L_S), computed incrementally via Cholesky updates: O(M^3) preprocessing for the full kernel, then **O(N^2 M)** to return N items; sliding-window variant **O(w N M)**. Tunable version replaces the objective by theta * r_i + (1 - theta) * (logdet gain). [SRC]
- Evidence vs MMR [SRC]: Netflix Prize / Million Song, N=20, relevance-diversity trade-off curves: "DPP enjoys the best relevance-diversity trade-off" among MMR, max-sum diversification, entropy, coverage; DPP runtime avg/99th pct 0.73/1.75 ms vs MMR 0.23/0.50 ms on Netflix (Table 1). 4-week online A/B test in a movie recommender: "DPP performed better compared with systems without diversification algorithm or with MMR" (the numeric table was not extracted). Theta about 0.7 gave best MRR in their sweep.

### 3.5 Submodular summarization (Lin & Bilmes ACL 2011)
- https://aclanthology.org/P11-1052.pdf (read). "A class of submodular functions for document summarization."
- F(S) = L(S) + lambda * R(S): coverage L(S) = sum_{i in V} min(sum_{j in S} w_ij, alpha * sum_{k in V} w_ik) (saturated; facility location, sum_i max_{j in S} w_ij, is the other form they mention) plus a clustered **diversity reward** R(S) = sum_k sqrt(sum_{j in S cap P_k} r_j). Budgeted greedy (cost-scaled) gives a (1 - 1/sqrt(e))-ish guarantee with a knapsack constraint, (1 - 1/e) for cardinality, if F monotone submodular. [SRC]
- Results [SRC, Table 1, DUC-04 ROUGE-1 F]: sum-similarity coverage 32.44; L1 saturated 38.65; R1 diversity reward 37.81; L1 + lambda R1 **38.90**; best DUC-04 system 37.94. Beat their own earlier MMR-styled submodular system (38.39 F).
- Beats MMR when you want to represent a whole pool (summary) rather than avoid near-neighbours.

### 3.6 Facility location, k-center, core-sets
- Facility location: f(S) = sum_i max_{j in S} sim(i, j): monotone submodular, greedy (1 - 1/e) (Nemhauser). Appears in Lin & Bilmes as a coverage variant. [SRC: Lin & Bilmes mention; guarantee from Nemhauser-Wolsey-Fisher 1978 as cited in Borodin et al.]
- k-center: greedy farthest-point is a 2-approximation for metric k-center (stated in GIST's abstract-level text as the basis for their warm-up; also Sydow for max-min dispersion). Core-set data selection (Sener & Savarese, ICLR 2018, k-center greedy) [UNVERIFIED: I did not fetch it this session].
- GIST (NeurIPS 2025): max-min diversification with monotone submodular utility g(S) + lambda * div(S), approximation 1/2 - eps, with 2/3 - eps bound for the Rust crate's metric case (README). [SRC: abstract excerpt, divsel README]

### 3.7 Portfolio theory of IR (Wang & Zhu, SIGIR 2009)
- https://ir.webis.de/anthology/2009.sigirconf_conference-2009.16 [UNVERIFIED beyond abstract-level summary; full PDF fetch timed out]. Mean-variance ranking: pick d maximizing E[rel(d)] - b * w_d * var(d) - 2b * sum_{selected} w_{d'} * w_d * sigma_d sigma_d' rho(d,d'), where b = risk preference, rho = correlation between document relevance scores. The formula is from my memory of the paper, not from a page I read. [EXT/UNVERIFIED]
- Notable: it is MMR-shaped (relevance minus correlation to chosen docs, with a variance term for uncertain relevance). A critique (Zuccon, Azzopardi, van Rijsbergen) says it violates the Probability Ranking Principle under non-trivial conditions (search summary, not read).
- Relevance for us [EXT]: the variance term is the principled place to put "this base fact might be wrong" for compare claims.

### 3.8 Max-sum / max-min dispersion
Covered in 2.2 and 2.3. Greedy edges (Hassin et al.) and vertex greedy (Ravi et al.) are 2-approx for max-sum with metric distances; farthest-point greedy 2-approx for max-min. All are relevance-free or fold relevance into the metric (d' = w(u) + w(v) + 2*lambda*d(u,v)). [SRC]

### 3.9 Sliding-window variants in recommender systems
Chen et al. 2018 (above): the diversity requirement is only among nearby positions in a feed; complexity O(w N M) for DPP; they also adapt MMR and MSD to consider only the last w-1 items for a fair comparison, and DPP wins on nDCG-vs-diversity under that setup. [SRC] The idea (windowed redundancy) maps to "don't let the same base fact appear in more than w nearby claims" [EXT].

---

## 4. Practice

### 4.1 How MMR is exposed in libraries and engines
| System | API | Defaults / semantics | Source |
|---|---|---|---|
| LangChain core (`VectorStore.max_marginal_relevance_search`) | `k`, `fetch_k`, `lambda_mult` | `fetch_k=20`, `lambda_mult=0.5`; k default 4 in the helper `maximal_marginal_relevance`; "0 = max diversity, 1 = min diversity". Implementation: first pick = argmax relevance; then score = `lambda_mult*query_score - (1-lambda_mult)*max(sim to selected)`; raw cosine, no normalization. | https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/vectorstores/base.py (read lines 660-730), `utils.py` (read) |
| LlamaIndex | `vector_store_query_mode="mmr"`, `vector_store_kwargs={"mmr_threshold": x}`; prefetch factor kwarg named differently across stores/versions (`mmr_prefetch_factor`, `mmr_prefetch_k`) | docs: "as the threshold goes to 1... MMR turned off; lowering prefers diverse". Backend-dependent. | https://developers.llamaindex.ai/python/examples/vector_stores/simpleindexdemommr ; search results [semantics of prefetch UNVERIFIED] |
| OpenSearch 3.3+ | `ext.mmr {candidates, diversity}`; needs system-generated search-processor factories enabled | diversity: 0 = relevance, 1 = diversity. Defaults not stated in blog. Benchmarks p50 (cohere-1m k-NN): k=10, 10 cand +13%; k=10, 100 cand +95.5%; k=50, 100 cand **+247%**. Only k-NN/neural queries (no bool/hybrid yet). | https://opensearch.org/blog/improving-vector-search-diversity-through-native-mmr/ |
| Elasticsearch | `diversify` retriever, `type: mmr`, `lambda` (required, 0-1), `size` (default 10), `rank_window_size` (default 10) | "Higher values weight similarity to the query vector more heavily". Preview since 9.3. | https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/diversify-retriever |
| Qdrant | `Mmr {diversity, candidates_limit}` on nearest-neighbour query | diversity 0-1, default 0.5, higher = more diverse; `candidates_limit` defaults to `limit`, so by default MMR can only reorder (course page: https://qdrant.tech/course/beginners/module-6/diversity-mmr/index.md); per the LangChain issue, qdrant computes `lambda = 1 - diversity` | search summary [candidates_limit default read only via search summary]; https://github.com/langchain-ai/langchain/issues/39052 |
| Weaviate 1.39 | `balance` (0-1) + `limit` for hybrid / near_* | **default balance 0.0 = full diversity**, 1.0 = pure relevance; not on BM25 or multi-vector. | https://weaviate.io/blog/weaviate-1-39-release ; PR https://github.com/weaviate/weaviate/pull/11903 (title only) |
| Vespa | **No native MMR** found. Offers `diversity` in rank-profile (attribute + min-groups), grouping, match-phase diversity, `collapsefield`. | MMR would be a custom Searcher. | https://docs.vespa.ai/en/querying/result-diversity.html |
| Milvus | Only through LangChain wrapper `max_marginal_relevance_search` (client-side). No native MMR found. | | https://reference.langchain.com/python/langchain-milvus/vectorstores/milvus/Milvus/max_marginal_relevance_search |
| PyTerrier-DR | `diversity` module (MMR, others) | not read | https://pyterrier.readthedocs.io/en/stable/ext/pyterrier-dr/diversity.html |

Takeaway: four mutually inconsistent conventions for the same knob. lambda_mult/balance/lambda: 1 = relevance. diversity (Qdrant, OpenSearch): 1 = diversity. Weaviate defaults to maximum diversity. [SRC]

### 4.2 Empirical evidence in RAG and retrieval, 2022-2026
- **"Finding the Right Balance: Relevance and Diversity in LLM Retrieval", arXiv 2610.09412** (https://arxiv.org/html/2610.09412; first 100k chars read). Compares k-NN, MMR (lambda 0.3/0.5/0.7/0.9), Maxmin, greedy DPP, and the authors' RNG-Score on HotpotQA, 2Wiki, MuSiQue, NQ-Open, five BEIR tasks. Findings [SRC]: on clean pools "diversification harms relevance, evidence coverage and answer quality". HotpotQA (bge-m3): k-NN S-Recall@5 78.7, EM 50.8; MMR 48.1 (lambda 0.3), 58.6 (0.5), 72.8 (0.7). BEIR NDCG@10 at lambda 0.5: SciFact 64.1 -> 52.9, FiQA 41.7 -> 29.6, TREC-COVID 66.1 -> 37.0, ArguAna 38.3 -> 0.2, Touche 25.2 -> 10.9. Cross-encoder+MMR Recall@5: 2Wiki 90.6 -> 71.0, MuSiQue 74.3 -> 52.7. MMR **helps when near-duplicates are injected**: k-NN S-Recall falls to 52.7, tuned MMR reaches 74.9; crossover at a measured near-duplicate-pair fraction of ~0.0012 to 0.0030. MMR has lowest minimax regret (6.3 pts vs ~22 for k-NN). Claim: apply diversity selectively.
- **DF-RAG: Query-Aware Diversity for RAG** (EACL 2026 Findings, https://aclanthology.org/2026.findings-eacl.150.pdf). Builds on MMR, argues a fixed lambda for all queries is suboptimal and estimates per-query diversity. Abstract read; numbers not extracted. [SRC for framing only]
- **VRSD** (arXiv 2407.04573, https://arxiv.org/abs/2407.04573): claims MMR's manually tuned parameter causes "optimization fluctuations and unpredictable retrieval results"; proposes a parameter-free NP-complete formulation with a heuristic; claims to beat MMR and k-DPP on geometric metrics and LLM-simulated judgments. [SRC abstract; self-reported]
- **CCBQP** (arXiv 2604.02554): see 2.1. Dominates MMR/DPP on Pareto frontier, up to 22.9x faster than MMR (self-reported).
- Classical IR: Dang & Croft 2012 (above): MMR ~ neutral vs plain query-likelihood on TREC Web 2009/2010, xQuAD/PM-2 clearly better when aspects are known. Chen et al. 2018: DPP > MMR in an A/B test.

### 4.3 Real-user experience (threads and issues)
1. **LocalLens #34, "Tune MMR lambda (0.5 -> 0.7)"** (https://github.com/SujieZong/LocalLens/issues/34, 2026-07-17, read). A RAG over 482 legal chunks: RAGAS answer-relevancy 0.25, context-recall 0.36. Root cause "MMR evicting the single most-relevant chunk": lambda=0.5 drops the right "deposit limits" chunk even at K=8; lambda 0.7 and 0.85 and plain similarity keep it. "Raising K does NOT help... lambda is the lever." Also noted earlier hybrid-BM25 A/B read flat because MMR was silently on. Real case where MMR hurt, at the LangChain default.
2. **langchain-ai/langchain #39052**, "QdrantVectorStore.as_retriever(search_type='mmr') inverts lambda_mult semantics" (https://github.com/langchain-ai/langchain/issues/39052, open, 2026-07-24, read). Root cause: the wrapper passes `lambda_mult` straight into Qdrant's `Mmr(diversity=...)`, but Qdrant computes `lambda = 1 - diversity`. Users tuning toward relevance get diversity.
3. **BERTopic #1142**, "MaximalMarginalRelevance gives poor results when combined with PartOfSpeech" (https://github.com/MaartenGr/BERTopic/issues/1142, 2023, read). MMR had no visible effect because it re-selects from a candidate set the same size as the output; maintainer: raise candidate count (`top_n_words=30`) and use diversity 0.9, because 1 "would not produce meaningful diversification"; a hard-coded `top_n_words=10` was also a bug. Shows the candidate-pool-size trap.
4. HN: Show HN Goodreads recommender (https://news.ycombinator.com/item?id=45862593): author added MMR "which should give you much less repetitive recommendations" (a one-line positive report, 2025-11). Elastic's MMR blog also posted to HN (item 49107189, no discussion). Only thin HN signal found.
5. Reddit r/MachineLearning "[D] Forcing diversification in similarity search" (https://www.reddit.com/r/MachineLearning/comments/14vzjbo/d_forcing_diversification_in_similarity_search/) surfaced by search but **Reddit blocked every fetch (403)**, so contents NOT read. Likewise a Medium post "I added MMR after cross-encoder reranking: it fixed one multi-hop RAG case, not the original" (https://blog.gopenai.com/i-added-mmr-after-cross-encoder-reranking-it-fixed-one-multi-hop-rag-case-not-the-original-dd8324d59a1b) returned 403; title only. [UNVERIFIED]

---

## 5. Efficient implementation

### 5.1 Incremental greedy with a cached max-sim vector
[SRC for complexity, EXT for the cache detail]: naive recomputation is O(k^2 n) similarity evaluations; keeping m[i] = max_{s in S} sim(i, s) and, after picking s*, m[i] = max(m[i], sim(i, s*)) is O(n) per step: **O(n k) similarity lookups total, O(k n d) if each similarity is a d-dimensional dot product** (arXiv 2604.02554 gives O(knd)). LangChain's own helper recomputes the full similarity of every candidate to the selected set each iteration with numpy (read the code), i.e. it is not cached. With a precomputed n x n similarity matrix the loop is O(nk); memory n^2 floats (n = 20k -> 1.6 GB at f32, too much for 6 GiB comfort; use a candidate window or on-the-fly dot products).

### 5.2 Lazy greedy (Minoux 1978)
- Standard for submodular maximization; keep a max-heap of stale upper bounds, re-evaluate only the top. Cited by Mirzasoleiman et al. as "orders of magnitude speedups in practice" (https://arxiv.org/pdf/1409.7938, lines read). Minoux's original paper itself was not fetched. [UNVERIFIED]
- [EXT, my derivation, easy to unit-test]: For MMR specifically the score of item i at step t is lambda*rel_i - (1-lambda)*m_i(t) with m_i(t) nondecreasing, so scores never increase. Lazy evaluation is therefore **exact** for the MMR rule (same output as eager) regardless of the non-monotonicity of F_MMR, because the argmax of nonincreasing-score items can be maintained lazily. It saves a lot when the first picks are far from most items.

### 5.3 Stochastic greedy (Mirzasoleiman, Badanidiyuru, Karbasi, Vondrak, Krause, AAAI 2015)
- https://arxiv.org/abs/1409.7938 (read). Each step evaluates a random sample of size (n/k) log(1/eps); achieves **(1 - 1/e - eps) in expectation** with **O(n log(1/eps)) evaluations**, independent of k. [SRC] Guarantee requires monotone submodular; for MMR (non-monotone) it is a heuristic. [EXT] Gains only appear when n*k is large; for n about 10^4 to 10^5 and k=1000 it is the difference between 10^7-10^8 and ~10^5 similarity evaluations.

### 5.4 Rust crates (checked crates.io API and GitHub; reporting dates, not stars)
| Crate | What | Last commit / publish | Notes |
|---|---|---|---|
| `mmr-rerank` 0.1.0 (https://github.com/MukundaKatta/mmr-rerank) | MMR reranker `mmr(&rel, &pair, lambda, k)`; zero deps; MIT/Apache | repo created 2026-05-16, last commit **2026-06-13** (CI workflow), 22 downloads | Takes a full n x n pairwise matrix; trivially re-implementable (~20 lines); not worth depending on |
| `divsel` 0.1.0 (https://github.com/Redrum624/divsel) | GIST max-min diversification with submodular utility (NeurIPS 2025); rayon; Python bindings | created 2026-08-21, last commit **2026-09-19**, 14 downloads | Relevant if we want a guarantee (1/2 - eps; 2/3 - eps for true metric) rather than MMR; very new, little usage |
| `ff_k_center` 1.2.2 (https://github.com/LeonSering/fair_and_fast_k_center_clustering) | linear-time fair k-center | published **2024-02-12** | niche (fairness constraint) |
| `qdrant-client` | has `Mmr` struct for server-side MMR | not checked | client only |
No Rust crate found for DPP greedy MAP, lazy greedy, stochastic greedy or general submodular selection (searched crates.io for "determinantal point process", "submodular", "lazy greedy", "k-center", "diversity reranking").

---

## 6. What I searched for and did NOT find (or could not read)

- Gollapudi & Sharma full PDF: Southampton mirror blocked by an Anubis proof-of-work page; Stanford and iw3c2 mirrors read only via exa excerpts. Axioms and max-sum / max-min remarks are verified; the "third objective" remark numbering is ambiguous.
- Wang & Zhu SIGIR 2009 full text: fetch timed out; only abstract-level secondary summaries. The mean-variance formula in 3.7 is from memory.
- Minoux 1978, Sener & Savarese 2018 (core-set), Hassin-Rubinstein-Tamir: not fetched; guarantees quoted via citing papers.
- Reddit threads (all 403): contents unknown. Medium/gopenai post (403). HN had almost no substantive MMR discussion (searched Algolia stories and comments for "maximal marginal relevance", "MMR reranking diversity", "MMR lambda").
- GitHub issues search returned many "feature: add MMR" tickets in agent/RAG projects but few failure reports besides the three in 4.3. No GitHub issue about lambda **scale mismatch** specifically; the scale mismatch point is my derivation from the formula.
- Qdrant `candidates_limit` default and diversity direction: confirmed only through a search summary plus the LangChain issue text; the Qdrant doc page itself not read. OpenSearch default values for `candidates`/`diversity`: not stated in the blog; the docs page text was truncated by the fetcher.
- Chen et al. A/B test numeric table (watch-time improvements): not extracted. DF-RAG numeric results: not extracted.
- No peer-reviewed proof of any approximation ratio for the exact MMR rule. The only formal statements are: non-monotone submodular (Lin & Bilmes 2011) so Nemhauser does not apply; and Borodin et al.'s guarantee for a related sum-penalty greedy.
- No Rust DPP / lazy-greedy / submodular crate; I did not search GitHub for non-published Rust repos.

---

## 7. Implications for VERIDYCT (my extrapolation, not sourced)

1. MMR's single-neighbour penalty is a poor fit for compare claims that share base facts: two claims sharing a base fact may be dissimilar in text yet "redundant" in dependency. Define sim over **dependency sets** (Jaccard on base fact ids) rather than text embeddings, or use a coverage objective (facility location, IA-Select-style: each base fact is a "category", gain = new facts covered, penalty for reliance on low-confidence facts).
2. Fold "risk" in as in portfolio theory: relevance term = confidence of claim, penalty = overlap in base facts weighted by fact error probability. A wrong base fact then costs by its blast radius.
3. For evidence-row selection when labelling: arXiv 2610.09412 says do NOT diversify by default; apply MMR only if the pool has measurable near-duplicate density, and keep lambda >= 0.7.
4. Use the cached-max-sim lazy greedy (5.1, 5.2), implement ourselves (about 30 lines); no crate is worth the dependency.
5. Because the scoring formula is unpublished, treat diversity as a tie-breaker above a confidence floor rather than trading confidence for diversity (PM-2 and Dang & Croft show diversity methods only pay when the aspect model is accurate).

---

## References (all URLs fetched or surfaced this session)

- Carbonell & Goldstein 1998: https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf ; https://doi.org/10.1145/290941.291025 ; https://aclanthology.org/X98-1025/
- Gollapudi & Sharma 2009: https://dl.acm.org/doi/10.1145/1526709.1526761 ; https://theory.stanford.edu/~aneeshs/papers/diversification.pdf ; https://archives.iw3c2.org/www2009/proceedings/pdf/p381.pdf
- Borodin, Lee, Ye / Borodin, Jain, Lee, Ye: https://arxiv.org/abs/1203.6397 ; https://www.cs.toronto.edu/~bor/Papers/RD-talg-submit-rev.pdf
- Sydow (dispersion survey): http://users.pja.edu.pl/~msyd/papers/sydow-bigTriangle-ma14.pdf
- xQuAD: https://archives.iw3c2.org/www2010/proceedings/www/p881.pdf ; https://eprints.gla.ac.uk/44352
- IA-Select: https://www.microsoft.com/en-us/research/publication/diversifying-search-results/ ; https://khoury.northeastern.edu/home/vip/teach/IRcourse/5_eval_userstudy/other_notes/diversifying-wsdm09.pdf
- PM-2: https://ciir-publications.cs.umass.edu/getpdf.php?id=1050
- DPP monograph: https://arxiv.org/abs/1207.6083 ; Chen, Zhang, Zhou: https://arxiv.org/abs/1709.05135
- Lin & Bilmes 2011: https://aclanthology.org/P11-1052.pdf
- Wang & Zhu 2009: https://ir.webis.de/anthology/2009.sigirconf_conference-2009.16
- Stochastic greedy: https://arxiv.org/abs/1409.7938
- GIST: https://proceedings.neurips.cc/paper_files/paper/2025/file/41febbd2bd4bd1f268ada869cee28e44-Paper-Conference.pdf ; https://github.com/Redrum624/divsel
- mmr-rerank: https://github.com/MukundaKatta/mmr-rerank
- CCBQP diversity retrieval: https://arxiv.org/html/2604.02554v1
- RAG evidence: https://arxiv.org/html/2610.09412 ; https://aclanthology.org/2026.findings-eacl.150.pdf ; https://arxiv.org/abs/2407.04573
- Libraries: https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/vectorstores/base.py ; .../utils.py ; https://developers.llamaindex.ai/python/examples/vector_stores/simpleindexdemommr ; https://opensearch.org/blog/improving-vector-search-diversity-through-native-mmr/ ; https://www.elastic.co/docs/reference/elasticsearch/rest-apis/retrievers/diversify-retriever ; https://qdrant.tech/course/beginners/module-6/diversity-mmr/index.md ; https://weaviate.io/blog/weaviate-1-39-release ; https://docs.vespa.ai/en/querying/result-diversity.html
- User threads: https://github.com/SujieZong/LocalLens/issues/34 ; https://github.com/langchain-ai/langchain/issues/39052 ; https://github.com/MaartenGr/BERTopic/issues/1142 ; https://news.ycombinator.com/item?id=45862593 ; https://github.com/qdrant/qdrant/issues/5390
