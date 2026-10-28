# VERIDYCT documentation

Status: WORKSPACE FOUNDATION. Rust crates, xtask commands, a local workbench, container
configuration and CI are implemented. The competition solver and claim generator are not.

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
| [Handoff template](handoffs/TEMPLATE.md) | Continue a task without rediscovery |
| [Foundation handoff](handoffs/workspace-foundation.md) | What this milestone delivers |
| [Practice × Lexicon Lab](../labs/practice-lexicon/README.md) | Offline graph, chronological practice queries, correlations and lab tests |
| [Knowledge base research](research/knowledge-base.md) | 63 techniques per KB step with verdicts, Rust availability and measured practice results; raw worker reports in [research/notes](research/notes/README.md), atlas sources in [research/atlas](research/atlas/README.md) |

## Official sources

- [Original organizer README](../UPSTREAM.md)
- [Runtime and output contract](../contracts/README.md)
- [Claim grammar](../contracts/claim-forms.md)
- [Value grammar](../contracts/value-forms.md)
- [Official checker](../scripts/check.sh)

## Next milestone

Implement the evidence model and independently evaluated reasoning pipeline. Keep the
workbench's solver status false until real classification and generation are available.
