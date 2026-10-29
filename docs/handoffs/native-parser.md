# Native selected-v2 Rust parser

- Task: `task_1137e36399cd`, dispatch `ctx_6cc61a652bf3`.
- Status: delivered; standalone native image, API, parity and resource validation complete.
- Human owner: unassigned. Agent owner: native Rust CPU parser worker.
- Branch: `teodorbalan/evidence-native-parser`; isolated checkout
  `C:/Users/Teodor/orca/workspaces/QA-DNA-JEV/evidence-native-parser`.
- Base commit: `d0af1691d49887870eb6dd638cf439afb7e7182d` plus the uncommitted files listed below.
- Scope: [standalone crate](../../crates/extractor/Cargo.toml),
  [native Dockerfile](../../Dockerfile.native-extractor),
  [native tools/instructions](../../tools/native_parser/README.md), this handoff.
- Acceptance: frozen preprocessing/decoding parity, public practice and official
  390 prediction parity, regression tests, real offline 2-CPU/6-GiB UID-10001
  container measurement, image below 3 GiB, recorded SHA256 provenance.

The port retains the frozen 24,850,029-byte selected-v2 three-BiLSTM ensemble.
There is no retraining, LLM decoding, truth lookup, GPU or CUDA dependency.
Native Rust implements grammar candidates, Python 3.11/Unicode 14 tokenization,
word/character IDs, candidate/clause tensor pooling and threshold-0.5 decoding.
Integer values preserve arbitrary precision; decimals and model scores follow
the frozen Python float semantics. Source-date qualifiers remain caller-owned;
the port does not rewrite text before inference.

## Integration boundary

`Extractor::load(bundle, Options)` creates one reusable CPU session;
`extract_batch(&mut self, &[InputRow]) -> Result<BatchOutput>` retains row fields,
supplied nonempty forms, ordering and duplicate IDs. Only current text and an
explicit context policy become features. Default context is `none`; the optional
`previous3text` policy uses only the preceding three public input texts.

CLI executable: `/opt/veridyct-extractor/veridyct-extractor`. Image:
`veridyct-native-extractor:selected-v2`. Bundle: `/opt/veridyct-extractor/model`.
Arguments preserve the optional Python adapter's contract:
`--bundle DIR --input FILE --output FILE --context none`, with optional
`--report`, `--practice-csv`, `--threads`, `--batch-size` and `--batching`.
The [tool instructions](../../tools/native_parser/README.md) give complete commands.

The optional `hybrid` Docker target copies coordinator-built solver and API
binaries from `SOLVER_IMAGE`, sets `VERIDYCT_NATIVE_EXTRACTOR`, and runs under
`USER 10001`. Default build remains a standalone extractor. This task does not
edit root Cargo.toml/Cargo.lock, core, CLI, root Dockerfile or organizer files.
The nested crate has its own workspace/lockfile pending explicit integration.

## Frozen parity

Full request suite: **10,512/10,512** exact encodings, decoded forms, candidate
character spans and value text. This includes 1,897 public practice rows without
context, 390 frozen official development rows with their original preceding
public context, 8,088 unsealed synthetic development rows, and 137 targeted
regressions/context requests. One whitespace-only regression is explicitly
rejected by both runtimes; the suite checks the same rejection.

All **390/390 official** and **8,088/8,088 synthetic** predictions also match the
original frozen `cpu-dev-predictions.jsonl`, independently of the fresh oracle.
Maximum absolute same-batch score difference: `1.2384643555130026e-7`.
Exact preprocessing covers all eight value kinds, currency/period variants,
comparison operators, dates, versions, multi-clause rows, Unicode character
offsets/case folding, non-ASCII digits, unknown names and large exact integers.
These are port-parity results, not independent extraction or truth accuracy.
No sealed/calibration gold was opened or used to tune the port.

Reference/model inputs are pinned in
[provenance.json](../../tools/native_parser/provenance.json). The model SHA256 is
`98eebdb851849f689c60499a9f4b2514305d520a523816b0505e98bba4523b6f`.
ONNX Runtime `libonnxruntime.so.1.23.2` is copied from the existing verified
Python wheel image and pinned as
`718c3fb0785d5ea06061b92c32ce4ad35be1bd4c71ae6192efe06f1ab21f0f8a`.
No unverified binary is downloaded. Model/runtime files remain ignored.

## Padding experiment

The frozen recurrent model processes padded tokens internally before masking.
Its predictions can therefore change with padded sequence length even when
preprocessing is identical. On all 1,897 public practice rows:

| Python policy comparison | Forms changed |
| --- | ---: |
| Unpadded batch1 vs default padded batch48 | 5 |
| Default batch48 vs deterministic shuffled batch48 | 7 |
| Unpadded batch1 vs optional exact-length groups | 0 |
| Exact-length groups vs shuffled exact-length groups | 0 |

Rust matches Python **1,897/1,897** under each of those five configurations.
Native preprocessing/inference seconds in this shared Docker run: batch1 3.342,
padded48 2.137, shuffled padded48 2.035, exact-length48 1.761, shuffled
exact-length48 1.807. Python: 3.368, 1.686, 1.613, 1.574, 1.608 respectively.
These are diagnostic single-run timings, not a statistically isolated speed claim.
Default padded behavior is preserved. `--batching exact-length` is explicitly
experimental; the coordinator owns any accuracy A/B and adoption decision.

## Verification and resource measurement

The crate forbids unsafe code. Six ordinary Rust tests pass without weights;
three model-dependent tests pass when explicitly enabled with the staged bundle,
verified native library and `--ignored --test-threads=1`. The latter include
shape-matched Python oracles for batches 1/7/48, original-row preservation,
metadata isolation, unsupported input isolation, public exact-text reuse and
conflict handling. CLI tests pass malformed schema, invalid thread count,
tampered weights and same-path refusal without partial output. Clippy passes
with warnings denied. `cargo xtask check` passes formatting, Clippy, documentation,
graph checks and organizer-file hashes. Docker needs the Windows worktree's common
Git directory mounted read-only at `/repo-git`, with
`GIT_DIR=/repo-git/worktrees/evidence-native-parser` and `GIT_WORK_TREE=/work`;
without this, the worktree's absolute Windows `.git` pointer cannot resolve in Linux.
`cargo xtask test` passes all 23 foundation tests. Standalone `cargo fmt --check`,
`cargo clippy --all-targets -- -D warnings`, six ordinary tests and all three
explicitly enabled release model tests pass on the final source. Python
development-tool syntax compilation also passes. The standalone release image
was tested after the final runtime change; subsequent edits only document results
and collect existing receipts.

Release benchmark: 20,000 repeated public practice texts, batch48, padded default,
no context, two intra-op CPU threads and one inter-op thread. Hardware: AMD Ryzen
9 6900HS, Docker Desktop Linux x86_64, Rust 1.90 release, base commit above and
uncommitted source hashes recorded in the
[validation receipt](../../tools/native_parser/validation.json). This benchmark
measures throughput and resource use; repeated practice is not unseen accuracy.

| Actual measurement | Value |
| --- | ---: |
| Preprocessing and inference | 19.7145 seconds |
| Process time through report creation | 19.9197 seconds |
| Docker start through exit, including file output | 20.6355 seconds |
| Process peak RSS | 302,716 KiB |
| Cgroup peak memory | 292,261,888 bytes |
| Final image size | 200,846,023 bytes |
| Rows / extracted assertions | 20,000 / 24,392 |
| Unsupported rows / OOM / exit status | 0 / false / 0 |

Actual Docker restrictions: `--network none --read-only --cpus 2 --memory 6g`,
UID 10001, `cpu.max=200000 100000`, memory limit 6,442,450,944 bytes. The harness
also checks that `/opt/veridyct-extractor` cannot be written and Python/Cargo are
absent. Image digest:
`sha256:1f21cd9400a76881e0ea1cec5e41ca6e51109cf8731ada13cd53ce5d3c5a1557`.
The complete Rust solver image was assembled and exercised by the coordinator;
this worker does not claim an official combined-system checker result.
The optional target in this Dockerfile also builds as
`veridyct-native-extractor:hybrid-validation` (219,796,689 bytes, `USER 10001`);
its offline, read-only `info` smoke test passes with the coordinator's current
`veridyct:evidence-rust` binaries. This separate validation tag leaves the
coordinator's integration tag untouched.

Ignored detailed receipts are under `tools/native_parser/artifacts/parity`,
`padding`, `benchmark-20000` and `cli-tests`. The checked-in aggregate validation
receipt contains the measurements, parity counts, exact source hashes and model/
native-library provenance. Native assets are at `tools/native_parser/model`,
`runtime` and `frozen`, all ignored. No commits, pushes or deployments were made.

## Safety boundary and limits

The safe [ort 2.0.0-rc.10 API](https://docs.rs/ort/2.0.0-rc.10/ort/)
owns input tensor storage, validates shapes/types and ties output lifetimes to
the session. Application code creates owned contiguous vectors, checks token,
candidate and span bounds before allocation, and releases borrowed outputs
before reusing the session. It introduces no custom FFI or unsafe Rust. ONNX
Runtime is a native C++ dependency outside Rust's memory-safety guarantee; its
exact CPU shared library is hash-pinned and exercised in the real container.

At most 384 total tokens, 24 encoded characters per token, 256 candidates and
64 predicted assertions are supported. Windows hold at most 512 encoded rows;
default batches are 48, configurable within 1–64, with intra-op threads 1–2 and
inter-op threads fixed to one. JSON input is bounded at 128 MiB; current text is
bounded at 65,536 characters. Current text is rejected instead of truncated.
Context keeps its final 96 tokens by the frozen contract. Failed preprocessing
or inference produces explicit row diagnostics, and recursive inference splitting
isolates failures. Atomic output uses buffered I/O for Windows bind-mount performance.

The frozen candidate grammar is still a heuristic subset of organizer value
forms. Unknown relations, shared-value ellipsis, long-distance context and
unsupported wording are not newly supported by this port. Scores are extraction
scores, not calibrated truth confidence. The standalone parser does not produce
competition verdicts, evidenced claims or a complete competition submission.
