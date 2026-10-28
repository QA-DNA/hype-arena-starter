# Agent roles and team workflow

These are task profiles, not running agents, automatic permissions, or assignments to
Teo, Edi, and Mihai. Assign a human owner when opening a task. One person may hold several
roles. Follow the user's authorization before launching agents or writing external messages.

| Role | Scope | Required delivery |
| --- | --- | --- |
| Integrator | Root tooling, docs, Cargo graph, CI, release assembly | Reproducible commands, integration checks, accurate state |
| Core engineer | crates/core | Stable typed interface, evidence provenance, meaningful correctness tests |
| Runtime engineer | crates/cli | Offline execution, bounded resources, output/deadline behavior |
| Demo engineer | crates/api and apps/web | Same core behavior, live interaction, inspectable explanations |
| QA reviewer | tests and evaluation documentation | Independent evaluation, contract checks, reproducible failures |
| Native performance engineer | native, only for an authorized future task | Measured speedup, CPU reference, FFI and numerical guarantees |

Scoped AGENTS.md files define module rules. Root instructions apply to every role.

## Task packet

Before work, record: task ID, owner, base commit, goal, authorized paths, acceptance
criteria, proposed interface changes, dependencies, and the next reviewer. A task's path
list is coordination metadata, not an operating-system permission boundary.

## Execution

1. Read root instructions, scoped instructions, and task-relevant design decisions.
2. Inspect the current implementation and working tree. Verify whether documented commands exist.
3. Work in the task's own branch/checkout. Agree on shared interfaces before parallel edits.
4. Implement the smallest complete change within scope; add or run checks proportionate to risk.
5. Update the affected documentation and a concise handoff. Record failed or unavailable checks.
6. Request a teammate's review of a concrete diff. The integrator resolves cross-module conflicts.

No agent may mark its own benchmark estimate as a measured result or a design node as
implemented without repository evidence. A task marked done includes a diff and verification.

## Working memory

- Issues track current assignment; Git tracks changes; decisions track reasons.
- Use one handoff file per task to avoid a shared log becoming a merge bottleneck.
- Record conclusions and evidence, not private thought transcripts or full conversation history.
- A generated project map is a navigation aid. Its edges do not override source code,
  test results, official rules, or direct user instructions.
- Generated context excludes credentials, .env files, binary artifacts, and unrelated tasks.

## Review focus

- Core: semantic correctness, missing evidence, temporal uncertainty, leakage.
- Runtime: offline operation, bounded memory, atomic output, termination handling.
- Demo: real calls to core, correct error/unknown states, no fabricated results.
- Integrator: clean checkout, cross-platform commands, dependency and feature boundaries.
- Native: realistic benchmark, FFI safety, error tolerance, CPU portability.

Template: [handoff](handoffs/TEMPLATE.md). Project memory: [knowledge map](knowledge/README.md).
