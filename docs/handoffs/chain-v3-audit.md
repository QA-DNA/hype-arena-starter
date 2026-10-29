# Chain v3 production-router audit

Task `task_97841131e50b`, dispatch `ctx_8688911b95b3`, worker chain-v3-audit;
human owner unassigned. Base `6a9b997e52429b986a83203b0a4fd65209cd7b80`;
coordinator interface commit `d8d1af4` was cherry-picked as `b268d31`.
Scope: [router](../../crates/core/src/kb_chain.rs),
[new regression tests](../../crates/core/tests/kb_chain_router_audit.rs), this handoff.
No organizer files, runtime model, final challenge gold, engine or CLI were edited.

## Result

Production rejects empty assertions, absent labelled comparisons, unresolved
names even beside a known-name distractor, explicit unknowns, incomplete
conjunctions and conflicting current-date observations. Independently resolved
typed proofs keep the engine prediction, including confidence and provenance;
an exactly refuted conjunct still dominates an unknown conjunct. Logical program
rows keep the engine because a positive fact bag cannot represent OR/NOT/comparisons.
Confidence retains full precision. Source identity is checked; normalized text
duplicates are excluded, production pages coalesce the same date, labelled source
duplicates are suppressed, and repeated predicates get one vote per key/date.

`run` and `guarded` retain their reference calculations and G1 behavior. Production
uses separate input preparation and duplicate-vote handling. The chain still uses
unlabelled statements as statistical inputs, never accepted typed evidence. Float
chain states remain separate from the exact rational/value graph. Observation
dates are not validity boundaries: earlier/later labelled observations can inform
a statistical estimate; explicit validity ranges are not extrapolated. A false
compound supplies no atom-wise negative without independent premises.

The three output fields are normalized decision weights, **not independently
calibrated three-class probabilities**. Decided chain weights split confidence
between true/false with zero unsure weight; a newly imposed abstention is one-hot
unsure. Existing engine abstentions retain their original uncertainty weights.
The old practice-fitted CONF_SCALE is retained, without decimal rounding or a
claim that it calibrates the changed production policy.

## Verification and measurements

Docker image `veridyct:dev` ID
`sha256:fd69385ab339602c033529a3b21e751750ad6757f148e3a894e953800fa79210`,
Rust 1.90.0, Linux x86_64, safe CPU Rust, two Cargo build jobs, networking disabled.
Windows command prefix (the image's non-root user could not write the new volume;
the first attempt failed with permission denied, so checks used container root):

```powershell
$chainWorkspace = (Get-Location).Path
docker run --rm --user 0:0 --network none `
  --mount "type=bind,source=$chainWorkspace,target=/workspace" `
  --mount "type=volume,source=veridyct-chain-v3-target,target=/workspace/target" `
  --mount "type=volume,source=veridyct-mvp-registry,target=/usr/local/cargo/registry" `
  -w /workspace -e CARGO_BUILD_JOBS=2 veridyct:dev cargo test --locked `
  -p veridyct-core --test kb_chain_router_audit --test kb_chain_parity
```

Focused checks passed: 11 new semantic regressions, four parity test functions
(the optional Sdev test returns early because its private local fixture was not
provided), and one intentionally ignored practice diagnostic. Practice reference
parity: 7,021/7,021 labels, maximum confidence error 2.22e-16; G1 390/390 matches.
No parity fixture/checker was weakened. The previous router's live-20-row
foreign-name test was replaced by independent synthetic vocabulary cases.

`cargo xtask test` passed the complete workspace: 117 tests passed and the one
diagnostic was ignored. `cargo xtask check` passed formatting and checked the
changed production code, but failed on an existing out-of-scope Clippy
`cmp_owned` warning at `crates/core/src/engine.rs:1406` (`"2026-02-01".to_owned()`
used only for comparison); the coordinator must fix that owner-controlled file.
Documentation validation follows Clippy in xtask and was not reached.

The diagnostic command replaces the cargo arguments above with:

```text
cargo test --locked -p veridyct-core --test kb_chain_router_audit practice_page_folds_report_route_metrics -- --ignored --nocapture
```

Five existing P80 page folds (1,897 targets, original class counts 1,581 true /
277 false / 39 unsure), gold forms supplied, training only visible labelled rows.
These familiar practice folds are a development diagnostic, not independent
generalization or calibration evidence. Brier3 is the mean sum of three squared
class errors. Baseline source blob `a24e88d8797b70f38d2641488d7033ecc67bfd08`;
rejected neutral-vote candidate blob `dd988236476eca049eb5d526d6dbe1709b725e29`.

| Policy | Arena | Coverage | Brier3 | True recall | False recall | Unsure recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Previous production router | 0.8408 | 0.9905 | 0.1534 | 1534/1581 | 203/277 | 0/39 |
| Neutral target emissions plus safety guards (rejected) | 0.6653 | 0.7406 | 0.5560 | 1135/1581 | 185/277 | 27/39 |

Neutral emissions materially worsened arena and proper score and were rejected.
The final policy retains statistical votes with the duplicate cap. Its full
five-fold accuracy/Brier comparison was not completed after the coordinator's
release deadline; do not transfer the baseline numbers to the changed router.
The two measured debug-profile diagnostic runs took 147.91 and 126.50 seconds;
these are not release performance benchmarks and peak RSS was not measured.

## Remaining caveats

The capitalized-token guard is conservative, not a complete owner recognizer;
proper owner grounding belongs to the coordinator's shared parser. Global
date pages approximate source pages because input has no explicit document/page
identity. Duplicate votes across different dates can still influence the
statistical timeline; they cannot become typed proof, and no labelled comparison
forces abstention. State/cell/step caps remain in place with engine fallback.
No new release performance, final Docker/official checker, independent confidence
calibration, or reserved challenge evaluation is claimed here. Final image and
cross-component integration are coordinator-owned.

Final source Git blobs before report creation: router
`e2424e4fe27d19971723150ec91c22b47a9d4567`, new tests
`3c737b3ea8c8a5451ce18ebd52e4fb11da2657e3`; unchanged parity test
`66ba9b72ae3ab001966cbaa48920c224ba26da91` and fixture
`d01008d095a33bb44f79703f10e7388736fdb7d2`.
