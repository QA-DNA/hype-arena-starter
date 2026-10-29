# Native selected-v2 extractor

The standalone [Rust crate](../../crates/extractor/Cargo.toml) runs the exact frozen
24,850,029-byte, three-BiLSTM ONNX ensemble on CPU. It ports the frozen Python
value grammar, Unicode tokenization, metadata encoding, clause/candidate pooling,
softmax threshold and deduplication. It does not train a model or return truth
verdicts. The [handoff](../../docs/handoffs/native-parser.md) records measurements,
limits and integration status; [provenance.json](provenance.json) pins every input.
The checked-in [validation receipt](validation.json) records measured parity,
padding behavior, resource use and the exact source hashes.

## Stage and build

From the repository root in PowerShell, with Docker Desktop running:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/native_parser/stage.ps1 -Bundle 'C:/Users/Teodor/orca/workspaces/QA-DNA-JEV/structured-extraction-training/artifacts/remote-results/selected-v2'
docker build --platform linux/amd64 -f Dockerfile.native-extractor -t veridyct-native-extractor:selected-v2 .
```

Staging verifies fixed SHA256 hashes, copies the weights/metadata and reference
sources into ignored directories, and copies ONNX Runtime 1.23.2 from the existing
`veridyct-neural-parser:integration` Python wheel. It downloads no native binary.
The final image contains the Rust executable, CPU shared libraries and frozen
bundle; it contains no Python, Cargo, GPU provider or training framework.

The builder defaults to the local `veridyct:dev` Rust 1.90 image. A compatible
`rust:1.90.0-bookworm` image can be selected with `--build-arg BUILDER_IMAGE=...`.
Only the standalone crate and its own lockfile are compiled. The model, runtime
libraries, caches, outputs and generated parity data remain ignored.

## JSON adapter

Create an `io` directory containing a UTF-8 JSON array `rows.json`:

```json
[{"id":"example","text":"Hooly AI Pro costs €79 per month.","date":"2026-10-29","label":""}]
```

```powershell
$io = (Resolve-Path io).Path
docker run --rm --network none --read-only --cpus 2 --memory 6g --user 10001 --mount "type=bind,source=$io,target=/io" veridyct-native-extractor:selected-v2 --input /io/rows.json --output /io/filled.json --report /io/report.json
```

The executable is `/opt/veridyct-extractor/veridyct-extractor`; its default bundle
is `/opt/veridyct-extractor/model`. It also accepts `--bundle DIR`. Output is the
original array with extracted `form` arrays. IDs, dates, labels and arbitrary
extra fields are retained. Nonempty supplied forms are retained. Missing, null
and empty forms are eligible for extraction. Duplicate IDs and input order are
preserved. `--practice-csv FILE` explicitly enables literal public practice text
reuse; conflicting forms for identical text are excluded. Empty known forms can
be reused. No label, date, ID, supplied form or gold-named field enters a tensor.

`--context none` is the default. `--context previous3text` explicitly joins the
three preceding input texts, then keeps their final 96 tokens. It uses input
order and ignores all annotations and `previous_text` fields on InputRows.

Default `--batch-size 48 --threads 2 --batching padded` matches the Python batch
adapter: stable sort within 512-row windows, padded batches, original-order
restoration. The frozen BiLSTM itself has padding-sensitive outputs. The optional
`--batching exact-length` groups equal token lengths within each bounded window;
it is experimental and can change forms relative to the frozen padded default.

Limits: 128 MiB JSON input, 65,536 current-text characters, 384 total sequence
tokens including two markers, 24 encoded characters per token, 256 candidates,
64 predicted assertions, batch sizes 1–64, and one or two CPU intra-op threads
with one inter-op thread. Current text is never silently truncated. Unsupported
rows receive an empty form and a report diagnostic; later rows are still processed.
Schema, model-integrity, configuration and file errors exit 2. JSON files are
buffered and written atomically beside their destination; input/output paths
must differ. Parent output directories must already exist and be writable.

`--mode encode` and `--mode requests` accept explicit `[{id?,text,previous_text?}]`
arrays for preprocessing/inference diagnostics. They do not accept annotations as
features. Requests use the frozen direct request order and padded batching;
`exact-length` applies to the InputRow batch adapter only.

## Library

```rust,no_run
use veridyct_extractor::{Extractor, InputRow, Options};
# fn run(rows: &[InputRow]) -> anyhow::Result<()> {
let mut extractor = Extractor::load("/path/to/selected-v2", Options::default())?;
let result = extractor.extract_batch(rows)?;
// result.rows preserves all fields; result.report records unsupported rows.
# Ok(()) }
```

Set `ORT_DYLIB_PATH` to the verified shared library outside the image. The safe
`ort` API owns tensor buffers and session lifetimes; this crate forbids unsafe
Rust. Calls on an extractor are serialized through `&mut self`. The
[batch example](../../crates/extractor/examples/batch.rs) shows a complete adapter.

## Verify

Commands below run inside a Rust 1.90 environment from the repository root:

```sh
cargo test --locked --manifest-path crates/extractor/Cargo.toml
cargo fmt --manifest-path crates/extractor/Cargo.toml -- --check
cargo clippy --locked --manifest-path crates/extractor/Cargo.toml --all-targets -- -D warnings
ORT_DYLIB_PATH=/absolute/path/libonnxruntime.so.1.23.2 cargo test --release --locked --manifest-path crates/extractor/Cargo.toml --test frozen -- --ignored --test-threads=1
```

The three ignored tests deliberately require real staged weights and the native
library. Ordinary tests run without either. The frozen fixture records Python
oracle outputs separately for batch shapes 1, 7 and 48, since padding can change
the model's scores. To regenerate it, run `oracle.py` inside the reference image
on `regression-requests.json` with `--fixture` pointing to the fixture path.

The scripts are development tools; none enter the native runtime:

```powershell
py -3.14 -X utf8 tools/native_parser/prepare_parity.py --practice data/practice.csv --frozen-predictions 'C:/Users/Teodor/orca/workspaces/QA-DNA-JEV/structured-extraction-training/artifacts/remote-results/selected-v2/cpu-dev-predictions.jsonl' --synthetic-dev 'C:/Users/Teodor/orca/workspaces/QA-DNA-JEV/structured-extraction-training/artifacts/training-data/dev.jsonl' --out tools/native_parser/artifacts/parity
# Mount this repository as /work in veridyct-neural-parser:integration:
# python3 /work/tools/native_parser/oracle.py --root /work/tools/native_parser --requests /work/tools/native_parser/artifacts/parity/requests.json --out /work/tools/native_parser/artifacts/parity
# Run the native image's encode and requests modes on the same requests.json,
# writing native-encoded.json and native-predictions.json beside Python outputs.
py -3.14 -X utf8 tools/native_parser/compare.py --dir tools/native_parser/artifacts/parity
py -3.14 -X utf8 tools/native_parser/test_cli.py --out tools/native_parser/artifacts/cli-tests
py -3.14 -X utf8 tools/native_parser/benchmark.py --input tools/native_parser/artifacts/parity/benchmark-input.json --out tools/native_parser/artifacts/benchmark-20000
```

`padding_probe.py` measures Python batch1/batch48/shuffle/exact-length outputs,
then `--native-image veridyct-native-extractor:selected-v2` runs corresponding
native containers and requires row-by-row parity. Its `--input` is the stripped
public `batch-input.json`, and `--out` is an ignored measurement directory.
Only public practice and unsealed development inputs/predictions are used.

## Complete solver image

After the coordinator's solver image includes its native-extractor selector:

```powershell
docker build --platform linux/amd64 --target hybrid --build-arg SOLVER_IMAGE=veridyct:evidence-rust -f Dockerfile.native-extractor -t veridyct:evidence-native .
```

The optional target copies both `/app/veridyct` and `/app/veridyct-api` from that
image and sets `VERIDYCT_NATIVE_EXTRACTOR` to the native executable. The complete
solver's reasoning, evidence, claim generation and official checker remain owned
by the coordinator. This standalone crate has an isolated `[workspace]` and lock;
root workspace integration requires an explicit coordinator change.
