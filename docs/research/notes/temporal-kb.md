# Temporal knowledge base: storage, as-of queries, change over time

Raw report from the 2026-10-28 knowledge base research, kept as written by the worker so nothing is lost. The curated version, with verdicts reconciled against the contract and the measured results, is [the knowledge base research](../knowledge-base.md).

- **Author:** W2, Claude Sonnet 5.5 research worker.
- **Scope:** S1 as-of query, S3 change over time, storage and Rust crates.
- **Tools:** free tools only (WebSearch, WebFetch, GitHub, crates.io, arXiv); no paid research service.
- **Citations:** Citations the worker marked "not verified" were checked afterwards where possible; the verified URLs are listed in [the notes index](README.md#verified-citations).
- **Note:** the `scallop` crate on crates.io was not confirmed to be the Scallop language. Datalog engines were rejected for the runtime anyway.

## TLDR
1. Our data is already atomic and typed. A plain in-memory `HashMap<(subject, attribute), Vec<Observation>>` plus a sorted-by-date step-function resolver handles 25k facts in milliseconds. No database, Datalog or graph engine is needed for storage or as-of queries.
2. The useful ideas from the literature are Wikidata-style interval qualifiers, TeCoRe-style temporal constraints (functional attributes mean one value per time point), and source reliability weighting. Implement them as about 300 lines of hand-written Rust. Every heavyweight engine (PSL, MLN, ProbLog, Scallop, clingo) is either not Rust or not worth its integration risk by 29 Oct 11:00.
3. For change modelling, a per-key 2-state or segmentation DP over anchored observations (Viterbi on a step function with a switch penalty) is a small hand-written port of about 80 lines. It is the PELT/HSMM idea without a crate. `changepoint` and `augurs-changepoint` target numeric series and fit categorical values poorly.
4. Temporal KG embeddings (TComplEx and similar) are IDEA-ONLY. 2.4k propositions over 514 keys is too small, and the real signal is in the typed values and dates.
5. Model "staleness" as an empirical hazard: P(value still valid | distance to the nearest anchor). It comes straight from the 1,897 practice labels and feeds the S6 calibration.

Counts below come from crates.io and GitHub on 2026-10-28. Items I could not verify are listed at the end.

---

### Wikidata statement qualifiers (data model, 2012+)
- Link(s): not fetched this session (no URL verified).
- What it does: each statement carries start time (P580), end time (P582) and point in time (P585) qualifiers. This is a valid-time interval per (subject, attribute, value).
- Steps: S1, S3, S4.
- Pros: it is the right mental model: `Fact{key, value, valid_from, valid_to: Option, support: Vec<row_id>}`. Open-ended intervals mean "still current".
- Cons: it assumes clean statements. Our intervals are inferred from noisy page observations.
- Rust: `struct` of about 30 lines.
- Fit here: derive intervals from observations, with the interval boundary being unknown between two observation dates.
- Verdict: ADOPT as the data model. Insanity 1.

### CoTS, Coupled temporal scoping (paper, WSDM 2012)
- Link(s): not verified (Semantic Scholar rate-limited, DBLP errored).
- What it does: infers validity intervals of relational facts from time-stamped text with a graph-based label propagation. It couples facts through constraints such as "a person has one spouse at a time".
- Steps: S1, S2, S3.
- Pros: the constraint coupling is exactly our "functional attribute" idea. It handles missing end times.
- Cons: it is built for web-scale extraction, and the original code is not public as far as I know (unverified).
- Rust: port ~150 lines for the propagation (a scoring pass over neighbouring keys).
- Fit here: borrow the idea that evidence at date d supports the interval around d and decays outside it.
- Verdict: IDEA-ONLY. Insanity 2.

### T-YAGO / YAGO2 temporal, YAGO 4.5 (KB, 2011 / 2023)
- Link(s): https://arxiv.org/abs/2308.11884 (YAGO 4.5, verified). YAGO2/T-YAGO not fetched.
- What it does: attaches time spans to facts, with begin and end dates.
- Steps: S1.
- Pros: confirms the interval-per-fact representation.
- Cons: no algorithms we can reuse.
- Rust: none needed.
- Fit here: citation only.
- Verdict: IDEA-ONLY. Insanity 1.

### Timely YAGO and TemporalWiki (KB / benchmark)
- Link(s): TemporalWiki https://arxiv.org/abs/2204.14211 (2022, verified). Timely YAGO not found, see the unverified list.
- What it does: TemporalWiki is about LM updating, not KB reasoning.
- Steps: none.
- Verdict: REJECT, off-topic (generative LM focus).

### TeCoRe, temporal conflict resolution (paper, AAAI 2017; demo VLDB 2017)
- Link(s): not verified.
- What it does: resolves conflicts in uncertain temporal KGs with weighted rules (MLN/PSL) plus hard temporal constraints (disjointness, precedence). The output is a maximum-weight consistent subset of facts.
- Steps: S2, S3.
- Pros: it is the formulation of our problem: pick one true value per key per time among conflicting observations.
- Cons: the machinery is MLN/PSL on the JVM. Inference needs an ILP/MaxSAT solver, which is heavy.
- Rust: reimplement the constraint as greedy or DP selection over intervals. For a single functional key this is weighted interval scheduling, about 60 lines and exact in O(n log n).
- Fit here: per key, choose non-overlapping value-intervals maximising total evidence weight (anchored labels weigh most).
- Verdict: ADOPT the idea, not the system. Insanity 2.

### Dylla et al., temporal-probabilistic database (paper, VLDB 2013)
- Link(s): not verified.
- What it does: probabilistic DB with temporal facts and deduction rules over intervals, with lineage formulas.
- Steps: S2, S5.
- Cons: the engine is academic with no maintained code. Lineage and confidence computation is #P-hard in general.
- Fit here: the S5 blame logic (a row is false if any proposition is false) is a lineage AND. It is trivial for us because rows are conjunctions of atoms, so P(row true) = product (assuming independence).
- Verdict: IDEA-ONLY. Insanity 1.

### Allen interval algebra / temporal constraint consistency (algorithm)
- What it does: 13 relations between intervals with composition tables.
- Steps: S2, S3.
- Pros: a clean vocabulary for "A ended before B started".
- Cons: our needs are met by two comparisons (start < end, adjacent or overlapping).
- Rust: about 40 lines for an enum. No crate verified.
- Verdict: IDEA-ONLY, use only for disjointness checks. Insanity 1.

### Probabilistic Soft Logic, PSL (system, Java)
- Link(s): https://github.com/linqs/psl, 315 stars, last push 2024-06-10.
- What it does: hinge-loss MRFs with convex MAP inference over soft truth values.
- Steps: S2, S6.
- Pros: calibrated soft scores, rules are declarative.
- Cons: JVM only, idle since mid-2024, and it breaks the "standalone Rust application" constraint. Startup and memory cost under 6 GiB are risky.
- Rust: none. The convex inference could be ported by hand, but the effort is large.
- Verdict: REJECT for runtime. Python `pslpython` (not verified this session) for labs only. Insanity 4.

### Markov Logic, Alchemy / Tuffy / RockIt
- Link(s): none verified. No crates.io hit for `tuffy`.
- What it does: weighted first-order logic with MAP/marginal inference.
- Cons: Java/C++ research code, old, ILP-based grounding.
- Verdict: REJECT. Insanity 5.

### ProbLog (system, Python)
- Link(s): the `problog/problog` GitHub path returned 404, so the repository was not verified.
- What it does: probabilistic logic programming with exact weighted model counting.
- Cons: Python, and exact inference scales poorly past a few thousand facts. No Rust.
- Verdict: REJECT for runtime; possible lab oracle on small slices. Insanity 4.

### Scallop (Rust neurosymbolic Datalog with provenance semirings)
- Link(s): https://github.com/scallop-lang/scallop, 520 stars, last push 2026-06-26, not archived. The `scallop` crate on crates.io is v0.0.30, 33,852 downloads, updated 2025-12-13.
- What it does: Datalog with differentiable provenance (top-k proofs, min-max, add-mult probabilities).
- Steps: S2, S5, S6.
- Pros: Rust, alive, has probabilistic Datalog.
- Cons: the crate name `scallop` is not confirmed to be this project (I only saw the version number). The compiler is a Python-and-Rust hybrid, API stability is unknown, and integration eats days.
- Rust: native, if the crate is actually the library.
- Fit here: could express "value valid at date" rules, but a hand loop is shorter.
- Verdict: IDEA-ONLY. Insanity 4.

### ascent (Rust Datalog macro)
- Link(s): crates.io `ascent` 0.8.1, 697,735 downloads, updated 2026-08-29; repo s-arash/ascent, 592 stars, pushed 2026-08-29.
- What it does: Datalog embedded in Rust through proc macros, with lattices and parallel evaluation.
- Steps: S1, S5, S7.
- Pros: compile-time, fast, can express relation-chasing rules (the entity-graph link followed over time).
- Cons: compile-time macro errors slow iteration, and rules are fixed at build time.
- Fit here: relation claims (follow a link, then read the attribute) can be a few Datalog rules. A plain `for` loop is equivalent.
- Verdict: TRY only if rules multiply. Otherwise skip. Insanity 2.

### crepe, datafrog (Rust Datalog)
- Link(s): `crepe` 0.2.0, 837,525 downloads, updated 2025-12-14; `datafrog` 2.0.1, 5,138,754 downloads, updated 2026-10-12.
- What it does: crepe is a macro Datalog like ascent. datafrog is a lightweight engine used inside rustc (Polonius).
- Verdict: IDEA-ONLY. Insanity 2.

### differential-dataflow / timely
- Link(s): `differential-dataflow` 0.25.1, 534,113 downloads, updated 2026-07-15; repo TimelyDataflow/differential-dataflow, 3,026 stars, pushed today.
- What it does: incremental computation over changing collections.
- Cons: far too heavy for 25k facts, and its learning curve is steep.
- Verdict: REJECT. Insanity 4.

### Nemo (Rust rule engine, TU Dresden knowsys)
- Link(s): https://github.com/knowsys/nemo, 309 stars, pushed 2026-10-20, latest release v0.10.1. The crates.io name `nemo` is an unrelated 2015 crate; `nemo-physical` and `nemo-cli` returned no hit.
- What it does: Datalog and existential rules with a fast columnar engine, with CLI and library.
- Cons: the crates.io publication is unclear, so a git dependency would be needed.
- Verdict: IDEA-ONLY. Insanity 3.

### egglog (equality saturation)
- Link(s): `egglog` 3.0.0, 169,643 downloads, updated 2026-08-19.
- What it does: Datalog plus e-graphs for equality reasoning.
- Fit here: the "same entity under another name" problem could use it, but a union-find does the same job.
- Verdict: REJECT. Insanity 3.

### Soufflé
- Not verified; C++ Datalog compiler with no Rust bindings. Verdict: REJECT.

### clingo / telingo (ASP with time)
- Link(s): https://github.com/potassco/clingo, 856 stars, pushed 2026-10-27. telingo: 27 stars, last push 2024-06-24.
- What it does: ASP solver. telingo adds temporal operators for step-wise programs.
- Pros: a very strong exact solver for consistency.
- Cons: C++ with Python bindings. The Rust bindings are unverified, and a CPU-only container would need a native build. Telingo's time model is integer steps, which does not match our dates.
- Verdict: REJECT for runtime. Insanity 4.

### PELT / changepoint detection (algorithm and crates)
- Link(s): `changepoint` 0.15.0, 201,358 downloads, updated 2025-10-20. `augurs-changepoint` 0.10.3, 92,423 downloads, updated 2026-10-27 (augurs 0.10.3, 84,123 downloads). `pelt` 0.3.4, 2,118 downloads, updated 2026-08-13. Python: `ruptures` (deepcharles/ruptures, 2,103 stars, pushed 2026-10-06).
- What it does: finds break points in a numeric series by minimising cost plus a penalty.
- Steps: S3.
- Pros: gives the shape of the DP I described.
- Cons: designed for numeric noise, but our observations are categorical values (price tags) with few points per key (about 4.7 per key). Penalty tuning with 514 keys is easy to overfit.
- Rust: crates exist, but a hand-written categorical segmentation DP (about 80 lines) fits better.
- Verdict: TRY the DP idea, not the crates. Insanity 2.

### BOCPD, Bayesian online changepoint detection (paper, Adams and MacKay 2007)
- Link(s): https://arxiv.org/abs/0710.3742 (verified). No dedicated Rust crate found by name.
- What it does: online run-length posterior with a hazard function.
- Pros: gives a probabilistic "change happened between d1 and d2" that feeds the S6 confidence directly.
- Cons: it needs a likelihood model per series. With sparse categorical data, a simple Dirichlet-categorical gives it, about 100 lines.
- Verdict: TRY as the confidence layer on top of the DP. Insanity 3.

### HMM / HSMM for value timelines (algorithm)
- Link(s): Rust `hmmm` 0.2.0, 5,330 downloads, last update 2020 (stale). `linfa` 0.8.1, 2,037,594 downloads, updated 2025-12-23 (the HMM piece is in linfa-hmm, not verified).
- What it does: hidden state = true value, observations = page claims with a liar emission model. Viterbi gives the MAP timeline, and the forward-backward pass gives marginals.
- Steps: S2, S3, S6.
- Pros: integrates source reliability (emission noise per page) and gives calibrated per-date probabilities.
- Cons: the hidden-state space per key is its small candidate set (2 to 4 values), so Viterbi is trivial.
- Rust: port ~100 lines, no crate needed. Semi-Markov duration is optional.
- Fit here: probably the best single model. Candidates = values seen for the key; transitions monotone in time (switch penalty); emissions = reliability of the page.
- Verdict: ADOPT. Insanity 3.

### Survival / hazard models for staleness (algorithm)
- Link(s): none needed. Rust: `statrs` 0.19.1, 44,512,631 downloads, updated 2026-08-11, for distributions.
- What it does: models how long a value stays valid and how evidence decays with distance in time.
- Steps: S1, S6.
- Pros: a nonparametric step estimate from the practice labels (Kaplan-Meier style) is about 40 lines and directly drives "unsure" (no nearby evidence).
- Cons: only about 514 keys, with right-censoring everywhere.
- Verdict: TRY. Insanity 2.

### Monotone attributes (heuristic)
- What it does: constraints like headcount and customers growing, versions increasing, launch dates fixed.
- Steps: S2, S3.
- Fit here: a cheap pre-classification per attribute (increasing / fixed / free) mined from practice data prunes impossible orderings in the DP. About 30 lines.
- Verdict: ADOPT. Insanity 1.

### Temporal KG embeddings (TTransE, HyTE, TA-DistMult, TComplEx / TNTComplEx)
- Link(s): TNTComplEx comes from Lacroix et al., ICLR 2020; I did not verify it (the arXiv search returned a different paper). A 2023 paper, "Temporal Smoothness Regularisers for Neural Link Predictors", https://arxiv.org/abs/2309.09045 (verified), covers the regularisation side.
- What it does: learns entity, relation and time embeddings for link prediction.
- Cons: needs GPU-style training and large data. Our data is 2.4k propositions, typed values (money, dates) that embeddings do not model, and the runtime is 2 CPUs with no pretraining.
- Rust: no maintained crate; a port would be large.
- Verdict: IDEA-ONLY. Insanity 5.

### Plain in-memory map (storage)
- What it does: `HashMap<(SubjectId, AttrId), Vec<Obs>>`, each Vec sorted by date, with binary search for the as-of lookup.
- Steps: S1, S7.
- Pros: 25k facts is about 1 MB. No dependencies, deterministic, trivial to test.
- Cons: none at this scale. The entity graph needs an adjacency list (`Vec<Link>` per entity).
- Verdict: ADOPT. Insanity 1.

### Interval trees (rust-lapper, intervaltree, iset)
- Link(s): `rust-lapper` 2.0.0-beta.1, 1,691,272 downloads, updated 2026-08-20. `intervaltree` 0.2.7, 3,011,791 downloads, last update 2021-11-04. `iset` 0.3.3, 601,090 downloads, updated 2026-05-09.
- What it does: stabbing queries (which intervals contain date d).
- Cons: with about 5 intervals per key, a linear scan beats any tree.
- Verdict: REJECT, unnecessary. Insanity 1.

### DuckDB (`duckdb` crate)
- Link(s): `duckdb` 1.20000.0, 5,322,554 downloads, updated 2026-10-22; repo duckdb/duckdb-rs, 981 stars, pushed today.
- Cons: bundled build is slow and large, and adds nothing for 25k rows. Fine as a lab tool only, through Python.
- Verdict: REJECT in the Rust core. Insanity 2.

### SQLite (`rusqlite`)
- Link(s): `rusqlite` 0.41.0, 137,773,996 downloads, updated 2026-10-24.
- What it does: embedded SQL, with window functions for as-of joins.
- Verdict: REJECT for runtime (no need). Insanity 1.

### Oxigraph (RDF/SPARQL, RDF-star)
- Link(s): `oxigraph` 0.5.13, 914,102 downloads, updated 2026-10-22; repo 2,004 stars, pushed 2026-10-23.
- What it does: Rust RDF store with SPARQL 1.1 and RDF-star for statement-level annotations like valid time.
- Cons: SPARQL has no native temporal joins, so every as-of query becomes a hand-written filter anyway.
- Verdict: REJECT. Insanity 3.

### CozoDB (Datalog with time travel)
- Link(s): `cozo` 0.7.6, 119,521 downloads, last update 2023-12-11. The repo's last push is 2024-12-04, 4,137 stars. A fork crate `cozo-ce` 0.7.13-alpha.3 was updated 2024-12-08.
- Cons: effectively unmaintained for 22 months. The time-travel feature is per-relation validity, nice but unneeded.
- Verdict: REJECT (stale). Insanity 3.

### Kuzu (embedded graph DB)
- Link(s): repo kuzudb/kuzu is archived (archived=true), last push 2025-10-10. Crate `kuzu` 0.11.3, last update 2025-10-10, 313,652 downloads.
- Verdict: REJECT, archived. Insanity 3.

### XTDB (bitemporal DB)
- Link(s): repo xtdb/xtdb, 3,092 stars, pushed today.
- What it does: native bitemporal storage (valid time and system time), SQL:2011 style.
- Cons: JVM, and no Rust client was verified. Total overkill.
- Verdict: IDEA-ONLY. Insanity 4. The bitemporal idea is useful in one narrow sense: valid time = the claimed date, and the page date is the "as-known-at" time. We can ignore transaction time.

### petgraph (entity graph)
- Link(s): `petgraph` 0.8.3, 579,160,130 downloads, updated 2025-09-30.
- What it does: graph structures and algorithms.
- Fit here: the entity graph is small, and a time-stamped adjacency map is enough. petgraph only helps for cycle detection in links.
- Verdict: TRY only if needed. Insanity 1.

### Date handling with precision (jiff / chrono / time)
- Link(s): `jiff` 0.2.38, 247,837,045 downloads, updated 2026-10-06. `chrono` 0.4.45, 922,661,671 downloads, updated 2026-06-04. `time` 0.3.55, 1,017,261,403 downloads, updated 2026-08-01.
- What it does: calendar date arithmetic.
- Pros: for partial dates (2025-11 vs 2025-11-04) represent them as `[start, end]` day intervals, e.g. `2025-11` = [11-01, 11-30]. Then equality is "interval contains" and comparisons are interval comparisons. About 40 lines on top of any of the three crates.
- Verdict: ADOPT jiff (modern API, strong civil-date support), or store dates as an integer day number and skip the crate. Insanity 1.

---

## Not found / unverified
- DBLP and Semantic Scholar queries failed (errors or rate limits), so I did not confirm links for CoTS (WSDM 2012), TeCoRe (AAAI 2017 / VLDB 2017), Dylla et al. (VLDB 2013), YAGO2/T-YAGO, HyTE (EMNLP 2018) or TNTComplEx. The descriptions are from memory.
- "Timely YAGO" was not found by any search.
- Wikidata qualifier docs were not fetched this session.
- The `scallop` crate (v0.0.30) was not confirmed to be the Scallop language library.
- The `problog/problog` repo path returned 404, and `pslpython` was not checked.
- No Rust BOCPD crate was found by name. `hmmm` last updated 2020, and I did not verify `linfa-hmm`.
- Nemo's crates.io publication status is unclear.
- No 2024-2026 temporal-KG reasoning papers were verified in the time available.
- I did not benchmark any engine on 25k facts. Throughput claims are reasoning, not measurement.
