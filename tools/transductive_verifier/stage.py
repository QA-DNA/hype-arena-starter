"""Freeze the current core and prepare label-free transductive research requests.

Only public practice.csv, lexicon.json and split_assignments.csv are opened.
No archive, reserved gold, pretrained parser or production verifier is read.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import unicodedata

SPLITS = ("random", "bundle_group", "template_group", "forward_time", "every_fifth")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def hidden(row: dict) -> dict:
    return {"id": row["id"], "text": row["text"], "date": row["date"], "label": "", "form": []}


def clean(training: list[dict], queries: list[dict]) -> list[dict]:
    ids = {r["id"] for r in queries}
    texts = {normalize(r["text"]) for r in queries}
    return [r for r in training if r["id"] not in ids and normalize(r["text"]) not in texts]


def snapshot(args) -> None:
    target = args.output / "snapshot"
    target.mkdir(parents=True, exist_ok=True)
    source_files = [args.integration / p for p in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "crates/core/Cargo.toml")]
    source_files += sorted((args.integration / "crates/core/src").glob("*.rs"))
    hashes = {}
    for source in source_files:
        relative = source.relative_to(args.integration)
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not args.reuse_core:
            before = sha(source)
            shutil.copyfile(source, dest)
            if sha(source) != before or sha(dest) != before:
                raise RuntimeError(f"Source changed during snapshot: {source}")
        elif not dest.exists():
            raise ValueError(f"Frozen snapshot is incomplete: {dest}")
        hashes[relative.as_posix()] = {"source": str(source), "sha256": sha(dest)}
    manifest = target / "Cargo.toml"
    manifest.write_text(re.sub(r'(?m)^members = \[.*\]$', 'members = ["crates/core"]', manifest.read_text(encoding="utf-8")), encoding="utf-8")
    for relative in ("crates/core/examples/transductive_features.rs", "tools/transductive_verifier/cluster.rs"):
        source = args.root / relative
        dest = target / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        hashes[relative] = {"source": str(source), "sha256": sha(dest)}
    # Core unit tests embed these public files at compile time.
    for name in ("practice.csv", "lexicon.json"):
        dest = target / "data" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.root / "data" / name, dest)
    manifest_path = args.output / "source-sha256.json"
    if not args.reuse_core:
        write(manifest_path, {"integration_commit": subprocess.check_output(["git", "-C", str(args.integration), "rev-parse", "HEAD"], text=True).strip(),
                              "files": hashes, "adaptation": "core-only workspace members; lockfile may be pruned by the first build"})
    else:
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        prior["files"].update({k: v for k, v in hashes.items() if k.startswith(("tools/", "crates/core/examples/"))})
        write(manifest_path, prior)


def run(args) -> None:
    args.root = args.root.resolve()
    args.integration = args.integration.resolve()
    args.output = args.output.resolve()
    snapshot(args)
    practice_path = args.root / "data/practice.csv"
    practice = list(csv.DictReader(practice_path.open(encoding="utf-8-sig", newline="")))
    for row in practice:
        row["form"] = json.loads(row.get("form") or "[]")
        if row["label"] not in ("true", "false", "unsure"):
            raise ValueError(f"Missing public practice label: {row['id']}")
    assignments_path = args.root / "analysis/practice/outputs/split_assignments.csv"
    assignments = list(csv.DictReader(assignments_path.open(encoding="utf-8-sig", newline="")))
    ids = {r["id"] for r in practice}
    if len(ids) != len(practice):
        raise ValueError("Duplicate practice IDs")
    audit = {"policy": "All public practice texts are an unlabelled transductive view; labels/forms remain only in cleaned training and a scoring sidecar.",
             "parser": "fresh pure-Rust Engine per outer split and per crossfit fold; no frozen neural model",
             "training_features": "five text-hash folds; each query, normalized duplicates and its fold excluded from extractor and evidence",
             "selection": "fixed GBT n_estimators=120, learning_rate=0.045, max_depth=2, min_samples_leaf=20, random_state=417",
             "input_sha256": {str(p): sha(p) for p in (practice_path, assignments_path, args.root / "data/lexicon.json")}, "splits": {}}
    for split in args.splits.split(","):
        if split not in SPLITS:
            raise ValueError(split)
        selected = [r for r in assignments if r["split"] == split]
        parts = {r["id"]: r["partition"] for r in selected}
        if len(parts) != len(selected) or set(parts) != ids or set(parts.values()) != {"train", "test"}:
            raise ValueError(f"Invalid assignments: {split}")
        test = [r for r in practice if parts[r["id"]] == "test"]
        raw_train = [r for r in practice if parts[r["id"]] == "train"]
        train = clean(raw_train, test)
        write(args.output / "inputs" / f"{split}.json", {"training": train, "queries": [hidden(r) for r in test], "corpus": [hidden(r) for r in practice], "split": split, "crossfit_folds": args.folds})
        # This sidecar is never passed to the Rust feature process.
        write(args.output / "targets" / f"{split}.json", {"training": [{k: r[k] for k in ("id", "text", "label")} for r in train],
                                                            "test": [{k: r[k] for k in ("id", "text", "label", "form")} for r in test]})
        audit["splits"][split] = {"training": len(train), "test": len(test), "removed_duplicates": len(raw_train) - len(train), "request_sha256": sha(args.output / "inputs" / f"{split}.json")}
    write(args.output / "stage-audit.json", audit)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--integration", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/transductive-verifier"))
    parser.add_argument("--splits", default=",".join(SPLITS))
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--reuse-core", action="store_true")
    run(parser.parse_args())
