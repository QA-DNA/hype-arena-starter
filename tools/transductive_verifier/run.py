"""Reproduce the clean five-split statistical transductive experiment.

Run with host Python 3.14 (sklearn/numpy) and existing veridyct:dev Docker image.
All writes stay in this checkout and its own named Cargo cache volumes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def run(command: list[str], log: Path) -> None:
    print(json.dumps({"command": command}), flush=True)
    start = time.monotonic()
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(result.stdout)
    print(result.stdout.decode("utf-8", errors="replace"), end="", flush=True)
    print(json.dumps({"exit_code": result.returncode, "seconds": time.monotonic() - start, "log": str(log)}), flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)


def main(args) -> None:
    root = Path.cwd().resolve()
    base = args.directory
    if base.is_absolute() or ".." in base.parts:
        raise ValueError("Output must be relative to the current checkout")
    base.mkdir(parents=True, exist_ok=True)
    docker = ["docker", "run", "--rm", "--network", "none", "--user", "0", "--cpus", "2", "--memory", "6g",
              "-v", f"{root.as_posix()}:/work", "-v", "veridyct-transductive-registry:/cargo/registry",
              "-v", "veridyct-transductive-target:/target", "-e", "CARGO_HOME=/cargo", "-e", "CARGO_TARGET_DIR=/target", "-w", "/work", "veridyct:dev"]
    if not args.skip_stage:
        run([sys.executable, "tools/transductive_verifier/stage.py", "--integration", str(args.integration), "--output", str(base), "--splits", args.splits] + (["--reuse-core"] if args.reuse_core else []), base / "logs/stage.log")
    if not args.skip_build:
        run(docker + ["cargo", "test", "--offline", "--release", "--manifest-path", f"{base.as_posix()}/snapshot/Cargo.toml", "-p", "veridyct-core", "--example", "transductive_features"], base / "logs/tests.log")
        run(docker + ["cargo", "build", "--offline", "--locked", "--release", "--manifest-path", f"{base.as_posix()}/snapshot/Cargo.toml", "-p", "veridyct-core", "--example", "transductive_features"], base / "logs/build.log")
    for split in args.splits.split(","):
        feature_file = base / "features" / f"{split}-test.jsonl"
        if not (args.reuse_features and feature_file.exists()):
            run(docker + ["python3", "tools/transductive_verifier/container_run.py", "--metadata", f"{base.as_posix()}/runtime/{split}.json",
                          "/target/release/examples/transductive_features", f"{base.as_posix()}/inputs/{split}.json", "data/lexicon.json", f"{base.as_posix()}/features"], base / f"logs/features-{split}.log")
    run([sys.executable, "tools/transductive_verifier/train.py", "--directory", str(base), "--splits", args.splits], base / "logs/train.log")
    for split in args.splits.split(","):
        run(docker + ["/target/release/examples/transductive_features", "--score", f"{base.as_posix()}/inputs/{split}.json",
                      f"{base.as_posix()}/features/{split}-test.jsonl", f"{base.as_posix()}/model-manifests/{split}.json", f"{base.as_posix()}/rust-scores/{split}.jsonl"], base / f"logs/parity-{split}.log")
    run([sys.executable, "tools/transductive_verifier/train.py", "--directory", str(base), "--splits", args.splits, "--parity"], base / "logs/parity.log")
    image = subprocess.check_output(["docker", "image", "inspect", "veridyct:dev", "--format", "{{.Id}}"], text=True).strip()
    compiler = subprocess.check_output(docker + ["rustc", "--version"], text=True).strip()
    (base / "environment.json").write_text(json.dumps({"docker_image": image, "compiler": compiler, "cpus": 2, "memory": "6 GiB", "network": "none", "container_user": 0,
        "registry_volume": "veridyct-transductive-registry", "target_volume": "veridyct-transductive-target"}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integration", type=Path, default=Path("../evidence-graph-runtime"))
    parser.add_argument("--directory", type=Path, default=Path("artifacts/transductive-verifier"))
    parser.add_argument("--splits", default="random,bundle_group,template_group,forward_time,every_fifth")
    parser.add_argument("--reuse-core", action="store_true")
    parser.add_argument("--skip-stage", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--reuse-features", action="store_true", help="Use only with unchanged frozen source and stage requests")
    main(parser.parse_args())
