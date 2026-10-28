# Building VERIDYCT together

Team JEV: Teo, Edi, Mihai. Use your own GitHub identity so contributions remain traceable.
The current repository is the public fork; keep secrets and private conversation history out.

## Before a change

- Read [AGENTS.md](AGENTS.md), the affected scope rules, and the task acceptance criteria.
- Sync `main`, create a short branch such as `feat/input-parser` or `fix/context-links`.
- Assign a human owner. Document dependencies and coordinate changes to shared interfaces.
- Separate checkouts are required for agents editing concurrently. Do not share a mutable
  working tree or force-push another person's branch.

## Before review

```sh
cargo xtask check
cargo xtask test
```

Run additional integration checks relevant to the change. State what was not run.
Use ordinary, specific commit messages: `Validate dates before building evidence` or
`Keep the workbench usable on small screens`. Describe what changed, without filler.

Leave a [handoff](docs/handoffs/TEMPLATE.md) when a task continues in another session.
Update a decision record when changing architecture; update the knowledge map when a
module boundary changes. A teammate reviews the concrete diff before merging routine PRs.

## Organizer updates

```sh
git remote add upstream https://github.com/QA-DNA/hype-arena-starter.git
git fetch upstream
```

Add the remote only if it is missing. Inspect updates before merging. A deliberate
upstream update must preserve the original source, record the new commit, and update
`docs/upstream-files.json` from the verified organizer revision. Do not regenerate hashes
merely to make an unexpected local change pass. Never alter contract examples to hide failures.

## Task completion

The behavior exists, relevant checks passed, docs match the code, and the handoff states
remaining limitations. A pretty UI or a successful build does not establish solver accuracy.
