# HTTP API scope

Read [root instructions](../../AGENTS.md). The API serves health, workspace metadata,
the curated project graph, and embedded browser assets. No solver endpoint exists yet.

- Adapt requests to the same core used by the CLI. Do not reimplement classification.
- Define request/response schemas, errors, and job status before a UI depends on them.
- Bound input size, concurrent work, queues, and retained results. CPU-intensive work
  must not block an async request executor indefinitely.
- Return evidence references and meaningful unknown/error states. Never fabricate
  a successful result to keep a demo responsive.
- Serve local UI assets. Keep local bind address and port configurable per checkout.
- No runtime external inference dependency. UI and API must remain demonstrable offline.
- Preserve the distinction between a health response and a completed computation.
- Keep shared API-schema changes synchronized with the frontend and relevant checks.
