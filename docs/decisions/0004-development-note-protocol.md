# 0004: Evaluate supplied-note protocols outside the competition interface

Teodor requested full evaluation of the million-row Downloads archives, including
the refined V2 and a comparison, after committing and publishing the implemented
solver. The [task handoff](../handoffs/million-evaluation.md) records ownership,
measurements and reproducibility.

The supplied datasets contain two different tasks. Source-preserving pilot rows
use the organizer-derived annotations; the larger tier asks recursive, explicitly
dated questions about provided notes. Its AST and evidence policy exceed the
competition CSV claim grammar. V2 changes the surface syntax and also rewrites
the temporal/comparison pilot tiers into this second task.

We add a research adapter under [tools/million_evaluation](../../tools/million_evaluation/README.md),
with an isolated safe Rust bridge workspace. Production interfaces, model weights,
organizer files and the root dependency graph stay unchanged. The adapter exposes
the published supplied-note grammar, per-query evidence availability and exact
typed comparison. Development-time renderer vocabulary is explicitly disclosed;
these measurements cannot establish arbitrary-English generalization.

Features and annotation sidecars are separate. Only input-derived feature files,
public practice training data and frozen models are mounted in inference Docker
containers. Generators, source-bank values, oracle answers, target ASTs, metadata
and recipes do not become features. Test-only oracle differential checks and
post-inference scoring are separate programs. Extraction memoization reuses a
deterministic parse, never the availability of an observation for another query.

Freeze the V1 surface adapter before scoring. Measure its strict V2 transfer,
including unsupported-language abstentions. Add V2 surface compatibility as a
separate, explicitly adapted track, retaining identical numerical kernels and
model weights; freeze it before its full scores. Verify that the extended grammar
produces identical V1 feature plans. Preserve failures and earlier scores rather
than silently replacing the strict transfer result.

Report truth accuracy, macro-F1, confusion matrices, parsing coverage, strict
projected AST equality, source exposure and per-family results separately. Null
parsing-only labels are counted and excluded from the truth denominator. A global
million-row accuracy is insufficient: finite-source templated logic dominates
the pool. V1/V2 stable IDs align related rewrites but can denote different
questions; exact unchanged-input overlap requires a full-public-input fingerprint.
Neither archive is an independent held-out factual benchmark or human gold.

Typed `recorded` assertions use literal typed equality; arithmetic comparisons
use compatible metadata and exact conversions. Comparing two partial date values
needs a protocol-specific range relation, distinct from the production interval
predicate API. The research bridge contains that explicit date-value boundary,
without changing production deductions. Exhaustive differential tests verify it.

Raw archives, per-row outputs, weights, caches and binaries remain local ignored
artifacts. Versioned documentation records curated results and provenance only.
The submitted application remains a standalone offline CPU Rust system; this
Python development harness is not a competition submission or deployment.
