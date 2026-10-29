# Staged belief composition checks

This isolated crate includes the production [belief module](../../crates/core/src/belief.rs)
by path while the coordinator owns the core exports and runtime wiring. It depends on
the core `claim_program` export from interface commit `d8d1af4` (cherry-picked here as
`54ee9eb`). It adds no runtime dependency to the core.

Run in the repository root with Rust 1.90:

```text
cargo test --locked --offline --manifest-path tools/belief/Cargo.toml
cargo clippy --locked --offline --manifest-path tools/belief/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path tools/belief/Cargo.toml -- --check
```

The worker uses `veridyct:dev`, no network, two CPUs, 6 GiB, user 0, the checkout
mounted at `/workspace`, `veridyct-belief-v3-target` at `/workspace/target`, and
`veridyct-mvp-registry` at `/usr/local/cargo/registry`. Set
`CARGO_TARGET_DIR=/workspace/target` and work in `/workspace`. The separate target
keeps concurrent workers from sharing build outputs; cached dependencies are the
existing shared registry.

The hand-written tests are development-time assistant-authored semantic fixtures,
not training examples or independent accuracy/calibration measurements. The
correlated-world test enumerates finite joint states solely to check bound
containment. No live20, challenge gold, or synthetic training labels are read.
The module never assumes atom independence and never turns a scalar chain score
into a complete three-class posterior. See the
[handoff](../../docs/handoffs/belief-v3.md) for the integration contract and limits.
