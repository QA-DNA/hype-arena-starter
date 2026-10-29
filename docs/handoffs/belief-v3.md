# Belief V3: validated masses and bounded claim composition

- Status: review; implementation and focused validation complete
- Human owner: unassigned
- Agent owner: dispatched worker `task_50255907ca4e`, dispatch `ctx_0a028201d4b2`
- Branch and checkout: `teodorbalan/belief-v3`, isolated Orca checkout `belief-v3`
- Base: `6a9b997e52429b986a83203b0a4fd65209cd7b80`; coordinator interface commit
  `d8d1af4` cherry-picked as `54ee9eb` exports the existing claim AST.
- Owned paths: [belief.rs](../../crates/core/src/belief.rs),
  [standalone checks](../../tools/belief/Cargo.toml), this handoff.
- Scope agreement: coordinator owns root exports, legacy model types, engine,
  CLI and AST; chain worker owns `kb_chain.rs`. This delivery does not edit those
  files. The inherited interface cherry-pick is separate from the belief commit.
- Acceptance: validated finite unit-sum masses; exact Strong Kleene logic;
  duplicate invariance; no independent confidence multiplication; explicit
  unsupported/missing-estimate handling; exact comparison callbacks; bounded
  AST evaluation; meaningful semantic and probability tests.

## Decision and resulting behavior

The [architecture](../architecture.md) separates exact constraints from
uncalibrated model scores. The new safe Rust CPU module keeps that separation:
`Composition.hard` comes only from exact per-leaf callbacks and three-valued
logic. `Composition.soft` contains bounds derived from supplied three-class
marginals. One channel never overwrites or proves the other. The legacy
`Probabilities`, `Prediction`, `ChainOutput` and AST structs are preserved.

`Belief::try_new(true, false, unsure)` rejects non-finite values, values outside
`[0,1]`, and sums more than `16 * f64::EPSILON` away from one. The unsure residual
is repaired only within that floating-point allowance. It does not normalize
arbitrary scores, balance class counts, pick labels, or manufacture confidence.
Private fields and no direct `Deserialize` implementation preserve validation.
Legacy conversions use `TryFrom<&Probabilities>` and `to_probabilities()`.
Negation swaps true/false and preserves the unsure mass.

For hard `All`, any false dominates, otherwise any unknown yields unknown,
otherwise the result is true. `Any` is dual. `Not(unknown)` is unknown. Empty
groups, `Unknown`, and `Unsupported` yield unknown. Before callbacks run, a
preflight checks the existing AST limits (512 nodes, depth 32); exceeding either
returns whole-program hard unknown and vacuous soft bounds without partial
callback effects. This does not bound caller callback work or validate a
caller's exact-evidence assertions.

There is deliberately no independent-product mode. With no joint distribution,
AND true is an intersection of true events and AND false is a union of false
events. OR reverses these roles. If `l_i`, `u_i` are the supplied marginal bounds,
the intersection is bounded by `[max(0, 1-sum(1-l_i)), min(u_i)]`, and the union
by `[max(l_i), min(1, sum(u_i))]`. Unsure follows from the complement of the two
disjoint decided classes. Intersecting with the unit simplex tightens each
class bound. These are outer marginal bounds conditional on coherent supplied
marginals; endpoints for all classes need not be simultaneously attainable,
and nested formulas can have loose bounds. The bounds cannot repair biased or
miscalibrated estimates and do not verify domain-specific joint feasibility.

Repeated identical atoms/comparisons invoke their callback once. Same-operator
groups flatten and deduplicate, and reordered identical subexpressions intern
to one node; double negation simplifies. Repeating a leaf or same-operator
subexpression therefore does not accumulate confidence. Different constraints
on the same slot remain different propositions. Shared `(subject, attribute)`
slots and shared evidence IDs are reported, and their marginals still use
dependence-safe bounds. Source IDs do not establish independence or logical
equivalence. The module does not solve cross-predicate mutual exclusion,
general Boolean equivalence/absorption or a joint probability optimization;
exact typed consistency remains with the caller's knowledge kernel.

## Interface for the coordinator

```rust
compose(
    expression: &ClaimExpr,
    atom: &mut impl FnMut(&Fact) -> LeafAssessment,
    comparison: &mut impl FnMut(&SlotReference, ComparisonOp, &SlotReference)
        -> LeafAssessment,
) -> Composition

LeafAssessment {
    hard: TruthValue,
    estimate: Option<Belief>,
    evidence_ids: Vec<String>,
}

Composition {
    hard: TruthValue,
    soft: BeliefBounds,
    evidence_ids: Vec<String>,
    diagnostics: CompositionDiagnostics,
}
```

`LeafAssessment::from_resolution(&Resolution)` maps `Supported` to hard true,
`Contradicted` to hard false, and `Unknown`/`Conflict` to hard unknown. It copies
source row IDs and supplies no model estimate. The caller can then attach a
validated estimate if its provenance justifies one. `compose` collects sorted
unique evidence IDs from all evaluated leaves; this is provenance, not a
minimal proof of the whole formula. Callbacks must be deterministic for one
call and must enforce query date, held-out row exclusion, source authority,
currency/billing/unit compatibility and exact typed semantics. The comparison
callback receives the untouched slots/operator; use `recorded_value` and
`compare_recorded_values` from [knowledge.rs](../../crates/core/src/knowledge.rs).

`LeafAssessment::unresolved()` supplies hard unknown and no estimate, giving
`BeliefBounds::VACUOUS` (`[0,1]` for each class). Lack of proof is not a complete
posterior and is not categorical `P(unsure)=1`. When an explicit categorical
unknown mass is justified, `LeafAssessment::categorical_unknown()` supplies
`Belief::UNKNOWN` (`0,0,1`). Parser-unknown, unsupported and empty AST branches
also have that fixed logical unknown state. The difference remains visible in
the bounds and `missing_estimates` diagnostic.

`BeliefBounds::true_mass()`, `false_mass()` and `unsure_mass()` expose immutable
`ProbabilityRange` values with `lower()` and `upper()`. `point(Belief)` makes a
degenerate envelope. `uncommitted_mass()` gives readable weights: lower true,
lower false, all remaining mass unsure. That last mass includes unidentified
dependence or unavailable model information, so it may exceed the unsure
marginal upper bound. This is an epistemic reporting projection; it is not a
calibrated posterior, must not be advertised as measured confidence, and is
deliberately not a midpoint of an unsupported distribution.

The initial API and this projection were agreed through Orca orchestration
before implementation. Root should export `pub mod belief;` after integration.
Call `compose(&program.expression, ...)` when AST semantics must be preserved;
do not flatten OR/NOT/incomplete programs into legacy positive fact bags.

## Verification

Environment: Docker `veridyct:dev`, image
`sha256:fd69385ab339602c033529a3b21e751750ad6757f148e3a894e953800fa79210`,
Rust 1.90, Linux CPU, no network, two CPUs, 6 GiB, user 0. Registry:
`veridyct-mvp-registry`; dedicated target: `veridyct-belief-v3-target`.
No performance claim is made.

For each command below, run from this checkout's root using this PowerShell
prefix (then append the listed command):

```powershell
docker run --rm --network none --user 0 --cpus 2 --memory 6g `
  --mount "type=bind,source=$PWD,target=/workspace" `
  --mount type=volume,source=veridyct-belief-v3-target,target=/workspace/target `
  --mount type=volume,source=veridyct-mvp-registry,target=/usr/local/cargo/registry `
  -e CARGO_TARGET_DIR=/workspace/target -w /workspace veridyct:dev
```

| Command after the prefix | Actual result |
| --- | --- |
| `cargo test --offline --manifest-path tools/belief/Cargo.toml` | Initial run: 13 passed, 0 failed; 2,916 correlated-joint containment checks inside one test. Generated the standalone lockfile. |
| `cargo test --locked --offline --manifest-path tools/belief/Cargo.toml` | Final run passed: 13 tests, 0 failures, including all 2,916 correlated-joint containment checks. |
| `cargo clippy --locked --offline --manifest-path tools/belief/Cargo.toml --all-targets -- -D warnings` | Passed, warnings denied. |
| `cargo fmt --manifest-path tools/belief/Cargo.toml -- --check` | Passed. |
| `cargo xtask check` | Failed on the unchanged engine test at `crates/core/src/engine.rs:1406`, Clippy `cmp_owned` for comparing to `"2026-02-01".to_owned()`. Workspace format passed; lint stopped before docs. Coordinator notified and reports its separate fix/check pass in `17b876e`; that fix was not imported or rechecked here. |
| `cargo xtask test` | Passed: 106 tests reported passed across the workspace. Optional external Sdev parity fixture was not supplied; this is not a new accuracy measurement. |
| `cargo xtask docs` | Passed: 394 local links, 19 graph nodes, 19 relationships; organizer checksums match. Required the read-only Git metadata mount described below. |

The first docs command could not interpret the Windows worktree's `.git`
pointer inside Linux (`/workspace/C:/Users/.../.git/worktrees/belief-v3`). For
the successful docs run, the same Docker prefix additionally used:

```powershell
--mount "type=bind,source=C:/Users/Teodor/orca/QA-DNA-JEV/.git,target=/repo-git,readonly" `
-e GIT_DIR=/repo-git/worktrees/belief-v3 `
-e GIT_COMMON_DIR=/repo-git -e GIT_WORK_TREE=/workspace `
-e CARGO_NET_OFFLINE=true
```

Both `cargo xtask check` and `cargo xtask test` also set
`CARGO_NET_OFFLINE=true`; the standalone Cargo commands use `--offline`.

The table-driven tests cover all nine AND/OR combinations and all three NOT
states, false+unknown, true+unknown, empty/unknown/unsupported branches,
nonfinite/negative/out-of-range/bad-sum inputs, legacy conversion, negation of
soft unsure, missing versus categorical unknown, incompatible recorded money
and billing periods, unit conversion, partial dates, temporal evidence gaps,
source IDs, conflict abstention, repeated identical and same-slot predicates,
reordered/nested duplicate groups, callback memoization, maximum accepted 511
atoms, and limits before any callback. The correlated fixtures enumerate all
27 three-atom joint states and 729 pairs of them for four different formulas.

## Limits and next integration step

No labels from live20, final challenge gold or synthetic training targets were
loaded. Test fixtures are assistant-authored development-time semantic checks,
not training material or independent predictive evaluation. No estimator was
fitted and no confidence calibration is claimed. A `ChainOutput.p_true` scalar
(`P(true | decided)` under its current contract) does not identify `p_unsure`
and must not be promoted to a three-class posterior by subtraction or an
invented unsure quota. There is no such adapter here.

The coordinator still needs to wire exports and decide which independently
measured per-leaf three-class estimator, if any, may populate `estimate`.
Prefer the exact kernel for hard proof and retain bounds/diagnostics in review
output. If calibration is later added, freeze the input/parser/model and measure
on a separately reserved representative partition with query labels/forms
excluded from prediction; report proper scoring, class calibration and
coverage separately from evidence correctness. Bounds and the uncommitted
projection do not replace that evaluation. The official checker was not run
and no competition accuracy or checker-pass claim is made by this delivery.
