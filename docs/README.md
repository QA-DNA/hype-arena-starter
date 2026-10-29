# VERIDYCT documentation

Status: LIVE MVP. The offline Rust core extracts typed assertions, estimates verdicts
with a seeded Random Forest, and selects evidenced claims with MMR. CLI and web use the
same core. Offline `lexicon compile`, `normalize`, `split` and `parse` commands
remain available for the independent text-preprocessing path. Format compliance and predictive quality are evaluated separately.

The CPU evidence-graph candidate has completed a frozen independent
evaluation: 87.74% on 5,000 targets and 87.58% on 20,000 targets. Its complete
native Rust/ONNX image and source snapshot are available locally; see the
[candidate handoff](handoffs/evidence-graph-runtime.md) for artifacts, assumptions,
commands and the distinction from the existing running workbench.

Organizer snapshot: `7c32449d878efde84aa1f38ce179778d1e2c4a48`.
Original files are checked against [the checksum manifest](upstream-files.json).

| Read | Purpose |
| --- | --- |
| [Root instructions](../AGENTS.md) | Rules shared by every task |
| [Development](development.md) | Setup, commands, OS details and troubleshooting |
| [Architecture](architecture.md) | Boundaries, implemented pieces and deferred GPU extension |
| [Agent roles](agents.md) | Responsibilities and coordination |
| [Project graph](knowledge/README.md) | Curated memory, extracted Cargo graph and context |
| [CPU decision](decisions/0001-cpu-first.md) | Competition execution target |
| [Evidence MVP decision](decisions/0002-evidence-mvp.md) | Model, provenance and runtime boundaries |
| [Compiled evidence graph](decisions/0003-compiled-evidence-graph.md) | Typed constraints and optional frozen neural extraction |
| [Evidence integration results](handoffs/evidence-graph-runtime.md) | Current measured accuracy, Docker and integration limitations |
| [Million V1/V2 evaluation](research/million-v1-v2.md) | Complete archive validation, strict transfer and declared protocol compatibility; synthetic development cohorts, not competition accuracy |
| [Million evaluation handoff](handoffs/million-evaluation.md) | Reproduction, input/target isolation, model freezes and retained test failures |
| [KB chain port](handoffs/kb-chain-port.md) | Rust F2 temporal chain + G1 guard, parity, `VERIDYCT_KB_CHAIN` switch |
| [Live MVP handoff](handoffs/live-mvp.md) | Interfaces, task ownership and validation |
| [Presentation and accuracy](handoffs/presentation-integration.md) | PNG diagrams, hidden-label test and downloadable LLM comparison |
| [Handoff template](handoffs/TEMPLATE.md) | Continue a task without rediscovery |
| [Foundation handoff](handoffs/workspace-foundation.md) | What this milestone delivers |
| [Practice × Lexicon Lab](../labs/practice-lexicon/README.md) | Offline graph, chronological practice queries, correlations and lab tests |

| [Assertion text pipeline](../labs/assertion-extraction/README.md) | CSV commands, structured records, generated practice output and limitations |
| [Parser internals](../labs/assertion-extraction/HOW-IT-WORKS.md) | Algorithms, libraries, source alignment and bounded discourse state |
| [Assertion extraction plan](assertion-extraction-plan.md) | Proposed row splitting, unresolved cases, and extraction evaluation |
| [Knowledge base research](research/knowledge-base.md) | 59 techniques per KB step with verdicts, Rust availability and measured practice results; raw worker reports in [research/notes](research/notes/README.md), atlas sources in [research/atlas](research/atlas/README.md) |
| [Claim generation research](research/claim-generation.md) | The separate generator: the five KB queries it calls, the pipeline to 1,000 claims, contract rules and 4 techniques |
| [MMR research](research/mmr.md) | MMR and diversity for claim selection and labelling, with measured practice experiments; scripts and source reports in [analysis/mmr](../analysis/mmr/README.md) |
| [Neural text layers](research/neural-embeddings.md) | Embeddings, NLI cross-encoders, fine-tuning, typed-value grammar and subject resolution measured on practice (2026-10-28): what the neural layer is for, what to use, x86 cost; scripts and JSONL results in [labs/embedding-experiments](../labs/embedding-experiments/README.md) |
| [Generator reverse-engineering](research/generator-reverse-engineering.md) | How deterministic the organizers' generator is, measured on practice (2026-10-28): ids, pages, closed lexicon and label semantics are exact; wording is free paraphrase (89% unique templates); lies are mostly time-shifted real values or upward numeric perturbations; unsure has no text rule; ceiling estimate for a dense universe; scripts in [labs/generator-reverse-engineering](../labs/generator-reverse-engineering/README.md) |
| [Evaluation suite results](research/evaluation-suite-results.md) | Our solution on the teammate's synthetic evaluation suite (2026-10-28): timeline engine exact with gold forms, practice-trained extractor 99.62% / 99.45% labels on held-out worlds, suite-trained extractor 100%, why the suite is easier than the competition, V9 decide() bug; scripts in [labs/evaluation-suite-runs](../labs/evaluation-suite-runs/README.md) |
| [Knowledge base campaign](research/kb-campaign.md) | Every KB variant and about 190 combinations measured on practice only, then tested on the whole synthetic suite (2026-10-29): the per-key temporal chain wins (0.809 arena points vs 0.742 for V9, 0.941 on suite transfer), no combination beats it on fresh splits, extracted forms are now the bottleneck, port spec for Rust; harness, family code, reports and every result line in [labs/kb-campaign](../labs/kb-campaign/README.md) |

## Official sources

- [Original organizer README](../UPSTREAM.md)
- [Runtime and output contract](../contracts/README.md)
- [Claim grammar](../contracts/claim-forms.md)
- [Value grammar](../contracts/value-forms.md)
- [Official checker](../scripts/check.sh)

## Next milestone

Improve extraction coverage and independent evaluation. The practice demo includes
training examples; its results are not an estimate of accuracy on unseen rows.
