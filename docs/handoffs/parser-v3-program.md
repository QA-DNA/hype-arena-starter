# task_2b12f41efec7: bounded claim-program parser

- Status: delivered for coordinator integration; staged API accepted and checks passed.
- Human owner: unassigned. Agent owner: dispatched parser-v3-program worker.
- Branch: `teodorbalan/parser-v3-program`.
- Checkout: `C:\Users\Teodor\orca\workspaces\QA-DNA-JEV\parser-v3-program`.
- Base: `22fa97b6fe27fcfa8d0bab7ae2e85c10c5386148`.
- Scope: [claim_program.rs](../../crates/core/src/claim_program.rs),
  [isolated harness](../../tools/claim_program/README.md), this handoff only.
- Coordinator owns core exports, model, engine, CLI and explicit document context;
  this task does not edit those files or `structured.rs`.
- Acceptance: bounded stable AST, text/schema-only leaves, Unicode spans, scoped
  values, three-valued logic, safe legacy projection, no neural broadcasting,
  semantic/boundary tests, Docker checks, and a local commit for integration.

## Delivered behavior and staged interface

`ProgramParser::compile(&serde_json::Value) -> Result<Self,String>` and
`parse(&self,text:&str,candidates:&[ValueCandidate],neural:&[Fact])->ClaimProgram`
are the accepted integration interface. `ClaimProgram` exposes `expression`,
`complete`, `notes`, `structured`; its `evaluate` and `legacy_facts` methods
provide pure callback evaluation and conservative legacy projection.

`ClaimExpr` has `Atom(Fact)`, `All(Vec<ClaimExpr>)`, `Any(Vec<ClaimExpr>)`,
`Not(Box<ClaimExpr>)`, `Compare { left, op, right }`, and
`Unknown { span, reason }` / `Unsupported { span, reason }` variants.
`SlotReference` contains canonical `subject`, `attribute`, and `date:Option<String>`.
`ComparisonOp` is `Eq/Ne/Lt/Le/Gt/Ge`; `TruthValue` is `True/False/Unknown`.
`CharSpan { start,end }` uses half-open Unicode scalar offsets. All boundary
types derive Clone/Debug/Serialize/Deserialize and appropriate PartialEq/Eq.
The expression JSON uses `kind`/`value` tags; enum spellings are snake_case.

AND binds before OR. Explicit groups, neither/nor, all/any, both/either and
not-all preserve their scope. Atomic lexical negation remains local, including
ASCII/curly contractions. `not less than` is GE, not whole-program NOT. Unknown
leaves stay in the AST: false AND unknown is false; true OR unknown is true.
Empty groups yield unknown, and incomplete programs cannot project to legacy.
Only complete Atom/All trees yield a legacy fact vector.

The existing `SchemaParser` binds leaves. Candidate offsets are rebased per leaf;
currency, billing period, units, dates and versions remain local. Known aliases
and quoted/nominal values shield lexical conjunctions; nominal spelling is
restored after binding. Ordinary prose without reliable logical structure has
`structured=false`, preserving the coordinator's existing fallback. Structured
leaves deliberately receive no unaligned row-level neural facts.

Slot comparison parsing consumes only explicit schema references and written ISO
dates, not actual values. Missing date defaults are an evaluation concern. Pure
evaluation calls mutable atom/comparison callbacks; the coordinator must return
unknown for missing values or incompatible currency, period, dimensions or date
precision. Accepted coordination messages: initial API `msg_514472d173b1`, exact
schema `msg_09abda17ba31`, root integration confirmations `msg_e38def65fc11` and
`msg_c35978834cbb`. This implements the CPU/text-only boundary in
[decision 0003](../decisions/0003-compiled-evidence-graph.md) without changing it.

Input bounds: 65,536 scalars, 4,096 candidate/neural proposals, depth 32, 512 AST
nodes, 2,048 tokens/schema mentions. Protection spans are sorted/merged for
bounded scanning. Conditionals, invalid scope, limit violations and unresolved
slot references produce explicit unsupported/unknown results, never a flattened
true assertion set. No organizer files, frozen scores, model weights, raw old
outputs, contracts, scripts, external services, pushes or deployments changed.

## Verification

All Rust commands use `veridyct:dev` (Rust 1.90), `--user root --network none`,
the shared `veridyct-mvp-registry` registry volume, and dedicated
`veridyct-parser-v3-program-target` at `/workspace/target`, with
`CARGO_TARGET_DIR=/workspace/target`. The host has no Cargo. The initial non-root
attempt failed on target-volume ownership; the corrected root container builds
without host installation or network.

- `cargo test --locked --offline --manifest-path tools/claim_program/Cargo.toml`:
  18 semantic tests passed; 256 deterministic malformed cases are included.
- `cargo clippy --locked --offline --manifest-path tools/claim_program/Cargo.toml --all-targets -- -D warnings`:
  passed with no warnings.
- `cargo fmt --manifest-path tools/claim_program/Cargo.toml -- --check`: passed;
  no ownership-external source file changed.
- `cargo xtask check`: passed formatter, all-workspace Clippy, 366 local links,
  graph checks and organizer-file checksums. The initial docs attempt could not
  resolve the Windows `.git` worktree pointer in Linux. The successful rerun
  mounted `C:\Users\Teodor\orca\QA-DNA-JEV\.git` read-only at `/repo-git` and set
  `GIT_DIR=/repo-git/worktrees/parser-v3-program`, `GIT_COMMON_DIR=/repo-git`,
  `GIT_WORK_TREE=/workspace`, `GIT_CONFIG_COUNT=1`,
  `GIT_CONFIG_KEY_0=safe.directory`, `GIT_CONFIG_VALUE_0=/workspace`.
- `cargo xtask test`: all 79 foundation tests passed. Both xtask commands use
  `CARGO_NET_OFFLINE=true`; this staged module is compiled through the isolated
  harness until root adds the public export.
- `cargo build --locked --offline --release --manifest-path tools/claim_program/Cargo.toml`:
  passed.
- `py -3.14 -X utf8 tools/claim_program/smoke.py prepare`, release adapter, then
  `py -3.14 -X utf8 tools/claim_program/smoke.py validate`: all 2,000 expected
  structures passed and all 1,000 counterfactual metadata pairs were identical.
  Input/output/metrics/receipt remain ignored under
  `artifacts/parser-v3-program/smoke/`. No old raw output was overwritten.

Tests establish all three-valued truth-table pairs in both orders, nested
quantifiers and negation, incomplete leaves, positive projection, exact comparator
boundaries, aliases and explicit slot dates, missing references, caller refusal
of incompatible currency/period, quoted descriptions and names, local values,
Unicode offsets/contractions, invalid candidate spans, neural isolation,
malicious depth/node/input bounds, empty groups, and 256 deterministic malformed
Unicode/syntax cases. Extra regressions ensure literal `version 2.3.0` is not a
second slot and `Cloud` inside `cloud_provider` is not another subject.
Development-time assistant-authored semantic fixtures have no independent
accuracy meaning. No full neural training or official checker was run.

The final release smoke run parsed 2,000 rows in `0.050380106 s`, peak process RSS
`20,196 KiB`, one parser thread, under Docker's 2 CPU / 6 GiB limit, Linux x86_64,
AMD Ryzen 9 6900HS, Rust `1.90.0 (1159e78c4 2025-09-14)`. This is parsing plus
output-object construction; it excludes schema/input preparation, serialization,
neural inference and candidate generation. The development-authored tiny syntax
cohort is a smoke measurement, not a general workload performance claim.

Fingerprints (SHA-256; final implementation working tree based on `22fa97b`):

- Input: `40f5c46cd6e353bdf688488feaf5dfbf09dfec02b12b6570d3c2198604c725dd`.
- Schema: `899e0e2326ba3e7f3b8f1cfcde44ede9f84c1992fa5affa77240a07ef64b70f5`.
- Output: `87a6817899b50a30cba3feaa6eece6eeee219aa4acd83e0161b785a663f255f0`.
- Production source: `27eb6179e7fce669a8d37c4d5d3cdb11824ccf80403c2ece45523040e97d6f65`.

## Limits and next integration step

Root must export the module, persist structured programs in extraction hints,
resolve exact evidence via callbacks, and forbid incomplete logical programs from
the flat GBT fallback. True OR/NOT programs must not license every atom as trusted
evidence. No truth-accuracy claim is made before independent integration testing.

The grammar intentionally does not infer conditionals, missing subjects/fields,
cross-clause ellipsis, implicit collections of schema subjects, or month-name
slot dates. Explicit caller-supplied document context and ordinary fact validity
scopes belong to root's context module. Leaves unresolved by the binder remain
unknown; disabling unaligned neural fallback can lower logical-row coverage.
Exact arithmetic/units and evidence uncertainty are callback responsibilities,
not functionality claimed by this parser harness.

Final implementation commit: `c3ae6590e924c7ebc24e2bd8465834e93abf4f7b`
(`Add bounded claim program parser and isolated semantic harness`). This handoff
is a separate documentation commit immediately after it; cherry-pick both from
`teodorbalan/parser-v3-program` to retain the validation record. The implementation
commit is based directly on `22fa97b` and requires root's agreed module export and
engine/CLI integration before production routing is enabled.
