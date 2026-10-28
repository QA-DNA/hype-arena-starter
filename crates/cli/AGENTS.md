# CLI and competition runtime scope

Read [root instructions](../../AGENTS.md). `info` works. `run` exits 2
because the competition solver is not implemented; preserve that honest boundary.

- Call the shared core; do not implement a second reasoning pipeline here.
- Honor the official input/output paths, CSV encoding, required columns, and IDs.
- Handle malformed input with actionable errors and a defined exit status.
- Respect ARENA_DEADLINE and termination. Write complete output to a temporary file
  in /output, then rename within that directory. Never rename a /tmp file across mounts.
- Keep output within 16 MiB and the runtime's writable-path and resource budgets.
- Read runtime input without requiring the practice form column; it is absent at evaluation.
- Runtime must work with no network, user 10001, no writable home, a read-only root,
  two CPUs, 6 GiB RAM, and bounded processes/threads.
- Log diagnostics separately from machine-readable output. Never print secrets.
- Test realistic CPU-only container execution once the solver exists. A health check,
  placeholder output, or successful process exit is not evidence of contest compliance.
