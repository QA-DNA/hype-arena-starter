# Workspace foundation

- Status: workspace foundation complete
- Human owner: Teo
- Branch: main, under explicit user authorization to initialize and push this workspace
- Base commit: 7c32449d878efde84aa1f38ce179778d1e2c4a48
- Scope: development environment, repository structure, documentation and collaboration
- Excluded: competition solver, claim generation, runtime LLM, GPU infrastructure

## Delivered behavior

- One Rust workspace with core, CLI, API and portable xtask commands.
- A local workbench with real API status, project knowledge exploration and runbook.
- CLI status, explicit errors for the unimplemented solver, scoped agent rules.
- Versioned context with actual Cargo package dependencies and source fingerprints.
- Development/container configuration and CI for three operating systems.
- Original organizer files preserved; original README archived as UPSTREAM.md.

## Verification

- `cargo xtask check`: formatting, Clippy, 58 local links, 15 project nodes,
  14 relationships and the original organizer checksums passed on WSL Linux.
- `cargo xtask test`: all 6 workspace tests passed.
- `cargo xtask graph` and scoped context generation passed; JavaScript syntax checked.
- Linux amd64 runtime image built successfully: approximately 111 MiB, user 10001.
  The status command passed with no network, a read-only root, 2 CPU and 6 GiB RAM.
  The default command exited 2 because the solver is intentionally absent.
- `docker compose up --build`: API health and workspace status passed, then shutdown passed.
- Development container built; Rust 1.90.0, Python 3 and the non-root user were verified.
- Local browser: API status, graph filtering/selection and responsive layout checked.
- [GitHub Actions](https://github.com/teodorbalan/VERIDYCT/actions/workflows/ci.yml)
  records the Ubuntu, Windows, macOS and container results for each pushed commit.

No solver accuracy or competition-checker success is claimed by this milestone.

## Scope clarification

The user explicitly requested only the workspace. Input parsing, classification,
evidence logic and generation are absent. Do not start the challenge implementation
until the team requests a new task.

## Future task, when requested

Define typed evidence and temporal behavior in crates/core, establish an independent
evaluation split, then implement the real solver. Add API/CLI adapters to that shared
implementation. Keep solver_ready false until the application genuinely supports it.
