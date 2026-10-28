# VERIDYCT documentation

Status: FOUNDATION AND TEXT PREPROCESSING. Rust crates, xtask commands, a local
workbench, container configuration, CI, and an offline normalization/assertion-text
pipeline are implemented. The competition solver and claim generator are not.

Organizer snapshot: `7c32449d878efde84aa1f38ce179778d1e2c4a48`.
Original files are checked against [the checksum manifest](upstream-files.json).

| Read | Purpose |
| --- | --- |
| [Root instructions](../AGENTS.md) | Rules shared by every task |
| [Development](development.md) | Setup, commands, OS details and troubleshooting |
| [Architecture](architecture.md) | Boundaries, implemented pieces and deferred GPU extension |
| [Assertion text pipeline](../labs/assertion-extraction/README.md) | CSV commands, structured records, generated practice output and limitations |
| [Parser internals](../labs/assertion-extraction/HOW-IT-WORKS.md) | Algorithms, libraries, source alignment and bounded discourse state |
| [Assertion extraction plan](assertion-extraction-plan.md) | Proposed row splitting, unresolved cases, and extraction evaluation |
| [Agent roles](agents.md) | Responsibilities and coordination |
| [Project graph](knowledge/README.md) | Curated memory, extracted Cargo graph and context |
| [CPU decision](decisions/0001-cpu-first.md) | Competition execution target |
| [Handoff template](handoffs/TEMPLATE.md) | Continue a task without rediscovery |
| [Foundation handoff](handoffs/workspace-foundation.md) | What this milestone delivers |
| [Practice × Lexicon Lab](../labs/practice-lexicon/README.md) | Offline graph, chronological practice queries, correlations and lab tests |
| [Knowledge base research](research/knowledge-base.md) | 59 techniques per KB step with verdicts, Rust availability and measured practice results; raw worker reports in [research/notes](research/notes/README.md), atlas sources in [research/atlas](research/atlas/README.md) |
| [Claim generation research](research/claim-generation.md) | The separate generator: the five KB queries it calls, the pipeline to 1,000 claims, contract rules and 4 techniques |
| [MMR research](research/mmr.md) | MMR and diversity for claim selection and labelling, with measured practice experiments; scripts and source reports in [analysis/mmr](../analysis/mmr/README.md) |
| [Neural text layers](research/neural-embeddings.md) | Embeddings, NLI cross-encoders, fine-tuning, typed-value grammar and subject resolution measured on practice (2026-10-28): what the neural layer is for, what to use, x86 cost; scripts and JSONL results in [labs/embedding-experiments](../labs/embedding-experiments/README.md) |
| [Generator reverse-engineering](research/generator-reverse-engineering.md) | How deterministic the organizers' generator is, measured on practice (2026-10-28): ids, pages, closed lexicon and label semantics are exact; wording is free paraphrase (89% unique templates); lies are mostly time-shifted real values or upward numeric perturbations; unsure has no text rule; ceiling estimate for a dense universe; scripts in [labs/generator-reverse-engineering](../labs/generator-reverse-engineering/README.md) |

## Official sources

- [Original organizer README](../UPSTREAM.md)
- [Runtime and output contract](../contracts/README.md)
- [Claim grammar](../contracts/claim-forms.md)
- [Value grammar](../contracts/value-forms.md)
- [Official checker](../scripts/check.sh)

## Next milestone

Implement the evidence model and independently evaluated reasoning pipeline. Keep the
workbench's solver status false until real classification and generation are available.
