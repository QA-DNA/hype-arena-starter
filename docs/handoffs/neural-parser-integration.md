# Frozen neural parser integration

Task owner: parser integration worker, `task_c369540ba504`, 2026-10-29.
Human ownership remains unassigned. Branch: `teodorbalan/evidence-parser-integration`,
base `d0af1691d49887870eb6dd638cf439afb7e7182d`.

## Scope and decision

Deliver a working offline CPU batch adapter for the strongest frozen BENGEE
extractor. Owned changes are [the adapter](../../tools/neural_parser/batch.py),
its byte-preserved frozen source,
[Dockerfile.neural](../../Dockerfile.neural), and this handoff. No core, CLI,
default Dockerfile, organizer data/contracts/scripts, training or model selection
was changed by this worker. The coordinator owns the optional Rust invocation
and evidence integration in the separate `evidence-graph-runtime` checkout.

This implementation uses **Python 3.11, NumPy and ONNX Runtime CPU**, with Rust
remaining the hybrid image's entrypoint. It is not a standalone Rust neural
extractor. A native ONNX/grammar port was assessed and deferred: the frozen Python
candidate grammar, Unicode token offsets, regular expressions and batching would
all require independent parity work within the short integration window. Copying
the frozen source exactly provides a reviewable working fallback. Host Python is
available through `py -3.11`; the bare `python` command is a Windows Store stub.

The model is a discriminative ensemble of three char-CNN/BiLSTM classifiers,
with static GloVe embeddings. There is no LLM decoder, API call, CUDA or PyTorch
runtime dependency. Extraction states what text claims, including false values;
the core must independently establish truth and evidence. The adapter neither
produces truth labels nor reads sealed gold. No retraining or threshold tuning
was performed.

## Interface

```sh
python3 /opt/veridyct-extractor/batch.py \
  --bundle /opt/veridyct-extractor/model \
  --input /output/parser-input.json \
  --output /output/parser-output.json \
  --report /output/parser-report.json
```

Input and output are JSON arrays of `{id,text,date,label,form?}` objects. Each
`id`, `text` and `date` is a string. Labels and additional fields are preserved.
Only text and, if explicitly enabled, prior public text reach the model.

- Nonempty supplied forms are preserved. Missing, null and empty forms are
  eligible for extraction, matching Rust's default `Vec<Fact>` serialization.
- Optional `--practice-csv PATH` reuses literal exact practice text forms before
  inference, including known empty forms. Conflicting duplicate texts are not
  reused. It supplies no external facts or truth verdicts. The coordinator's core
  also owns its exact-practice override independently of this option.
- Output order, IDs, text, date and labels are preserved, including duplicate IDs.
  The adapter returns typed forms, without inserting a model truth score.
- Default `--context none` ignores even supplied `previous_text` or gold-named
  fields. `--context previous3text` is explicitly experimental: only the actual
  preceding three input text strings are joined, with no gold pointers. The
  frozen encoder retains the final 96 context tokens. CSV adjacency is not a
  reliable antecedent guarantee.
- The frozen total token limit is 384, including two marker tokens and context.
  Current text is rejected rather than silently truncated. Additional adapter
  limits are 65,536 current-text characters, 256 candidates and 64 predicted
  assertions per row. A rejected row gets an empty form and a structured stderr
  diagnostic; subsequent rows continue. Inference batch failures are bisected to
  isolate an offending row.
- Default batch size is 48, constrained to 1..64; CPU threads are 2, constrained
  to 1..2. Encoded windows contain at most 512 rows and are length-sorted before
  batching. Forms are restored to original positions afterward.
- Malformed input, missing files or checksum mismatches exit 2 with a structured
  error and no newly written output. Successful row-level unsupported inputs
  exit 0 and are counted in the optional report. JSON files are written atomically
  using temporary files in their requested parent directory, normally `/output`.

Python callers can `from tools.neural_parser import BatchExtractor`, initialize
one session with `BatchExtractor(bundle)`, then call `extract_rows(rows)` for
`(output_rows, report)`. Serialize calls on an instance. The frozen source's
generic module names are restored after loading so the embedding application's
imports remain intact.

## Artifact provenance and build

[provenance.json](../../tools/neural_parser/provenance.json) pins every frozen
source and bundle file. The original freeze was `2026-10-28T23:04:51.892639+00:00`.
The selected ONNX model is 24,850,029 bytes, SHA256
`98eebdb851849f689c60499a9f4b2514305d520a523816b0505e98bba4523b6f`.
Metadata SHA256 is
`3ab93d76b178bb714bd4c5ac665da2de0d97c29a46d32597ca43be3e52c08567`;
lexicon SHA256 is
`40d591b7e0345172f2822742c1d1b2cda69619c564ff23dd306d11984756747c`.

The peer source is the read-only sibling
`structured-extraction-training/artifacts/remote-results/selected-v2`. Its
`runtime.py`, `grammar.py` and `prepare.py` are copied byte-for-byte under
`tools/neural_parser/frozen`. Only the tokenizer is invoked from the preparation
module; its training functions are never called. Model, metadata, lexicon,
staged contexts and run outputs stay under ignored `artifacts/neural-parser/`.
No weights or generated predictions belong in Git.

From the repository root, stage a fresh context with PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/neural_parser/stage.ps1 `
  -Bundle ../structured-extraction-training/artifacts/remote-results/selected-v2
docker build --platform linux/amd64 --target neural-parser `
  -f Dockerfile.neural -t veridyct-neural-parser:integration artifacts/neural-parser/build
```

The staging script refuses an existing output directory; use `-Output` to choose
another fresh directory rather than overwriting artifacts. It validates the
frozen source and model hashes. The image validates again during build, and the
adapter validates them before initializing its session. The Python base is pinned
by SHA256; runtime requirements, including transitive dependencies, are pinned to
the frozen image's versions. Dependency downloads occur during build only.

Once the coordinator has built the current Rust solver image using the unchanged
default Dockerfile, build the optional hybrid:

```powershell
docker build --platform linux/amd64 --target hybrid `
  --build-arg SOLVER_IMAGE=veridyct:evidence-rust `
  -f Dockerfile.neural -t veridyct:evidence-neural artifacts/neural-parser/build
```

The hybrid copies `/app/veridyct` and `/app/veridyct-api`, sets
`VERIDYCT_NEURAL_HELPER=/opt/veridyct-extractor/batch.py`, and runs the Rust CLI
as UID 10001. `VERIDYCT_NEURAL_BUNDLE` is the coordinator's optional bundle-path
override. Both targets retain the Python dependencies; the default Dockerfile
remains the standalone Rust option. Build the helper target explicitly when the
solver image is unavailable. Hybrid end-to-end truth/claim acceptance belongs to
the coordinator; helper tests do not prove competition correctness.
The hybrid target was built successfully against `veridyct:evidence-rust` under
the separate local smoke tag `veridyct-neural-parser:hybrid-smoke`; the Rust `info`
command ran successfully offline as the configured entrypoint.

To invoke the helper, mount input/output files under `/output`:

```powershell
docker run --rm --network none --read-only --cpus 2 --memory 6g `
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 `
  --tmpfs /tmp:rw,nosuid,nodev,size=128m `
  --mount "type=bind,source=$((Get-Location).Path)/artifacts/neural-parser,target=/output" `
  veridyct-neural-parser:integration `
  --input /output/benchmark-input.json --output /output/benchmark-output.json `
  --report /output/benchmark-report.json
```

## Verification and limitations

Twelve adapter tests pass inside the offline constrained helper image. They cover
frozen single-row versus batch sizes 1, 7 and 48 parity, exact stated values 79
and 71, Unicode, duplicate IDs/order, preservation of supplied forms and metadata,
empty/null/missing forms, experimental context, oversized input continuation,
isolated inference failure, immutable weight hashes and atomic JSON output.
All 1,897 public practice forms are reused exactly in the public-practice option
test. A malformed JSON row exits 2 and creates no output. Python compilation
passes. No Rust source was changed, so workspace foundation and combined official
checker runs are left to the coordinator and are not claimed here.

Reproduce the adapter tests after building the helper:

```powershell
docker run --rm --network none --read-only --cpus 2 --memory 6g `
  --tmpfs /tmp:rw,nosuid,nodev,size=128m `
  --mount "type=bind,source=$((Get-Location).Path)/tools/neural_parser,target=/integration,readonly" `
  --entrypoint python3 veridyct-neural-parser:integration `
  -m unittest discover -s /integration -p test_batch.py -v
```

The 20,000-row performance sample repeats public practice text, strips forms and
labels, and performs neural inference on every row with context disabled. It is
a throughput sample, not an accuracy or generalization evaluation. Host: AMD
Ryzen 9 6900HS, 8 cores / 16 logical processors, Docker Desktop Linux amd64 on
WSL2; 2 CPU quota, 6 GiB memory, two ONNX intra-op threads and one inter-op thread.
The actual container used networking disabled, a read-only root filesystem,
UID 10001, capabilities dropped, no-new-privileges, 128 PIDs and a 128 MiB `/tmp`.
The `/output` bind mount had no filesystem quota.

Final measured run: 20.18 seconds container-command wall time, 18.10 seconds
application total, 17.74 seconds including preprocessing/inference; peak process
RSS 174,516 KiB (170.43 MiB). It produced
24,392 assertions, 703 empty predictions, zero unsupported rows and a
5,085,374-byte output. All 20,000 IDs, texts, dates, labels and order matched the
input. Maximum predicted assertions on any sample row was eight. Output bytes
were identical before and after the assertion-count guard. Final timing and
source hashes are recorded in ignored `benchmark-report.json`,
`benchmark-command.json` and `validation-summary.json` under
`artifacts/neural-parser/`. Adapter source SHA256 is
`116ab0be140600a7eff7f05907e7dc5c1258c7e49017acbc43261a2204858622`;
output SHA256 is
`0fe5be3c5b4e81130012f24cc4af9b43e1306eb3874e78e5d5408ee82bb708c1`.

The frozen model's known limitations remain: unsupported paraphrases, ambiguous
antecedents, missed values and semantically inappropriate attribute/unit pairings.
No confidence calibration or new blind accuracy result is supplied by this task.
Empty predictions and rejected rows must remain uncertainty for the core, not
fabricated evidence. No commit, push, remote deployment or organizer-file change
was performed.
