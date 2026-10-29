# Verifier lab

Development-only training and evaluation; runtime inference is in
[boosted.rs](../../crates/core/src/boosted.rs). Read the
[handoff](../../docs/handoffs/verifier-lab.md) for scores, exclusions and limitations.
Install training dependencies with `py -3.14 -m pip install -r
tools/verifier_lab/requirements-research.txt`. Generated inputs, models, source
copies and reports belong under ignored `artifacts/`.

Stage the 390 diagnostic from the evaluator worker's ID file. `stage.py` reads
only explicitly allowed development releases when `--archive` is provided;
calibration/sealed gold are not opened. Run the frozen neural helper on
`practice-parser-input.json`, with no practice-form override, then rerun staging
with `--predictions` pointing to the resulting JSON array.

```powershell
py -3.14 tools/verifier_lab/stage.py --integration ../evidence-graph-runtime --test-ids ../evidence-evaluation/artifacts/parser390/test-ids.json --archive C:/Users/Teodor/Downloads/veridyct-evaluation-data-v3.zip
py -3.14 ../evidence-graph-runtime/tools/neural_parser/batch.py --bundle ../structured-extraction-training/artifacts/remote-results/selected-v2 --input artifacts/verifier-lab/practice-parser-input.json --output artifacts/verifier-lab/practice-parser-output.json --report artifacts/verifier-lab/practice-parser-report.json
py -3.14 tools/verifier_lab/stage.py --integration ../evidence-graph-runtime --test-ids ../evidence-evaluation/artifacts/parser390/test-ids.json --predictions artifacts/verifier-lab/practice-parser-output.json
```

Create a separate core-only snapshot with root's manifests and exact types.
The initial snapshot build updates its derived lockfile to remove other workspace
members; subsequent builds can use `--locked --offline`. Root's original
manifests and lockfile remain unchanged. `--reuse-core` keeps the frozen kernel
when refreshing only the owned evaluator/feature code.

```powershell
py -3.14 tools/verifier_lab/snapshot.py --integration ../evidence-graph-runtime --output artifacts/verifier-lab/exact-world --world-evaluator crates/core/examples/evaluate_world.rs --feature-evaluator crates/core/examples/verifier_features.rs
```

All Docker commands below use the lab checkout mounted at `/work` and working
directory `/work`, image `veridyct:dev`, user 0, 2 CPUs and 6 GiB. Build with
`CARGO_HOME=/work/artifacts/verifier-lab/cargo-home` and
`CARGO_TARGET_DIR=/work/target`. These are research-container commands, not the
official competition runner.

```sh
cargo build --release --manifest-path artifacts/verifier-lab/exact-world/Cargo.toml -p veridyct-core --example verifier_features --example evaluate_world
python3 tools/verifier_lab/export.py --names fit,validation,refit,practice390,production --modes inferred --output-dir artifacts/verifier-lab/exact-features
```

The original 50-candidate search is `train.py --mode inferred`. After fixing
the selected configuration, `--reuse-grid` consumes that unchanged search log
to refit against a separate feature/kernel snapshot; it does not tune on 390.
PowerShell log redirection can be UTF-16; the loader recognizes its BOM.

```powershell
py -3.14 tools/verifier_lab/train.py --mode inferred --reuse-grid artifacts/verifier-lab/train-inferred.log --features artifacts/verifier-lab/exact-features --tag exact --source-manifest artifacts/verifier-lab/exact-world/source-sha256.json
py -3.14 tools/verifier_lab/train.py --production --features artifacts/verifier-lab/exact-features --selection-report artifacts/verifier-lab/training-inferred.json --source-manifest artifacts/verifier-lab/exact-world/source-sha256.json
```

For the development world, retain original public CSV and lexicon under
`worlds/development/public/` and evaluator-only gold under its `gold/` directory.
The example's `--emit-parser-input` clears forms and removes only root-recognized
explicit interval prefixes. It does not read gold.

```sh
target/release/examples/evaluate_world --input artifacts/verifier-lab/worlds/development/public/universe.csv --emit-parser-input artifacts/verifier-lab/worlds/development/parser-input.json
```

Run the frozen public parser twice, then combine passes by public known labels.
The context pass uses actual input adjacency, not gold context metadata.

```powershell
py -3.14 ../evidence-graph-runtime/tools/neural_parser/batch.py --bundle ../structured-extraction-training/artifacts/remote-results/selected-v2 --input artifacts/verifier-lab/worlds/development/parser-input.json --output artifacts/verifier-lab/worlds/development/parser-output.json --report artifacts/verifier-lab/worlds/development/parser-report.json
py -3.14 ../evidence-graph-runtime/tools/neural_parser/batch.py --bundle ../structured-extraction-training/artifacts/remote-results/selected-v2 --input artifacts/verifier-lab/worlds/development/parser-input.json --output artifacts/verifier-lab/worlds/development/parser-context3-output.json --report artifacts/verifier-lab/worlds/development/parser-context3-report.json --context previous3text
py -3.14 tools/verifier_lab/mix_context.py --without-context artifacts/verifier-lab/worlds/development/parser-output.json --with-context artifacts/verifier-lab/worlds/development/parser-context3-output.json --output artifacts/verifier-lab/worlds/development/parser-mixed-output.json
```

Run the normal evaluator after parsing; use `--oracle-forms` only for a separately
named component diagnostic. Gold is loaded after normal predictions.

```sh
target/release/examples/evaluate_world --input artifacts/verifier-lab/worlds/development/public/universe.csv --practice /work/data/practice.csv --lexicon artifacts/verifier-lab/worlds/development/public/lexicon.json --gold artifacts/verifier-lab/worlds/development/gold/labeled.csv --parsed artifacts/verifier-lab/worlds/development/parser-mixed-output.json --output artifacts/verifier-lab/world-mixed-exact-v2.json
target/release/examples/verifier_features artifacts/verifier-lab/inputs/practice390-inferred.json data/lexicon.json artifacts/verifier-lab/parity-exact390.jsonl artifacts/verifier-lab/models/inferred-no_lexical-gbt-exact.json
```

Verify features, logits, scores and training exclusions on the host:

```powershell
py -3.14 tools/verifier_lab/parity.py --model artifacts/verifier-lab/models/inferred-no_lexical-gbt-exact.json --reference-features artifacts/verifier-lab/exact-features/practice390-inferred.jsonl --rust-output artifacts/verifier-lab/parity-exact390.jsonl --test-targets artifacts/verifier-lab/targets/practice390.json --output artifacts/verifier-lab/parity-exact390.json
```

`PRODUCTION-all-practice-gbt.json` is a different artifact with all public practice
labels. Never pass it to any heldout evaluation. The public partition guard
rejects it against the diagnostic's training rows.
