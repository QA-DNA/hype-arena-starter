# LLM-assisted development (build time only) to improve the classical parser

Status: researcher notes, 2026-10-28. The researcher.md instruction file named in the brief did not exist at the given path, so I followed the brief directly.
Confidence labels: [V] = verified this session (fetched), [M] = cited from memory (arXiv id given, re-check before quoting in the write-up), [E] = my own estimate, not from literature.

## 0. Bottom line

1. Rank 1: **Forward synthetic generation (structured fact -> text), verified by round trip**. Fixes the real bottleneck: 321 attributes over 1,897 rows (about 6 rows per attribute, 1,467 rows have a single fact), and 33% of rows that never name their subject.
2. Rank 2: **LLM-assisted error analysis that ends in rules/features we write and test**. The weak kinds (booleans 0.20, names 0.49, dates 0.64) are limited by rules, not by training data; synthetic data will not fix them alone.
3. Rank 3: **LLM annotators used as auditors/verifiers, not bulk labellers** (measure on gold first; find gold errors; two-model agreement as the synthetic-data filter). Weak supervision (Snorkel-style label model) is only useful in a tiny role.
4. Rank 4: **Counterfactual false-claim / hard-negative generation by value mutation**. Mostly deterministic code; the LLM is only a renderer. Helps the judge only if mutated rows are placed inside a timeline.
Expected total spend about USD 8-12 of the 20 cap. Realistic gain: **parser recall 0.69 -> 0.75-0.80 at equal precision [E]**, which maps to end-to-end 87% -> about 89-90% (the gold-fact ceiling is 92%). No literature number transfers directly; the ablation in section 7 is what decides.

## 1. The legal boundary (what the rules say)

Quotes (README at github.com/QA-DNA/hype-arena-starter, line 22; page https://hype-arena.vercel.app [V]):
- README: "LLMs may help you build your system, and make what it learns from, but the system itself may not be an LLM."
- Page: "Use LLMs to help you build the system and to generate material it learns from." / "Your submitted system may not be an LLM." / "Choose your approach, model design, algorithms, and implementation." / "Don't rely on the live web or facts a pretrained model happens to know." / "The source material is your entire world." / "A claim is only as reliable as the evidence in Hooly's universe."
- Runtime: network "None", 2 CPUs, 6 GiB, 30 min, image 3 GiB; "The build process has network access. The actual run does not."

Reading: LLM-generated training material, LLM-written rules, LLM-discovered features, LLM-audited gold are explicitly fine. The shipped artefact must be a non-LLM system.

Grey areas and the safe interpretation:
| Grey area | Risk | Safe choice |
|---|---|---|
| Shipping a small model trained on LLM-written text (our TF-IDF + logistic regression, gradient boosting) | Low: "material it learns from" is covered | Do it. Keep sklearn-class models. |
| Shipping a distilled small **neural** encoder / transformer | Medium: arguably "an LLM in small"; also 2 CPUs/30 min for 18k rows and 3 GiB image | Avoid; no accuracy case for it here. If wanted, ask first. |
| Embedding LLM-written text in the image (synthetic training set, paraphrase bank used as TF-IDF vocabulary, rule lists written by an LLM) | Low-medium: data is allowed, but a reviewer could say "the system is a lookup of LLM outputs" | Ship only the trained model + rule code + small lexicons; keep the generating scripts and a seed/provenance file in the repo; do not ship an LLM-written "answer table" keyed on test-like rows. |
| Using LLM world knowledge to decide truth (e.g. "is 71 languages plausible") | Violates "facts a pretrained model happens to know" | Never use LLM verdicts as labels for true/false/unsure. Use LLMs only for form (text -> facts), never for truth. |
| Task 2 (1,000 new TRUE claims) produced by an LLM at build time | Unclear: is the claim generator part of "the system"? | Ask organizers. Safe route: programmatic generator from lexicon + timeline, LLM only to paraphrase surface text at build time. |
| Forks are public; prompts and synthetic data committed | None, but note it | Fine, and helps "follow your work". Do not commit .env. |

Questions for the organizers (send now, one message): (1) Is a trained sklearn model/rule set whose training data and rules were produced with LLMs acceptable, including LLM-written text committed in the repo and image? (2) Is a small non-LLM neural classifier acceptable, or only classical models? (3) For Task 2, may claims be pre-generated at build time by a script that used an LLM for wording, or must the submitted system generate them? (4) Are the 20 sample rows released at 09:00 on 29 Oct allowed as additional training/tuning data? (they said the run input has no form column, so only as smoke test).

## 2. Technique 1 (rank 1): forward synthetic generation with round-trip verification

**What.** Run the task backwards: take a structured fact set (subject, attribute, value), ask an LLM for sentences that express exactly it. The label is correct by construction, unlike extraction. Josifoski et al., "Exploiting Asymmetry for Synthetic Training Data Generation: SynthIE" (arXiv:2303.04132) [V abstract]: generating text from structure is easier than the reverse; 1.8M synthetic examples took small models +57 micro-F1 over the prior state of the art on closed IE. (That is a zero-real-data regime with a huge label space, so it overstates our gain; direction of the effect is what transfers.) Related: Self-Instruct (Wang et al., arXiv:2212.10560) [M], ZeroGen (Ye et al., arXiv:2202.07922) [M]; survey: Tan et al., "LLMs for Data Annotation and Synthesis" (arXiv:2402.13446) [M]. Counter-evidence: Li et al., "Synthetic Data Generation with LLMs for Text Classification: Potential and Limitations" (EMNLP 2023, arXiv:2310.07849) [M]: synthetic-only training lags real data, gap grows with task subjectivity and low diversity; mixing with real data helps most when real data is scarce. Our task is objective and real data is scarce per attribute, which is the favourable case.

**Why it fits.** Data: 1,897 rows, 321 attributes, kinds quantity 1028/money 268/duration 229/name 209/percent 201/boolean 174/version 128/date 165. Gold has a fixed lexicon (62 subjects, 13 events, attribute list per subject), so the **space of (subject, attribute, kind) is enumerable**: we can generate coverage for every pair, including ones with 1-3 real examples. The test rows come from the same generator, so surface-form diversity (negation, "Despite everything, ...", headline style, subject-less sentences) is the missing piece, not new attributes.

**Three generators, in order of value:**
a. *Coverage generation*: for each lexicon (subject, attribute), sample 6-10 values from the empirical value distribution of that attribute (or a kind-appropriate sampler), ask for 4 diverse single sentences in styles seen in practice. About 600-900 pairs x 2 calls. 
b. *Paraphrase of real rows* (already piloted: 3,279 outputs from 490 rows, 79-87% kept). Scale to all train rows with 4-5 paraphrases from 2 models.
c. *Context windows*: 3-6 consecutive sentences where the first names the subject and later ones say "it", "the app", "its price", or nothing. This targets the 33% of rows that never name their subject; the parser's context logic (CTX_ROWS=10) can only be trained/tuned on such sequences. Without this, synthetic single sentences push the model further toward "subject always named".

**Verification filters (the part that decides quality):**
- Deterministic value parser round trip is good for quantity/money/percent/version/duration. **But it is circular for names, dates, booleans** (exactly the weak kinds): a filter by our own parser keeps only sentences the parser already reads, so the new data cannot teach what it misses (selection bias). The existing tools/augment.py `accept()` does this. Fix: for name/date/boolean, require agreement of **two different LLM extractors** (round-trip: a second model sees only the generated sentence and the attribute menu and must return the same value), and for booleans a negation check by a third prompt. Keep the gold value as target, never the extractor's.
- Reject if subject name missing when the generator was told to include it; reject new numbers/names not in the fact; dedupe by normalised text with value masked (otherwise 40 near-identical "The price of X is N" dominate).
- Keep a "hardness" tag: items the current parser gets wrong are the most valuable; after round 1, oversample generation for attributes/kinds where CV recall is lowest (cheap active learning).

**Mixing and diminishing returns.** Literature rule of thumb [M, Li et al.; Ding et al. arXiv:2212.10450]: gains rise fast to roughly 1-3x real data per class, then flatten or reverse when synthetic style dominates. Plan: real weight 1.0, synthetic sample_weight 0.3-0.5, test ratios synth:real = 0, 1, 2, 4 per attribute (cap per-attribute synthetic count so rare attributes are lifted to about 15-20 total examples, frequent ones get few). Stop at the knee of the CV curve. TF-IDF + LR saturates quickly; more than about 5k synthetic rows is unlikely to pay [E].

**Cost** (tokens ~15 per 53-char sentence; prompts about 300-600 tokens with a style guide, JSON out). Pilot measured about USD 0.0001/row for 3 paraphrases. Generator a: 1,500 calls x (500 in + 300 out) = 0.75M in + 0.45M out; Qwen2.5-72B = 0.28 + 0.18 = about USD 0.5; DeepSeek-V3.1 = 0.21 + 0.45 = USD 0.7. Generator b at 1,900 rows x 2 models x 5 paraphrases: about USD 0.8. Generator c: 800 windows x 1.2k tokens = about USD 0.6. Verifier calls (two extractors over about 15k candidates, 300 in/60 out): about USD 3 with Mistral-Small + Qwen-72B. **Total about USD 5-6.**

**Pitfalls.** (1) LLM voice homogeneity: vary model (Qwen, DeepSeek, Mistral, gpt-oss) and temperature; the pilot already mixes three. (2) Style drift to "assistant-y" prose vs. terse corporate text of Hooly: put 5 real rows of the same attribute in the prompt as style exemplars (from the train fold only). (3) Leakage: generate **per source row/pair and tag `src`**; training may use synthetic rows only whose `src` is in the training fold (assert in code). Coverage generation (a) has no src row, but its value samples must not be drawn from the held-out fold's values if the exact held-out sentences could be reproduced; tag it with fold-independent seed and, in CV, regenerate-or-filter any synthetic sentence with normalised text equal to a held-out real row. (4) Values: sample dates inside the Hooly year and keep spellings (12 January 2026 / 2026-01-12 / Jan 12) varied or the date parser stays brittle. (5) Do not let the LLM invent attributes outside the lexicon.

## 3. Technique 2 (rank 2): LLM-assisted error analysis -> rules and features we implement

**What.** Take the parser's errors on CV out-of-fold predictions (never on the training fit), cluster them, have an LLM name the failure modes and propose rules/features, then **we** implement and test each on grouped CV. Literature: LLM-generated labeling functions / rule proposals in weak supervision (Smith et al., "Language Models in the Loop," arXiv:2205.02318 [M]; Guan et al., "Can LLMs design accurate label functions?", arXiv:2311.00739 [M, verify id]); error-slice discovery work (Eyuboglu et al., Domino, arXiv:2203.14960 [M]) shows slice descriptions in natural language are useful. Evidence of LLM-proposed rules beating hand rules is thin; treat the LLM as a fast brainstorming and triage partner, not an oracle.

**Why it fits.** Booleans 0.20, names 0.49, dates 0.64 are rule problems: e.g. which phrases flip a boolean (negation scope: "no region beyond Europe" -> region_outside_europe = false), which verbs mark a person-attribute (presented by, led by -> executive_owner), which date role (joined/launched/ends). These are small, enumerable pattern families in a fixed lexicon. 33% no-subject rows are a context-resolution problem (pronouns, "the app", topic carried from previous sentences), which an LLM can characterise from examples but cannot replace our inference.

**Recipe.**
1. Run 5-fold grouped CV of the current parser; dump all fact-level errors (FP, FN, wrong value, wrong attribute, wrong subject) with row text, previous 3 rows, gold, parsed. About 600-1,000 errors.
2. Cheap triage: send errors in batches of 40 with the instruction "assign each error to one of these categories or propose a new one; give the minimal regex/cue that would fix it". Cost: 1,000 errors x 250 tokens = 0.25M in + 0.1M out with DeepSeek-V3.1 = under USD 0.2 per pass. Even 5 passes with different models (self-consistency, Wang et al. arXiv:2203.11171 [M]) cost USD 1-2. Rule of thumb: about USD 0.2 per 1,000 rows analysed, plus about 3x for a long-context reasoning model if used.
3. Humans read the category histogram, pick the top 5-8 categories by error mass, implement each as a rule/feature, accept only if grouped-CV fact F1 improves with paired bootstrap interval excluding 0.
4. Ask the LLM for **adversarial probes per rule**: 20 sentences that should and should not trigger it (cheap unit tests; also feed good ones into the synthetic pool tagged `probe`).
5. Re-run on residual errors; two or three rounds are the realistic limit.

**Expected gain.** Highest per-dollar of all four, but depends on engineer time. For booleans (0.20) and names (0.49) I would expect the largest absolute move (+10-25 pts on those kinds) [E]; for the overall fact recall maybe +3-6 pts. Pitfalls: LLM-suggested rules overfit the 1,897 rows (fix: accept only on out-of-fold errors, evaluate on folds the rule was not designed from); regexes proposed from a handful of errors miss the long tail; time sink if we accept every proposal.

## 4. Technique 3 (rank 3): LLM annotators as auditors/verifiers; weak supervision in a small role

**Honest framing.** For this task bulk LLM silver-labelling has **no unlabeled pool**: the 18k real input rows are not available before the run (only 20 sample rows arrive on 29 Oct 09:00). Offline pseudo-labelling of the real universe is impossible; the only unlabelled text we can have is LLM-generated text, which is already labelled by construction. So the annotator's value is three narrower things:

a. **Measure annotator quality on gold before trusting it** (needed anyway because it is the verifier in section 2): run each candidate model (Qwen2.5-72B, DeepSeek-V3.1, Mistral-Small-24B, gpt-oss-120b) on a 400-row stratified gold subset with a prompt containing the subject/attribute menu (from the lexicon), the value schema, and 6 few-shot examples drawn from outside the subset. Score at fact level with exactly the repo's canonicaliser (as in `canon()` in tools/augment.py): P/R/F1 per kind, per-attribute. Use that to pick verifier models and to decide kinds where the LLM is better than our parser (then its output is a *feature source for building rules*, never shipped). Literature calibration [M]: LLMs match or beat crowd annotators on classification (Gilardi et al., PNAS 2023, arXiv:2303.15056; Alizadeh et al. arXiv:2307.02179), but trail supervised models on **structured** IE (Han et al., "Is Information Extraction Solved by ChatGPT?", arXiv:2305.14450; Wadhwa et al., arXiv:2305.05003 shows few-shot LLMs near but below fine-tuned RE) and show run-to-run inconsistency (Reiss, arXiv:2304.11085). Expect an open 72B model with schema + few-shot to reach fact F1 0.8-0.9 on this clean templated text [E]; the measurement will tell.
b. **Gold audit / noise detection**: where all 3 models agree with each other and disagree with gold, inspect by hand. Gold forms may miss facts (parser "precision 0.91" may be underestimated if gold is incomplete) or contain slips. Confident-learning idea (Northcutt et al., arXiv:1911.09491 [M]). Cost: 1,897 rows x 3 models, about 2k tokens each with menu and few-shot: 3.8M in per model; Qwen-72B about USD 1.5, DeepSeek about USD 1.1 (+0.2 out), Mistral-Small about USD 0.7: **about USD 4 for the full gold set, USD 1 for a 400-row subset**. Start with the subset; run the full set only if the subset shows annotators >= 0.85 fact F1.
c. **Verifier for synthetic data** (section 2) by two-model agreement. Multi-model voting is the standard denoiser for LLM-generated data (Ding et al., arXiv:2212.10450 [M]; self-consistency).

**Weak supervision (Snorkel).** Data programming (Ratner et al., NeurIPS 2016, arXiv:1605.07723; Snorkel, VLDB 2018, arXiv:1711.10160; Snorkel DryBell, arXiv:1812.00417 [M]) learns label-function accuracies without gold when you have large unlabelled data and no labels. We have the reverse: gold on all practice rows, no unlabelled real pool. A label model adds nothing over simple supervised stacking here, and it is a new dependency for no gain. Use only: (i) weights for combining {rules, LR, LLM-roundtrip votes} on synthetic data; a 3-vote majority with abstain is enough, no Snorkel package. (ii) If the organizers permit the 20 sample rows as unlabeled tuning input, nothing to learn from 20 rows. **Not recommended: Snorkel/generative label model, Wrench-style benchmarks (arXiv:2109.11377).**
Self-training / pseudo-labelling: impossible at run time, and at build time there are only practice rows (already gold) and 20 sample rows (too few). Skip.

**Pitfalls.** Positional/format bias in extraction prompts; temperature 0; cache by hash of (model, prompt); parse failures counted as misses; use the lexicon attribute menu in the prompt or open models invent attribute names; non-determinism of hosted models means keep raw outputs in data/ for reproducibility.

## 5. Technique 4 (rank 4): counterfactual false claims and hard negatives

**What.** Create false rows by mutating a true row's value (price +/- step, wrong date, wrong name from the same attribute's pool, boolean flip), after Kaushik et al. (counterfactually-augmented data, arXiv:1909.12434 [M]) and contrast sets (Gardner et al., arXiv:2004.02709 [M]). Hard negatives for the **parser**: sentences containing numbers/names that are NOT facts of the row (a sibling attribute's value, a date mentioned as context, a competitor name), so the parser learns not to extract them. 

**Why it ranks last.** (1) Mutation is deterministic code; the LLM only helps with rendering natural wording, which technique 1 already provides. (2) For the **parser**, a false claim is parsed exactly like a true one (same facts, different value), so mutated false rows add attribute/value examples but no new signal beyond technique 1. (3) For the **judge** (timeline evidence + gradient boosting), rows are judged against evidence from other rows and dates; a lone synthetic row has no timeline, so it cannot train the judge. It can only help if injected into a *synthetic timeline* (several rows with dates where a value changes over time, with true and mutated sentences). That is a real data-engineering job (about 2-3 hours) with unclear payoff; the judge already gets 92% with gold facts, so the headroom is the parser. (4) Class balance: 277 false vs 1,581 true; mutated falses could correct the prior, but real-row 'lie' patterns (pages that "lie" with plausible values) differ from random mutations: random mutation produces easy falses, which can inflate judge training accuracy and **hurt calibration of the confidence** that scoring depends on.
Do it only for: hard negatives for parser (cheap, deterministic), and if time remains, a synthetic timeline test to check the judge's behaviour on value changes (as evaluation probe, not training).
Cost: negligible (<USD 1).

## 6. What would NOT help (and why)

- **LLM zero-shot true/false/unsure labels** as training targets: the truth is defined by the Hooly timeline; an LLM has no access to it and the rules forbid pretrained knowledge. Worse than the existing judge and violates the spirit.
- **Fine-tuning/shipping a neural encoder distilled from an LLM**: grey-area legally, heavy on 2 CPUs/30 min/18k rows, and the sentences are short templated text (about 53 chars) where TF-IDF + rules is competitive. Not worth the risk.
- **Snorkel label models, pseudo-labelling at run time, self-training on test**: no unlabeled pool, no network, no benefit over gold.
- **Massive synthetic scaling (tens of thousands of rows)**: saturation at the knee, style homogenisation, and model-collapse style degradation if later rounds train on earlier synthetic outputs (Shumailov et al., arXiv:2305.17493 [M]). Cap per attribute.
- **Using the LLM as a second opinion on values at run time**: forbidden (system may not be an LLM).
- **Paraphrase-only augmentation filtered by our own parser**: already piloted; as argued it is circular for the weak kinds. Keep it, but it is the lowest-value synthetic source.
- **Chasing LLM annotation of gold rows to "fix" them wholesale**: audit only; humans decide.

## 7. Evaluation protocol (honest)

- **Real rows only for evaluation.** Never synthetic, never LLM-annotated rows. Gold rows with possibly audited labels evaluated against the original gold; corrections reported separately.
- **Grouped CV.** 5-fold `GroupKFold`, groups = page/date window (consecutive rows share context and timeline; random row-level splits leak neighbour context to the parser's CTX_ROWS and to the judge). Also report a second grouping by (subject, attribute) leave-pattern-out as a stress test: if test rows contain unseen surface templates, this is the pessimistic bound.
- **Synthetic isolation, enforced by code**: each synthetic row has `src` (real row id) or `pair` (lexicon pair) plus a generator id; training function receives the fold's train ids and filters synthetic rows by `src in train_ids`; unit test asserts no overlap. For coverage-generation rows (no src), additionally drop any synthetic sentence whose normalised form (digits masked) equals a held-out real row.
- **Metrics.** Parser: fact-level precision/recall/F1 per kind and per attribute frequency bucket (<5, 5-20, >20 examples). End-to-end: label accuracy and the confidence-weighted score on out-of-fold rows, parser output fed to the judge trained on gold facts of the training fold only.
- **Ablation grid** (the actual decision): real only; +paraphrases; +coverage; +context windows; +all; synth:real in {1,2,4}; with/without LLM-roundtrip filter for names/dates/booleans. Paired bootstrap (1,000 resamples over groups) for each delta; accept only when the 95% interval excludes zero.
- **Do not tune on the 20 sample rows**: smoke test only.
- **Reproducibility**: every LLM call goes through tools/featherless.py (priced, logged, capped); cache raw outputs to data/synth/*.jsonl with model, prompt hash, temperature, seed; `make synth` script regenerates the filtered set deterministically from the cache.

## 8. Cost-bounded plan (cap USD 20; planned about USD 9-12), about 10 hours

Check first: Featherless limits concurrent requests by plan and model size (large 70B-class models may allow only 1-2 concurrent calls) [M, verify on the dashboard]; that drives wall-clock more than cost. Use Mistral-Small-24B and gpt-oss-20b for bulk, Qwen-72B/DeepSeek for verification and hard cases.

| Step | What | Tokens | Est. cost | Time |
|---|---|---|---|---|
| 0 | Measure existing paraphrases' effect: retrain parser on train-fold + their `src`-matched paraphrases, grouped CV | 0 | 0 | 45 min |
| 1 | Annotator quality on 400 stratified gold rows x 3 models (section 4a) | about 2.4M in/0.2M out total | about USD 1.0 | 1 h |
| 2 | Error dump + LLM triage, 2 passes, 2 models (section 3) | about 0.6M in/0.25M out | about USD 0.6 | 1 h + 3 h to implement rules |
| 3 | Coverage generation (a) + context windows (c) | about 1.8M in/1.2M out | about USD 1.5 | 1.5 h |
| 4 | Paraphrases at scale (b), 2 models x 5 | about 1M in/0.9M out | about USD 0.8 | 30 min |
| 5 | Round-trip verifiers (two models) over about 15k candidates | about 4.5M in/0.9M out | about USD 3 | 1 h |
| 6 | Ablation grid + pick mixing ratio | 0 | 0 | 1.5 h |
| 7 | Second generation round targeted at the lowest-recall attributes/kinds | about 1M in/0.7M out | about USD 1 | 45 min |
| 8 | Optional: full-gold annotator audit (section 4b) | about 11M in/1M out total | about USD 4 | 1 h |
| Reserve | retries, prompt iterations | | about USD 3 | |

Order matters: step 0 and step 2 are the cheapest and tell us whether data (synthetic) or rules is the bottleneck, before spending on 3-7. If step 0 shows no gain from 3,279 verified paraphrases, expect modest gains from the rest of technique 1 and shift hours to technique 2.

Per-model price anchors (USD/M in/out from the brief): Qwen2.5-72B 0.37/0.40; DeepSeek-V3.1 0.285/1.00; Mistral-Small-24B 0.175/0.29. Output-heavy jobs favour Qwen/Mistral (DeepSeek output is 2.5x Qwen's).

## 9. Risks specific to this project

- 6 rows per attribute means CV estimates per attribute are noisy; report kind-level and bucket-level numbers, not per attribute.
- If the hidden rows are produced by the same templated generator that made the practice rows, the biggest win is covering its template families; LLM paraphrase diversity may exceed the generator's actual variety and dilute the real distribution. Weight synthetic below real and verify by the ablation.
- Gold completeness: if gold forms omit facts that sentences contain, "precision 0.91" is a floor; the audit (4b) quantifies it.
- Judge training uses gold facts but runs on parsed facts (92 vs 87): consider training the judge on **parsed out-of-fold facts** (error-aware), a no-LLM change that may gain more than any synthetic data; mention to the architecture researcher.

## 10. Sources

- Josifoski et al., SynthIE, arXiv:2303.04132 [V: https://www.arxiv.org/abs/2303.04132]
- Repo README and https://hype-arena.vercel.app [V]
- Ratner et al., Data Programming, arXiv:1605.07723; Snorkel, arXiv:1711.10160; Snorkel DryBell, arXiv:1812.00417 [M]
- Hinton, Vinyals, Dean, Distilling the Knowledge in a Neural Network, arXiv:1503.02531 [M]; Hsieh et al., Distilling Step-by-Step, arXiv:2305.02301 [M]
- Gilardi et al., ChatGPT outperforms crowd workers, arXiv:2303.15056; Alizadeh et al., arXiv:2307.02179; Reiss, arXiv:2304.11085 [M]
- Ding et al., Is GPT-3 a Good Data Annotator?, arXiv:2212.10450; Wang et al., Want to reduce labeling cost? GPT-3 can help, arXiv:2108.13487 [M]
- Han et al., Is IE solved by ChatGPT?, arXiv:2305.14450; Wadhwa et al., arXiv:2305.05003 [M]
- Wang et al., Self-Instruct, arXiv:2212.10560; Ye et al., ZeroGen, arXiv:2202.07922; Li et al., arXiv:2310.07849; Tan et al. survey, arXiv:2402.13446 [M]
- Kaushik et al., arXiv:1909.12434; Gardner et al., arXiv:2004.02709; Wei and Zou, EDA, arXiv:1901.11196 [M]
- Shumailov et al., Curse of Recursion, arXiv:2305.17493; Northcutt et al., Confident Learning, arXiv:1911.09491 [M]
- Smith et al., Language Models in the Loop, arXiv:2205.02318; Guan et al. (LF design) arXiv:2311.00739 (verify); Eyuboglu et al., Domino, arXiv:2203.14960; Wang et al., Self-Consistency, arXiv:2203.11171 [M]
- Local: hype/parse.py, tools/augment.py (circular accept() filter), tools/featherless.py (priced and capped client), data/synth/paraphrases.jsonl, data/practice.csv (counts above computed this session)
