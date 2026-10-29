# ADR 0001: Rust CPU baseline; native GPU acceleration deferred

Status: ACCEPTED FOR THE FOUNDATION. Date: 2026-10-28. The user authorized the Rust
workspace and development environment. Solver implementation and GPU provisioning remain
separate tasks; this decision does not authorize either by itself.

## Evidence

The [runtime contract](../../contracts/README.md) specifies two CPUs, 6 GiB RAM,
30 minutes, offline execution, a read-only root, and bounded writable paths.
The [official checker](../../scripts/check.sh) does not expose GPU devices.
The [challenge README](../../UPSTREAM.md) disallows an LLM as the submitted system.
GPU availability is therefore not a supported assumption; the rules do not need
to explicitly ban GPU experiments for this constraint to matter.

## Decision

Use Rust on CPU for the competition application, with a single core shared by the CLI
and API. Keep C++/CUDA outside the default build. Python is available for organizer
checking tools, and browser assets remain necessary for the required frontend.

## Consequences

Every teammate can develop without NVIDIA hardware. The runtime avoids CUDA dependencies
and GPU initialization. Performance work focuses first on data layout, algorithms, bounded
allocation, and actual CPU profiles. Hardware throughput does not establish semantic accuracy.

## Revisit conditions

An explicitly requested future workload has compatible NVIDIA hardware, a measured parallel
numeric bottleneck, validated precision tolerances, a CPU reference, and end-to-end evidence
that GPU acceleration improves the relevant metric including transfers and synchronization.

References: [NVIDIA container setup](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/sample-workload.html),
[CUDA performance guidance](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html),
[Rust FFI](https://doc.rust-lang.org/nomicon/ffi.html).
