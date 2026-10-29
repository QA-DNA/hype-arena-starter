# Future C++ and CUDA scope

Read [root instructions](../AGENTS.md). This directory contains a future-extension policy
only. No native library, CUDA dependency, or GPU task is currently implemented.

- Work here only when a task explicitly calls for native acceleration. A roadmap entry
  does not justify implementing or provisioning GPU infrastructure.
- Establish a CPU reference and a representative measured bottleneck first.
- Prefer established libraries for standard matrix/tensor operations. Custom kernels need
  a measurable reason, regression cases, and reproducible performance evidence.
- Include data transfers, synchronization, allocations, and warm-up in the measurement
  appropriate to the actual workload. Report both steady-state and end-to-end behavior.
- Specify hardware architecture, toolkit, driver, precision, batch shape, and build flags.
- Isolate Rust/native interaction behind a narrow boundary with documented ownership,
  lengths, alignment, lifetimes, error codes, thread safety, and asynchronous completion.
- C++ exceptions must not cross a C ABI boundary; buffers must outlive asynchronous work.
- FP16/BF16 require numerical comparison with a suitable reference and task-level accuracy
  checks. Do not use reduced precision for exact facts, money, dates, or identifiers.
- The competition build and normal developer setup must not link or initialize CUDA.
  Keep GPU verification opt-in on compatible hardware and preserve a correct CPU path.
- Any added C++ compiler/CMake/CUDA configuration must be versioned and reproducible.
  A kernel-only speedup is not automatically an application speedup.
