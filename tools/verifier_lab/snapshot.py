"""Copy integration source to an ignored snapshot, recording byte-level hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--world-evaluator", type=Path, help="Build an isolated core-only Cargo snapshot with this evaluator")
    parser.add_argument("--feature-evaluator", type=Path, help="Also stage reusable verifier features against the copied core")
    parser.add_argument("--reuse-core", action="store_true", help="Keep existing frozen source/manifests while updating evaluator code")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    cargo_snapshot = bool(args.world_evaluator or args.feature_evaluator)
    sources = list((args.integration / "crates/core/src").glob("*.rs")) if cargo_snapshot else [args.integration / "crates/core/src" / name for name in ("engine.rs", "forest.rs", "knowledge.rs", "model.rs", "temporal.rs")]
    if cargo_snapshot:
        sources += [args.integration / name for name in ("Cargo.toml", "Cargo.lock", "crates/core/Cargo.toml", "rust-toolchain.toml")]
    for source in sources:
        name = str(source.relative_to(args.integration)).replace("\\", "/") if cargo_snapshot else source.name
        target = args.output / name if cargo_snapshot else args.output / "src" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not args.reuse_core or not target.exists():
            shutil.copyfile(source, target)
        fingerprint = hashlib.sha256(target.read_bytes()).hexdigest()
        if not args.reuse_core and hashlib.sha256(source.read_bytes()).hexdigest() != fingerprint:
            raise RuntimeError("Source changed while snapshotting: " + str(source))
        hashes[name] = {"source": str(source), "sha256": fingerprint}
    if cargo_snapshot:
        manifest = args.output / "Cargo.toml"
        text = manifest.read_text(encoding="utf-8")
        manifest.write_text(re.sub(r"(?m)^members = \[.*\]$", 'members = ["crates/core"]', text), encoding="utf-8")
    if args.world_evaluator:
        evaluator = args.world_evaluator.read_text(encoding="utf-8")
        evaluator = re.sub(r"#\[rustfmt::skip\].*?mod temporal;", "use veridyct_core::{engine, model, temporal};", evaluator, count=1, flags=re.S)
        target = args.output / "crates/core/examples/evaluate_world.rs"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(evaluator, encoding="utf-8")
        hashes["snapshot_adaptations"] = {"workspace_members": ["crates/core"], "evaluator_source": str(args.world_evaluator), "evaluator_sha256": hashlib.sha256(args.world_evaluator.read_bytes()).hexdigest(), "note": "Evaluator imports the copied core library instead of external snapshot modules; manifests otherwise preserved"}
    if args.feature_evaluator:
        evaluator = args.feature_evaluator.read_text(encoding="utf-8")
        evaluator = re.sub(r'#\[path = "[^\"]*/engine.rs"\].*?mod temporal;', "use veridyct_core::{engine, knowledge, model};", evaluator, count=1, flags=re.S)
        target = args.output / "crates/core/examples/verifier_features.rs"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(evaluator, encoding="utf-8")
        boosted = args.feature_evaluator.parent.parent / "src/boosted.rs"
        shutil.copyfile(boosted, args.output / "crates/core/src/boosted.rs")
        hashes["feature_evaluator"] = {"source": str(args.feature_evaluator), "sha256": hashlib.sha256(args.feature_evaluator.read_bytes()).hexdigest(), "boosted_sha256": hashlib.sha256(boosted.read_bytes()).hexdigest()}
    (args.output / "source-sha256.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(json.dumps(hashes, indent=2))
