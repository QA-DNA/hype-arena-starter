# Docker and laptop QA

Task: live-mvp / docker-qa. Agent owner: docker_qa; human owner unassigned.
Isolated branch: teodorbalan/mvp-docker-qa. Base: 2ced5d1.
Owned paths: [benchmark wrapper](../../tools/benchmark-arena.ps1) and this handoff.
Acceptance: verify final image sandbox, 20,000-row output completeness, memory and
runtime, plus explicit malformed-input/deadline failures. No production logic changed.

## Final image verified

Image: `sha256:f0272c73e801fa085c96e5ae46334c919cb1d89f027aa6afb0a27cf270f4b424`.
Unpacked size: 125,151,675 bytes, below 3 GiB; image USER is 10001.
Builder supplied source baseline: 6f2c52d, with Dockerfile toolchain-cache and example
format changes in the builder working tree. The image digest identifies tested code;
the benchmark checkout revision identifies only the harness, not the image source.
Production changes reported by the integrator: engine 343907a (integrated as
2f1bf5b), claims 71fe1cf (integrated as 2ced5d1), and UI fixes 5f58fc2. Root
be2587b subsequently adds documentation, Dockerfile and example formatting only.

The Windows arena wrapper matches every resource and isolation flag in the preserved
organizer `scripts/check.sh`: Linux amd64, no network, read-only root, UID/GID
10001:10001, 2 CPUs, 6 GiB memory and swap limit, 256 PID limit, all capabilities
dropped, no new privileges, `/tmp` tmpfs 128 MB, read-only `/universe`, writable
`/output`, and ARENA_DEADLINE. Docker inspect confirmed limits and no OOM.
The Linux checker uses chmod for bind directories; Docker Desktop maps Windows host
permissions instead. Actual runtime UID and filesystem write-access checks passed.
Neither wrapper enforces a filesystem quota on `/output`; output size is checked.

## Reproducible throughput measurement

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/benchmark-arena.ps1 -SourceCommit 6f2c52d
```

Hardware: AMD Ryzen 9 6900HS, 8 physical / 16 logical cores; Docker run capped at 2 CPUs.
Release binaries from the final runtime image. Core pipeline is single-threaded; the
benchmark adds a lightweight measurement shell and 50 ms `/proc` sampling.

Fixture: all 1,897 practice rows with supplied labels, then 18,103 synthetic unlabelled
near-template probes. Exactly four input columns; no forms. The probes append a QA
performance marker to practice text; their semantic labels are deliberately unknown.
This tests throughput and output completeness, not accuracy or unseen generalization.
Input SHA-256:
`c3e9f52f05c09d34f76ea36fa693b992f639b23dd0dfd0c0dbc4272b0dab363e`.

Measured 2026-10-28 16:19 UTC:

| Check | Result |
| --- | --- |
| Input rows | 20,000 |
| Required output labels | 18,103; all present once, in input order |
| Generated claims | Exactly 1,000 from 1,315 candidates |
| Text uniqueness/newness | 1,000 distinct normalized texts; none copies runtime input |
| Output | 803,789 bytes, below 16 MiB |
| Classification | 4.296 s |
| Complete CLI pipeline | 4.442 s |
| Wall time including Docker start/poll | 5.069 s |
| Cgroup memory peak | 124,293,120 bytes, including shell/page cache |
| Sampled process VmHWM | 122,988 KiB |
| Process exit / OOM | 0 / false |

The memory shell invokes the unmodified `/app/veridyct run`, reads the solver's
`/proc/<pid>/status` every 50 ms, and prints cgroup `memory.peak` after it exits.
Sampled VmHWM can miss a higher allocation after the final sample; it is not an exact
externally measured peak RSS. The measurement entrypoint differs from the default
entrypoint solely to collect these metrics. The parent separately runs the default
entrypoint under the organizer practice contract.

Ignored artifacts: `artifacts/benchmark-20261028-181943/` contains input hash,
container inspection, logs, output and validation JSON. An earlier run without RSS
sampling measured 4.373 s and cgroup peak 122,966,016 bytes on the identical fixture.

## Negative cases

All use final image and the same network/user/root/resource flags:

- ARENA_DEADLINE=1: exit 2 with `Arena deadline reached before next processing stage`;
  output directory remains empty.
- CSV date 2026-99-12: exit 2 with `CSV row 2 date must be a valid YYYY-MM-DD`;
  output directory remains empty.
- Container identity command returned 10001; `/app` is not writable and `/tmp` is
  writable; command exit 0.

Negative-case records are under ignored `artifacts/negative-qa/`. Hard deadline
SIGTERM behavior was not exercised by this short run. Schema and public grammar
validation belong to the separate contract QA task; synthetic truth was not judged.
