"""Run a real compiled adapter with public-only mounts, then score development.

The predictor never imports this script or the independent private scorer.
All subprocesses use argument arrays, timeouts and resource-limited Docker.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
import zipfile

ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ("reverse_candidates", "shuffle_candidates", "replace_candidate_ids",
            "inject_untrusted_gold_fields", "reverse_document_order", "replace_input_ids")


def sha256(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def write(path, value):
    with Path(path).open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")


def jsonl(path, rows):
    with Path(path).open("x", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as source:
        # Never round a Rust exact JSON decimal through a Python binary float.
        # The public evaluator explicitly accepts exact numeric strings.
        return [json.loads(line, parse_float=str) for line in source if line.strip()]


def command(argv, *, timeout=300, log=None):
    started = perf_counter()
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout, check=False)
    record = {"argv": argv, "exit_code": result.returncode,
              "seconds_wall": perf_counter() - started,
              "stdout": result.stdout, "stderr": result.stderr}
    if log:
        write(log, record)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv[0]}\n{result.stderr}")
    return record


def snapshot(output, baseline=None):
    paths = [ROOT / "Cargo.toml", ROOT / "Cargo.lock"]
    for directory in ("crates/core", "crates/extractor", "tools/parser_v3_runtime"):
        paths.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts)
    hashes = {}
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            relative = path.relative_to(ROOT).as_posix()
            archive.write(path, relative)
            hashes[relative] = sha256(path)
        if baseline:
            archive.write(baseline, "frozen-baseline/structured.rs")
            hashes["frozen-baseline/structured.rs"] = sha256(baseline)
    return hashes


def native_copy(image, output):
    """Copy the actual frozen bundle and library, without running inference."""
    container = subprocess.check_output(["docker", "create", image], encoding="utf-8").strip()
    try:
        command(["docker", "cp", f"{container}:/opt/veridyct-extractor", str(output)], timeout=120)
    finally:
        command(["docker", "rm", container], timeout=30)


def run_adapter(public, output, target, backend, *, native=None, variants=True):
    # Runtime receives public bundle files and generated inputs only. No root
    # source, gold, scorer, practice CSV, or host directory beyond these mounts.
    base = ["docker", "run", "--rm", "--user", "root", "--network", "none",
            "--read-only", "--cpus", "2", "--memory", "6g", "--pids-limit", "128",
            "--mount", f"type=volume,source={target},target=/build,readonly",
            "--mount", f"type=bind,source={public},target=/public,readonly",
            "--mount", f"type=bind,source={output},target=/out"]
    if native:
        base += ["--mount", f"type=bind,source={native},target=/native,readonly",
                 "-e", "ORT_DYLIB_PATH=/native/lib/libonnxruntime.so.1.23.2"]
    base += ["--entrypoint", "/build/release/veridyct-parser-v3-runtime", "veridyct:dev"]
    common = ["--lexicon", "/public/lexicon.json", "--backend", backend]
    if native:
        common += ["--model", "/native/model"]
    rows = read_jsonl(public / "input.jsonl")
    paths = {}
    run_names = ("none", *VARIANTS) if variants else ("none",)
    for name in run_names:
        transformed = deepcopy(rows)
        reverse_ids = {}
        if name == "reverse_document_order":
            transformed.reverse()
        if name == "inject_untrusted_gold_fields":
            for row in transformed:
                row.update(gold={"subject": "untrusted", "truth": "true"},
                           family="untrusted", label="false", candidates=[{"subject": "untrusted"}])
        if name == "replace_input_ids":
            for index, row in enumerate(transformed):
                replacement = f"opaque-nuisance-{len(rows) - index}"
                reverse_ids[replacement] = row["id"]
                row["id"] = replacement
        jsonl(output / f"input-{name}.jsonl", transformed)
        variant = "none" if name == "replace_input_ids" else name
        command(base + common + ["--variant", variant, "--input", f"/out/input-{name}.jsonl",
                                 "--output", f"/out/raw-{name}.jsonl",
                                 "--metrics", f"/out/metrics-{name}.json"],
                timeout=300, log=output / f"run-{name}.json")
        predictions = read_jsonl(output / f"raw-{name}.jsonl")
        if reverse_ids:
            for prediction in predictions:
                prediction["id"] = reverse_ids[prediction["id"]]
        path = output / f"predictions-{name}.jsonl"
        jsonl(path, predictions)
        paths[name] = path
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--target-volume", default="veridyct-parser-v3-runtime-target")
    parser.add_argument("--backend", choices=("program", "schema", "frozen-schema"), default="program")
    parser.add_argument("--baseline-source", type=Path, help="preserved source compiled by frozen-baseline feature")
    parser.add_argument("--native-image", help="copy and use the frozen model in this image")
    parser.add_argument("--native-directory", type=Path)
    parser.add_argument("--no-variants", action="store_true")
    args = parser.parse_args()
    bundle, output = args.bundle.resolve(), args.output.resolve()
    if "artifacts" not in output.parts:
        raise ValueError("run output must be under ignored artifacts")
    sys.path.insert(0, str(ROOT))
    from tools.parser_v3_evaluation.io import verify_public
    manifest = verify_public(bundle)
    if manifest["split"] != "development":
        raise ValueError("this development runner refuses reserved-final scoring")
    output.mkdir(parents=True, exist_ok=False)
    source_hashes = snapshot(output / "source-snapshot.zip", args.baseline_source)
    command(["docker", "run", "--rm", "--network", "none", "--user", "root",
             "--mount", f"type=volume,source={args.target_volume},target=/build,readonly",
             "--mount", f"type=bind,source={output},target=/out", "--entrypoint", "cp",
             "veridyct:dev", "/build/release/veridyct-parser-v3-runtime", "/out/solver"], timeout=60)
    native = args.native_directory.resolve() if args.native_directory else None
    if args.native_image:
        if native:
            raise ValueError("choose native image or native directory")
        native = output / "native"
        native_copy(args.native_image, native)
    receipt = {"source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, encoding="utf-8").strip(),
               "git_status": subprocess.check_output(["git", "status", "--short"], cwd=ROOT, encoding="utf-8"),
               "host": platform.platform(), "source_files_sha256": source_hashes,
               "source_snapshot_sha256": sha256(output / "source-snapshot.zip"),
               "solver_sha256": sha256(output / "solver"),
               "public_bundle_sha256": manifest["public_bundle_sha256"],
               "backend": args.backend, "native": str(native) if native else None,
               "native_files_sha256": {p.relative_to(native).as_posix(): sha256(p)
                                       for p in native.rglob("*") if p.is_file()} if native else {},
               "no_runtime_llm": True, "prediction_mounts": "public files, own generated inputs, compiled binary, optional frozen model only"}
    write(output / "receipt-before-predictions.json", receipt)
    paths = run_adapter(bundle / "public", output, args.target_volume, args.backend,
                        native=native, variants=not args.no_variants)
    # The first private read occurs only after all predictions have been saved.
    from tools.parser_v3_evaluation.score import score_bundle
    report = score_bundle(bundle, paths["none"], output / "score.json",
                          variant_paths={key: path for key, path in paths.items() if key != "none"})
    predictions = {p["id"]: p for p in read_jsonl(paths["none"])}
    rows = {p["id"]: p for p in read_jsonl(bundle / "public/input.jsonl")}
    gold = {p["id"]: p for p in read_jsonl(bundle / "private/gold.jsonl")}
    jsonl(output / "all-failed-rows.jsonl", [
        {"failure": error, "input": rows[error["id"]], "prediction": predictions.get(error["id"]),
         "expected": gold[error["id"]]} for error in report["errors"]])
    summary = {key: report[key] for key in (
        "rows", "parse_exact_accuracy", "ast_scope_exact_accuracy", "status_accuracy", "ast_coverage",
        "semantic_truth_accuracy", "semantic_cases", "semantic_with_ast_accuracy", "semantic_ast_coverage",
        "assertion_micro", "subject_attribute_micro", "per_family", "metamorphic", "counts")}
    write(output / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
