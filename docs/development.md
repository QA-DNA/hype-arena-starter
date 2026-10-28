# Development guide

The workspace uses Rust 1.90.0, Cargo.lock, and a small Rust task runner. The workbench
uses local HTML/CSS/JavaScript served by the API, with no Node installation or frontend
build required. Python 3 is only needed for the organizer's checker.

## First checkout

Install Git and Rust through [rustup](https://www.rust-lang.org/tools/install).
The first Cargo command honors rust-toolchain.toml and installs rustfmt and Clippy.
Cargo itself must already be available: doctor cannot bootstrap a missing compiler.

```sh
cargo xtask setup
cargo xtask doctor
cargo xtask dev
```

Visit http://127.0.0.1:8787. Ctrl+C stops the foreground process tree. The server also
handles SIGTERM on Unix. Restart after edits: hot reload is not implemented. Local
HTML/CSS/JS and the curated graph are embedded at compilation.

The first build downloads dependencies. Subsequent locked builds can use the local Cargo
cache. No network access is required by the compiled application itself.

## Operating systems

- Windows: WSL2 is recommended for Linux parity. Inside WSL, a checkout on its Linux
  filesystem generally avoids mounted-drive overhead. Native Windows is also checked in CI;
  install the MSVC C++ build tools required by the standard Rust Windows toolchain.
- Linux: install a linker/compiler through the OS package manager, or use the dev container.
- macOS: install Xcode Command Line Tools. Apple Silicon can develop natively; final Docker
  evaluation is linux/amd64. Do not compare emulated timings with native evaluator timings.
- Dev Container: reopen in a compatible editor. Docker must be running on the host. The
  container includes Rust, linker tools, Git, and Python; post-create runs locked setup.
  A Docker daemon is not mounted into it automatically. Run container checks on the host.

## Commands

| Command | Behavior |
| --- | --- |
| `cargo xtask doctor` | Required Rust/Git checks; optional Docker/Python diagnostics |
| `cargo xtask setup` | Fetch locked dependencies; no solver training or API calls |
| `cargo xtask dev` | Start the API and workbench in the foreground |
| `cargo xtask check` | Format check, Clippy, local links, graph validation, upstream hashes |
| `cargo xtask test` | Run tests across the workspace |
| `cargo xtask build` | Locked release build of the workspace |
| `cargo xtask docs` | Documentation, graph and original-file checks only |
| `cargo xtask graph` | Export curated relations and actual Cargo workspace dependencies |
| `cargo xtask context --scope core` | Bounded context with source commit and fingerprint |
| `cargo xtask arena-check` | Run the official Linux checker; expected to fail before solver completion |

Format changes with `cargo fmt --all`. The runner executes argument arrays and propagates
failures; it does not interpret shell command strings. Unknown options are errors.

## Local configuration

No credentials are needed. `.env.example` describes settings; native binaries do not load
`.env` files automatically. Set variables in the process environment.

PowerShell:

```powershell
$env:VERIDYCT_ADDR = '127.0.0.1:8788'
cargo xtask dev
```

Linux/macOS/WSL:

```sh
VERIDYCT_ADDR=127.0.0.1:8788 cargo xtask dev
```

Use different ports for separate checkouts. Bind to a public interface only when needed.

## Containers

```sh
docker compose up --build
docker compose down
docker build --platform linux/amd64 -t veridyct:local .
docker run --rm --network none --read-only veridyct:local info
```

Compose starts the live API with a read-only filesystem, 2 CPUs and 6 GiB RAM. Its local
HTTP port requires Docker networking. The same image defaults to the competition CLI,
which reads `/universe/universe.csv` and `/universe/lexicon.json` and atomically writes
`/output/output.csv`. The CLI container is separately checked with networking disabled.

`scripts/check.sh` requires Linux, Docker and Python 3. On Windows the team wrapper
reproduces its restrictions and calls the unchanged organizer scripts:

```powershell
powershell -ExecutionPolicy Bypass -File tools/arena-check.ps1
# Reuse a built image:
powershell -ExecutionPolicy Bypass -File tools/arena-check.ps1 -SkipBuild
```

Run artifacts are retained in ignored `artifacts/arena-*`. A passing format check does
not prove claim grammar or semantic truth; practice scores include familiar training
rows. The web Run button and the CLI use the same core implementation.

The reproducible CPU benchmark and diagnostic holdout are available with
`cargo run --release -p veridyct-core --example evaluate`. Record source SHA and run
under the 2 CPU / 6 GiB container limits when comparing timings. The
`tools/validate_claims.py` diagnostic reads an HTTP job snapshot and uses Python's
`jsonschema` and `referencing` packages for the organizer schemas. Its public grammar
and provenance checks do not replace the private referee.

## CI and performance

CI checks Ubuntu, Windows and macOS, plus a Linux amd64 runtime container. Caches are
partitioned by OS, architecture, compiler, profile and Cargo.lock. GitHub Actions use
pinned action revisions and read-only repository permissions.

Measure release builds on representative input and record hardware, active threads,
source commit, wall time, peak RSS and correctness. Shared CI timing is not a reliable
strict microbenchmark gate. Generated snapshots and run outputs belong in ignored artifacts/.

## Troubleshooting

- `cargo` not found: install rustup and reopen the shell; on WSL source its Cargo env file.
- Linker missing: install the OS linker tools described above.
- Port already used: set VERIDYCT_ADDR to a free port.
- Docker unavailable in doctor: native development still works; start Docker for image checks.
- Organizer checksum mismatch: inspect the diff and upstream revision; do not blindly accept it.
- Old UI after editing: stop and restart cargo xtask dev so assets are recompiled.
