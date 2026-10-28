# VERIDYCT documentation

Status: LIVE MVP. The offline Rust core extracts typed assertions, estimates verdicts
with a seeded Random Forest, and selects evidenced claims with MMR. CLI and web use the
same core. Format compliance and predictive quality are evaluated separately.

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
| [Live MVP handoff](handoffs/live-mvp.md) | Interfaces, task ownership and validation |
| [Presentation and accuracy](handoffs/presentation-integration.md) | PNG diagrams, hidden-label test and downloadable LLM comparison |
| [Handoff template](handoffs/TEMPLATE.md) | Continue a task without rediscovery |
| [Foundation handoff](handoffs/workspace-foundation.md) | What this milestone delivers |
| [Practice × Lexicon Lab](../labs/practice-lexicon/README.md) | Offline graph, chronological practice queries, correlations and lab tests |

## Official sources

- [Original organizer README](../UPSTREAM.md)
- [Runtime and output contract](../contracts/README.md)
- [Claim grammar](../contracts/claim-forms.md)
- [Value grammar](../contracts/value-forms.md)
- [Official checker](../scripts/check.sh)

## Next milestone

Improve extraction coverage and independent evaluation. The practice demo includes
training examples; its results are not an estimate of accuracy on unseen rows.
