# Research: graph approaches and a bigger synthetic dataset

Date: 28 Oct 2026. No code changed; no experiment was run except the small read-only counts marked **[measured]** (done with `./.venv/bin/python` on `data/practice.csv`, `data/lexicon.json`, `bench/parsed_date.json`). Anything marked **[inference]** is my own reasoning, and **[unverified]** means I could not confirm it from a primary source.

## Summary (10 lines)

1. **Would a graph help the judge? No, not measurably.** Judge A on gold facts is 0.92 and on parsed facts 0.87; the 5-point gap is parsing, and no graph method fixes rows the parser emits nothing for.
2. **Would a graph help claim generation? Yes, but as a plain dict of per-(subject, attribute) timelines plus a link table, not as a graph library or embeddings.** It is needed for `relation`, `at_event` and `compare`.
3. **Would a graph help the parser? Not a KG. Page-level context would.** [measured] 33% of practice rows (635/1,897) never name their facts' subject; subject+attribute recall is 0.75 where the subject is named but 0.31 where it is not. 87% (512/588) of those rows share a subject with the previous row on the same date.
4. Temporal KG embeddings (TComplEx, DE-SimplE) and KG fact-checking (FactKG, knowledge streams) do not fit: they predict entities from big graphs, we have about 500 observed facts, mostly numeric literals.
5. Truth discovery (TruthFinder, Dawid-Skene) is already in our judge B; it adds little unless the parser improves.
6. Allen algebra, PSL/Markov logic, Datalog: not worth the hours here. Hand-written rules in Python cover the same ground.
7. **Would a bigger synthetic dataset help? Probably a little, and only for the parts the parser fails to read, not for rows that lack subject context.** The rules allow it (README and site quotes in section 3a).
8. The main risks are circularity (a generator written from the parser's own rules), distribution shift and leakage. Honest evaluation means real held-out practice rows, grouped by date, with templates mined from training folds only.
9. My guess is +2 to +5 points of parser recall from synthetic data **[inference, no source]**, against more for neighbour-row context. A one-day test with a learning-curve check (section 3d) decides it.
10. Order of work: (1) subject carry-over from neighbour rows, (2) boolean/negation and name/date rules from practice templates, (3) timeline dict and claim generator, (4) synthetic data only if the learning curve says the parser is data-starved.

---

## 1. Graph approaches, one by one

Our measured state (`tasks/results.md`): gold facts -> A 0.920, B 0.908; parsed facts -> A 0.868, B 0.868. Parser precision 0.94, recall 0.61 (boolean 0.13, name 0.34, date 0.59).

| # | Approach | What it is | Needs | Fits 2 CPU / 6 GiB / 30 min / no net? | Helps the judge? | Verdict |
|---|---|---|---|---|---|---|
| a1 | TComplEx / TNTComplEx | ComplEx tensor decomposition extended with time for temporal KB completion (link prediction under temporal constraints) ([Lacroix et al.](https://arxiv.org/abs/2004.04926)) | Many (s, r, o, t) quadruples; entity-valued objects | Runs, but needs a quadruple set we do not have | No | Skip |
| a2 | DE-SimplE | Static SimplE plus a diachronic function giving entities time-dependent embeddings ([Goel et al.](https://arxiv.org/abs/1907.03143)) | Same | Same | No | Skip |
| a3 | TKG completion in general | Methods grouped by how timestamps are used ([Cai et al. survey](https://arxiv.org/abs/2201.08236)) | Same | Same | No | Skip |
| a4 | FactKG | 108k claims, five reasoning types (one-hop, conjunction, existence, multi-hop, negation), verified by reasoning on a KG ([Kim et al., ACL 2023](https://arxiv.org/abs/2305.06590)) | A ready KG and claims already linked to it | Needs a KG built from our noisy parse | No (taxonomy only) | Skip |
| a5 | Knowledge streams | Unsupervised network-flow fact checking: find a flow from subject to object in a KG ([Shiralkar et al.](https://arxiv.org/abs/1708.07239)) | A background KG of real-world entities | Needs an external KG; none exists here | No | Skip |
| a6 | FEVER | Claim verification against Wikipedia ([Thorne et al.](https://arxiv.org/abs/1803.05355)) | Evidence retrieval corpus | Our "evidence" is the universe | Only as a source of mutation ideas (section 3b) | Use ideas only |
| b | Allen interval algebra | 13 mutually exclusive relations between two time intervals ([Allen 1983, CACM 26(11), 832-843](https://cse.unl.edu/%7Echoueiry/Documents/Allen-CACM1983.pdf); I confirmed the citation, not every relation definition) | Intervals with start and end | Trivial | No: our bracketing evidence already is "value held before and after the date" | Skip the algebra; keep the idea |
| c1 | TruthFinder | Iterate source trust and fact confidence; sources with many true facts are trusted, facts from trusted sources are believed ([Yin, Han, Yu, TKDE 2008](https://doi.org/10.1109/TKDE.2007.190745)) | Several sources per fact | Trivial | Already covered by judge B | No new gain |
| c2 | Dawid-Skene | EM estimate of per-observer error rates when the true label is unknown ([Dawid and Skene 1979, DOI 10.2307/2346806](https://doi.org/10.2307/2346806)) | Multiple noisy labellers per item | Trivial | Same | No new gain |
| c3 | Truth discovery survey | Merge conflicting claims by estimating source reliability ([Li et al.](https://arxiv.org/abs/1505.02463)) | Same | Trivial | Same | Reference only |
| c4 | Entity resolution and relation propagation | Link a value that is itself an entity (e.g. CTO = Richard Hendrix) to that entity's own facts | Alias table (the lexicon) | Trivial | Slightly, as features (see section 2) | **Do**, as dict lookups |
| d | PSL / Markov logic | Soft first-order rules compiled into a hinge-loss MRF; scalable MAP inference ([Bach et al., JMLR 2017](https://arxiv.org/abs/1505.04406)) | Rules plus a package; I did not check current Python packaging **[unverified]** | Probably, but extra dependency in a 3 GiB image | Marginal | Skip: rules as GBM features do the same job |
| d2 | Datalog-style engine | Declarative rules over facts **[no primary source fetched]** | Engine | Python dict joins suffice at 20k rows | No | Skip |
| e1 | Data programming / Snorkel | Write labelling functions, model their accuracies and correlations without ground truth ([Ratner et al. 2016](https://arxiv.org/abs/1605.07723), [Snorkel, VLDB 2017](https://arxiv.org/abs/1711.10160)) | Labelling functions | Concept fits; do not add the package | Useful for the **parser** (attribute and negation cues as labelling functions over the 18k unlabelled rows) | Concept yes, package no |
| e2 | Calibration | Temperature scaling fixes miscalibration with one parameter ([Guo et al. 2017](https://arxiv.org/abs/1706.04599)) | A validation fold | Trivial | Our isotonic step already does this | Keep what we have |
| e3 | Conformal prediction | Distribution-free guaranteed prediction sets ([Angelopoulos and Bates](https://arxiv.org/abs/2107.07511)) | Calibration set | Trivial | No: it gives sets, while the score wants a probability; I did not verify the exchangeability assumption from the page | Skip |

**Why graphs do not address the bottleneck [inference, from `tasks/results.md`]:** Judge A loses 5 points from gold to parsed facts, and the gap between judges (A vs B vs rules) is under 1 point on parsed facts. A better reasoner over the same missing facts cannot recover them. The 40% of facts that the parser misses give the judge the prior (85% true), which is exactly the fallback it already uses.

**One graph-flavoured idea that is cheap and could add to the judge [inference]:** cross-fact constraints between a row's own facts and other rows' facts, for example "Holdan joined 2026-01-12" implies every row on a date before that is false if it says he runs something. These are timeline rules (algorithms.md option C), not a graph engine.

---

## 2. Would a graph help us? Direct answer by step

All counts below are **[measured]** on practice.csv (2,402 facts in 1,897 rows) and `data/lexicon.json`.

### (i) Judging: no

See section 1. The only plausible gain is from a few cross-entity rules, and the oracle-parse ceiling is 0.92 anyway.

### (ii) Claim generation: yes, as a dict (not a graph package)

| Count | Value |
|---|---|
| Name-valued facts | 209 of 2,402 (8.7%) |
| ...whose value is itself a lexicon subject or alias | 40 (19% of name facts) |
| ...whose target has at least one observed fact | 40 of 40 |
| ...whose target person has an observed `joined` fact | 28 of 40 |
| People with a `joined` attribute in the lexicon | 6 (all 6 observed in practice) |
| Link attributes observed (value is a lexicon entity) | reliability_lead 6, venue 6, head_of_workspace 4, head_of_product 4, head_of_security 4, executive_owner 3, cto 3, head 2, run_by 2, owner 2, executive_sponsor 2, chair 1, chairs 1 |
| `cto`, `ceo`, `head_of_*`, `series_a_lead` | all live on the single subject `Hooly`; `cto` has 10 observed facts, `ceo` 7, `series_a_lead` 7 |
| Events in the lexicon | 13, and all 13 are also subjects with their own attributes |
| Events with at least one `date` fact in practice | 7 of 13 (Cloud Next 7 facts, I/O 2026 7, Made by Hooly 5, May 2026 outage 4, Maps Day 2, Gemini Launch Night 1, I/O 2027 1) |
| Events with no `date` fact | 6 (Employee Survey, Q1/Q2/Q3 2026 Results, Q4 2025 Results [has `published`], Sustainability Report [has `published`]) |
| Numeric/date attributes (240) shared by two or more subjects (candidates for `compare`) | 70 |

What this means for the claim types **[inference]**:
- `relation` (subject, link, target, attribute, value): needs "who held `cto` when" and the target's `joined` or `previous_employer` value. With 6 persons, 10 `cto` observations and 28 usable links the supply of true relation claims is small but non-zero; the practice data names only `joined` and `previous_employer` on people, so the (link, attribute) pairs are few. A dict of timelines plus the lexicon alias table is enough.
- `at_event`: needs the event's date (7 of 13 events have one in practice) and another attribute of the same subject with a known value on that date. Limited to those 7 events.
- `compare`: needs same-kind numeric attributes across subjects, with units that convert and the same currency/period (rule in `contracts/claim-forms.md`). 70 shared attributes give a candidate pool; each pair must be checked for a value on 29 Oct 2026.
- None of it needs embeddings, only the timeline already planned in `tasks/plan.md` T8 and the referee.

### (iii) Parser: a KG does not help; neighbour-row context does

| Slice [measured, `bench/parsed_date.json`, subject+attribute recall only] | Gold facts | Recall |
|---|---|---|
| Subject named in the row text | 1,648 | 0.749 |
| Subject not named in the row text | 754 | 0.308 |
| boolean, subject named / not named | 140 / 34 | 0.19 / 0.00 |
| name, subject named / not named | 119 / 90 | 0.53 / 0.12 |
| date, subject named / not named | 122 / 43 | 0.67 / 0.12 |

Also **[measured]**: 635 of 1,897 rows (33%) name none of their facts' subjects; 588 of them have a previous row on the same date, and in 512 (87%) one of the row's fact subjects also appears in the previous row's gold facts. Examples: `Recruiting is run by 4 recruiters.`, `Our 14 sponsors filled the demo hall`, `He begins with a small crew of 4 engineers`.

So the largest parser loss is a context problem (a "current subject" per page), plus boolean negation ("does not ... yet", "no AI answers yet"). Both are fixed with sequential rules or a small per-page tracker, not a graph. Caveat: my check measures only subject+attribute matching, and the parser's current prior-row logic (if any) may differ from what I tested.

---

## 3. A bigger synthetic dataset

### 3a. What the rules allow

- README on GitHub: "LLMs may help you build your system, and make what it learns from, but the system itself may not be an LLM." and "How you build it is yours to decide." ([repo](https://github.com/QA-DNA/hype-arena-starter)).
- Challenge page: "Use LLMs to help you build the system and to generate material it learns from." and "Your submitted system may not be an LLM." ([hype-arena.vercel.app](https://hype-arena.vercel.app)).
- The same pages say the truth is what the universe says and warn against "facts a pretrained model happens to know". The README does not say whether data beyond practice.csv and lexicon.json may be added.
- **Reading:** synthetic training material is allowed, including LLM-written. The constraint is that the material must come from the universe's own facts and style, and the labels must come from our timelines, not from model knowledge. Do not let an LLM invent attribute values that contradict practice; generate from practice facts and lexicon names only. Keep the log of LLM use for the README (plan T19).
- Synthetic data cannot give labels for real unlabelled rows; its only use is training or testing the parser (and optionally the judge's text cues).

### 3b. Established techniques (primary sources)

| Technique | Source | Relevance here |
|---|---|---|
| Grammar-induced recombination: induce a high-precision synchronous grammar from training examples, sample new ones | [Jia and Liang, ACL 2016](https://arxiv.org/abs/1606.03622) | Best match: our rows are template-like sentences paired with structured forms |
| Canonical utterances from a grammar over a schema, then paraphrase | [Wang, Berant, Liang, ACL 2015](https://aclanthology.org/P15-1129/) (the page I fetched had no abstract, so I rely on the title only) | Same idea; we would paraphrase with an LLM at build time |
| Simple augmentation for NER helps most on small training sets | [Dai and Adel, COLING 2020](https://arxiv.org/abs/2010.11683) | Supports mention replacement/swap for the name and subject fields |
| Back-translation of target-side text to create pairs | [Sennrich et al. 2016](https://arxiv.org/abs/1511.06709) (NMT; I am citing the idea only) | Paraphrase via LLM is the practical analogue; not tested for extraction anywhere I verified |
| Mutated claims for FEVER: six types, paraphrase, negation, substitute entity/relation with similar or dissimilar one, more general, more specific; annotators struggled with non-trivial negation | [Thorne et al., FEVER](https://arxiv.org/abs/1803.05355), section 3.1 and appendix A | Template for our false-row builder |
| Counterfactually revised data (minimal edits flipping the label) reduces reliance on spurious features | [Kaushik, Hovy, Lipton, ICLR 2020](https://arxiv.org/abs/1909.12434) | Pairs of (true row, minimally edited false row) |
| Claim-only bias: classifiers can predict FEVER labels without evidence | [Schuster et al. 2019](https://arxiv.org/abs/1908.05267); similar in NLI: [Gururangan et al. 2018](https://arxiv.org/abs/1803.02324) | Warns that generated false claims carry telltale artefacts |
| Programmatic labelling of unlabelled data | [Ratner et al. 2016](https://arxiv.org/abs/1605.07723) | Labelling functions for attribute/negation on the 18k rows |
| Self-training: teacher pseudo-labels unlabelled data, student trained with noise | [Xie et al., Noisy Student](https://arxiv.org/abs/1911.04252) (images; I did not find a verified NLP-extraction source) | Pseudo-label the unlabelled rows only where the parser is confident |
| Training on generated data loses the tails of the real distribution | [Shumailov et al.](https://arxiv.org/abs/2305.17493) | Warns against training only on synthetic text |

### 3c. Concrete risks

1. **Circularity.** If the generator uses the parser's own cue lists, the parser scores itself. Evidence comes only from real held-out practice rows.
2. **Distribution shift.** Real rows contain context-dependence (pronouns, "now", "still"), page headings ("Hooly Docs 2.0"), quotes, and facts with `op`. A template generator tends to emit clean standalone sentences, so the 33% unnamed-subject class is exactly what it does not reproduce unless you generate sequences of rows.
3. **Leakage.** If templates are mined from all 1,897 rows and the test fold is then drawn from the same rows, results are inflated. Mine per training fold. The image may hold practice.csv with forms (contracts/README.md), so check.sh counts are an upper bound.
4. **Label artefacts** in synthetic false rows (Gururangan, Schuster above): a judge's text-cue model will learn "the generator's style", not falsehood. Do not train the judge's labels on synthetic rows; train the parser only.
5. **Hallucinated universe facts** if an LLM writes sentences: restrict it to a fixed structured fact and forbid new values.
6. **Time budget:** a day for a modest gain may compete with the claims work (1,000 valid claims) which is a hard requirement.

### 3d. Recipe for this data

**What to mine from practice.csv (training folds only):**
- Per attribute: the sentence frame around the value, with subject/value slots; per value kind, the surface forms (`3,100`, `three`, `2.9 billion`, `€59 per month`, `12 January 2026` vs `June 9, 2026`, `v2.0`, `over 100`).
- False-row construction, measured: of false-row facts, 202 equal a value that was true on another date (stale) and 158 were never true (invented) (`tasks/algorithms.md`); build false rows in that ratio (stale: swap in another date's value from the timeline; invented: perturb within the attribute's observed range).
- Booleans (174 facts): both polarities per attribute, with the observed cues ("does not ... yet", "no X yet", "now", "still", "remains"); each attribute needs a true and a false rendering, since polarity is the point.
- Multi-fact sentences (27% of rows state 2+ facts: 373 two-fact, 45 three-fact rows).
- **Page sequences:** generate 3 to 8 consecutive rows on one date where later rows drop the subject ("Our 14 sponsors ...", "He ...") with the gold form carrying the earlier subject. This is the highest-value part given the section 2(iii) numbers.
- Distractor sentences with no fact (rows with an empty form do not exist in practice, so also sample non-fact sentences from the 18k unlabelled input for negatives).

**Size:** start with 3 to 5 synthetic rows per real row for each attribute (about 5k to 10k rows), capped so synthetic rows are at most about 70% of training. Weight real rows 2 to 3 times. **[inference, no source]**

**Mixing:** real plus synthetic for the parser's attribute/subject/polarity components; never for judge calibration. Calibrate the judge only on real out-of-fold predictions.

**One-day experiment (decides whether to continue):**
1. Split practice by date into 5 folds (the repo's `bench.common.folds`). For each fold, mine templates from the other 4 only.
2. Baseline: train the parser's learned parts on the 4 real folds. Measure fact precision/recall/F1 per value kind on the held-out fold, plus subject+attribute recall on the "subject not named" slice.
3. **Learning-curve check first (30 min):** train on 25%, 50%, 100% of the real training folds. If recall barely moves, the parser is not data-starved and synthetic data will not help; stop here.
4. If it moves: add synthetic sets one at a time (A: templates with standalone rows; B: A plus page-sequence rows; C: B plus LLM paraphrase) and compare. A paraphrase variant that gives no gain over B is not worth the LLM time.
5. Second check: pseudo-label the 18k unlabelled rows with the parser, keep only high-confidence facts, add them, re-measure (self-training).
6. Report parser F1 by value kind, then judge A's accuracy and log-loss with the new parser (pass 2 in `tasks/results.md`).

**Honest expected benefit [inference]:** A rules-first parser gets most of its gain from rule changes (context carry-over, negation handling) rather than from more training rows; learned components (attribute classifier) may gain a few recall points from templates. I have no source quantifying this for a task like ours, and the learning-curve check is the way to find out. If the parser is mostly rules, synthetic data mostly gives a test set for regression, which is still useful but is not a score gain.

**What could go wrong:** generator and parser agreeing on conventions that the real universe does not follow; precision dropping (the parser's 0.94 is its asset, and synthetic rows can teach over-eager extraction); time lost to LLM prompting that produces unusable or contradicting text; the mixed set hiding that real rows are still missed.

---

## 4. Recommendation (about 20 hours, freeze 29 Oct 11:00)

Ranked by expected gain per hour **[inference]**:

| Rank | Option | Why | Rough cost |
|---|---|---|---|
| 1 | Page-level subject carry-over in the parser (previous row on the same date, pronouns, "Our X", "He/She/It") | Targets the biggest measured hole: 754 facts, recall 0.31 vs 0.75, 87% share a subject with the previous row | 2 to 3 h |
| 2 | Boolean and negation rules, name and date surface forms from practice templates | Boolean recall 0.13, name 0.34, date 0.59; 174 + 209 + 165 facts | 3 to 4 h |
| 3 | Timeline dict, link table, referee, claim generator (fact, change first; then at_event, relation, compare) | Task 2 needs 1,000 valid claims; invalid claims still use slots | already planned, 6 to 8 h |
| 4 | Cross-fact timeline rules as judge features (e.g. person joined date vs row date) | Cheap, but gain is bounded by the 0.92 oracle | 1 to 2 h |
| 5 | Learning-curve diagnostic, then synthetic data only if the curve is steep | Decides item 6 in 30 min | 0.5 h |
| 6 | Synthetic generation with page sequences (and optional LLM paraphrase) | Plausible parser gain, real risk of circularity | 5 to 8 h if justified |

**Do first:** items 1 and 2, then 3 in parallel by a second person.
**Skip:** TKG embeddings, FactKG/knowledge-stream style KG fact-checking, Allen algebra as a library, PSL/Markov logic, Datalog engine, Snorkel as a dependency, conformal prediction, any new judge beyond A+B.

**Experiments that would change my mind:**
- If the learning curve (3d step 3) rises steeply from 50% to 100% of real data, move synthetic data up to rank 2.
- If, after carry-over and boolean rules, parser recall is above about 0.85 but judge accuracy stays under about 0.90, the judge or timeline is the bottleneck and truth discovery over the 18k rows (judge B) deserves more time.
- If the supply of valid `relation`/`at_event` claims is under what we need after the referee, spend time on the link table before anything else.

---

## Sources

Challenge pages: [repo README](https://github.com/QA-DNA/hype-arena-starter), [hype-arena.vercel.app](https://hype-arena.vercel.app); local `contracts/README.md`, `contracts/claim-forms.md`.

- Lacroix, Obozinski, Usunier, Tensor decompositions for temporal KB completion: https://arxiv.org/abs/2004.04926
- Goel et al., Diachronic embedding for temporal KG completion: https://arxiv.org/abs/1907.03143
- Cai et al., Temporal KG completion survey: https://arxiv.org/abs/2201.08236
- Kim et al., FactKG (ACL 2023): https://arxiv.org/abs/2305.06590
- Shiralkar et al., Finding streams in KGs to support fact checking: https://arxiv.org/abs/1708.07239
- Thorne et al., FEVER: https://arxiv.org/abs/1803.05355
- Allen 1983, Maintaining knowledge about temporal intervals: https://cse.unl.edu/%7Echoueiry/Documents/Allen-CACM1983.pdf
- Yin, Han, Yu, TruthFinder (TKDE 2008): https://doi.org/10.1109/TKDE.2007.190745
- Dawid and Skene 1979: https://doi.org/10.2307/2346806
- Li et al., A survey on truth discovery: https://arxiv.org/abs/1505.02463
- Bach et al., HL-MRFs and PSL: https://arxiv.org/abs/1505.04406
- Ratner et al., Data programming: https://arxiv.org/abs/1605.07723
- Ratner et al., Snorkel: https://arxiv.org/abs/1711.10160
- Guo et al., On calibration of modern neural networks: https://arxiv.org/abs/1706.04599
- Angelopoulos and Bates, Conformal prediction intro: https://arxiv.org/abs/2107.07511
- Jia and Liang, Data recombination: https://arxiv.org/abs/1606.03622
- Wang, Berant, Liang, Building a semantic parser overnight: https://aclanthology.org/P15-1129/
- Dai and Adel, Simple augmentation for NER: https://arxiv.org/abs/2010.11683
- Sennrich et al., Back-translation: https://arxiv.org/abs/1511.06709
- Kaushik, Hovy, Lipton, Counterfactually augmented data: https://arxiv.org/abs/1909.12434
- Schuster et al., Towards debiasing fact verification models: https://arxiv.org/abs/1908.05267
- Gururangan et al., Annotation artifacts in NLI data: https://arxiv.org/abs/1803.02324
- Xie et al., Noisy Student: https://arxiv.org/abs/1911.04252
- Shumailov et al., The curse of recursion: https://arxiv.org/abs/2305.17493

Not verified / not fetched: Markov logic (Richardson and Domingos), Datalog, Dechter-Meiri-Pearl temporal constraint networks, Dong et al. dynamic truth discovery, current PSL packaging, FactKG's underlying KG, any primary source quantifying synthetic-data gains for text-to-structure extraction on small template-like corpora.
