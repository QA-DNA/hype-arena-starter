# Architecture and implementation boundaries

Status: FOUNDATION IMPLEMENTED. Workspace metadata, a CLI status command, API,
local workbench and xtask exist. Offline lexicon normalization and assertion-text
splitting now live in core; typed values, truth reasoning and evidence evaluation remain planned.

## Competition profile

The default application is Rust on CPU. CLI and HTTP adapters call the same core.
The browser currently presents architecture, live workspace status and project context.
It will present solver results once those exist. Its assets are served locally.

```mermaid
flowchart LR
    CLI["Rust CLI"] --> Core["Rust core"]
    Web["Browser UI"] --> API["Rust HTTP API"]
    API --> Core
    Core -. planned .-> Evidence["Typed evidence and temporal relations"]
    Core -. planned .-> Output["Validated result and explanations"]
```

| Boundary | Responsibility | Must not depend on |
| --- | --- | --- |
| crates/core | Workspace metadata, lexicon normalization and assertion-text splitting | HTTP, browser, CUDA |
| crates/cli | File input/output, deadline, process exit behavior | HTTP server availability |
| crates/api | Request validation, job limits, responses, local assets | A separate implementation of reasoning |
| apps/web | Input controls, architecture diagram, results and provenance | External CDN availability |
| xtask | Development and verification commands | Competition runtime execution |
| native | Future isolated native acceleration | Inclusion in the default competition build |

## Performance rules

- Profile first. Record end-to-end latency, peak memory, input characteristics, correctness,
  compiler profile, and active CPU concurrency before making an optimization claim.
- Use bounded buffers and bounded CPU workers under the 2-CPU limit. Do not assign one
  operating-system thread per row. Account for library-created thread pools too.
- Share immutable reference data where useful; avoid speculative global caches and
  lock-heavy mutable graphs. Deterministic output ordering is explicit.
- Use exact representations for monetary values, dates, IDs, and graph keys. Model scores
  may use floating point under a documented numerical contract.
- Do not ship target-cpu=native or unconditional instructions absent from the supported
  evaluator target. Runtime feature detection needs a correct portable path.
- Every result carries source references and an explanation suitable for review.

## Future GPU profile

An explicitly requested future workload may add Rust orchestration -> a narrow native
boundary -> C++/CUDA libraries or kernels -> NVIDIA hardware. This is not part of the
competition profile, the present build, or the foundation acceptance gate.

- Start with a profiled workload and a CPU reference implementation.
- Prefer established GPU libraries for standard operations before writing custom kernels.
- Measure transfers, synchronization, allocation, kernel execution, and total runtime.
- Choose FP16/BF16 only for operations with validated error tolerances and hardware support.
  Exact facts, dates, money, and equality decisions must not silently change precision.
- Document buffer ownership, lifetimes, alignment, sizes, errors, thread safety, and
  synchronization at the FFI boundary. Do not let C++ exceptions cross a C ABI boundary.
- The default Cargo dependency graph and runtime image must remain CUDA-independent.
  GPU tests run only on designated compatible hardware; all ordinary checks still run on CPU.

See [the CPU decision](decisions/0001-cpu-first.md) and [native rules](../native/AGENTS.md).

## Text preprocessing

The [assertion extraction lab](../labs/assertion-extraction/README.md) calls the same
Rust core used by `veridyct normalize`, `split`, and `parse`. `lexicon compile` creates
a versioned alias index. The core accepts no labels or practice forms, and returns
structured records with separate subject, attribute, assertion wording, spans and
unresolved reasons. CLI adapters own CSV serialization and parent-row metadata.

The combined path passes in-memory objects directly between normalization and splitting.
It performs no typed-value interpretation or truth classification. Evaluation may
load a new index built from the runtime lexicon. The solver remains unavailable.
See the [scope decision](../labs/assertion-extraction/DECISION.md) and
[handoff](handoffs/assertion-pipeline.md).


The contextual extraction update adds a bounded ordered-stream adapter in core, shared
by combined/staged CSV commands. Cross-row evidence references and version/scope
qualifiers are typed metadata rather than reparsed display sentences. It makes no
truth decisions; the row-local splitter remains available. See the
[v2 handoff](handoffs/contextual-extraction.md) for interfaces and validation.
