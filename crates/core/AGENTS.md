# Core scope

Read [root instructions](../../AGENTS.md). Only workspace metadata exists;
the evidence model and reasoning engine are future work.

- Own typed domain data and reusable computation. CLI, HTTP, and UI depend on core,
  while core must remain independent of those adapters and of CUDA.
- Distinguish observed statements, accepted evidence, conflicts, and unknowns.
  Preserve source row IDs, date precision, units, operators, and provenance.
- Do not infer exact change boundaries from observation dates without evidence.
- A false compound row does not prove each extracted statement false. Unlabelled
  rows must not become trusted facts merely because they recur.
- Keep exact money/date/identifier handling separate from approximate model scores.
- Use explicit domain errors rather than panics for malformed external input.
- Keep output order and seeded behavior reproducible. Do not rely on hash iteration order.
- Bound allocations and CPU concurrency. Optimize representative release builds only
  after locating a bottleneck and checking correctness after the change.
- No runtime LLM or network access. Development-time generated data needs provenance.
- Tests should establish semantics, boundary behavior, and regression protection;
  do not mirror implementation details or pretend validation data was unseen.
- Deliver interface changes with their callers and meaningful checks, or clearly
  record a staged interface agreement before parallel implementation.
