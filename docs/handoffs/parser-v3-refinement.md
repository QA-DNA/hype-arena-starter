# Parser V3 raw-literal refinement

- Task: `task_eebd618d0623`, dispatch `ctx_6f74a63866fc`.
- Agent owner: dispatched refinement worker; human owner unassigned.
- Branch: `teodorbalan/parser-v3-refinement`; base `a6a1996`.
- Owned production paths: `crates/core/src/structured.rs` and
  `crates/core/src/claim_program.rs`; focused tests and this handoff.
- Interfaces: unchanged. Safe offline Rust; no added dependency.
- Scope narrowed by coordinator at the final release deadline to the confirmed
  nominal-shielding corruption and minimal verified repairs.

## Result

Program leaves no longer rewrite nominal candidate text to fullwidth ASCII.
The binder already protects nominal spans from clause splitting. It now also
ignores boolean and unknown keywords inside nominal proposals, keeping quoted
names opaque without altering the source spelling inspected by typed repairs.
Overlapping name proposals can no longer mutate quantity units, currencies,
version markers, or date text. All candidates retain Unicode scalar offsets;
candidate order does not select which source characters survive.

The new [focused regressions](../../tools/claim_program/tests/raw_literals.rs)
exercise both candidate orders for GB, mW, USD, versions, dates and durations
after a Unicode subject, as well as names containing boolean/unknown keywords
and accented characters. These are development-authored semantic fixtures,
not independent accuracy estimates or training material.

## Verification

All Rust commands ran offline in `veridyct:dev`, as root, with two CPUs,
6 GiB memory, `veridyct-refinement-v3-target` and the shared
`veridyct-mvp-registry`. Host Cargo was not installed.

- Claim-program harness: all 18 prior tests and two new regression tests pass.
- Schema-binder harness: all 43 prior tests pass.
- Claim-program all-target Clippy with `-D warnings`: passes.
- Rustfmt applied to the three changed Rust files.
- Paired released practice390: **339/390 exact**, unchanged from the integrated
  binder baseline; zero changed parsed rows, zero exact regressions, and all
  328 pure neural fallbacks retain the original neural facts.

The practice adapter ran from the debug build for a fast deadline check; its
timing is not a release performance benchmark. Only input and public lexicon
were mounted into the parser runtime; practice gold was read by the separate
host evaluator after output existed. Frozen practice inputs and baseline were
copied unchanged from the binding worker's retained artifacts. Full evaluator
output remains ignored at `artifacts/parser-v3-refinement/evaluation.json`.

## Remaining work

The coordinator owns final release build, workspace `cargo xtask check` /
`cargo xtask test`, Docker packaging, official checker and integration. These
were not rerun by this deadline-limited worker. DEVELOPMENT512 rescoring belongs
to the runtime worker; no new challenge score is claimed here.

Broader multi-clause pronoun carry, API/product version disambiguation,
contrastive subject distractors, explicit negation wrappers and adapter grammar
coverage remain outside this minimal freeze. No final2048, private world,
labels, dates or truth values were used as runtime parsing features; no model,
organizer file, deployment or external publishing changed.
