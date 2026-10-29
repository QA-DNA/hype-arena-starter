"""Audit feature inputs, shuffle checks, and actual Rust failure on bad partitions."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import unicodedata


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args) -> None:
    base = args.directory
    root = Path.cwd().resolve()
    if base.is_absolute() or ".." in base.parts:
        raise ValueError("Audit directory must be inside the current checkout")
    source = json.loads((base / "source-sha256.json").read_text(encoding="utf-8"))
    audited_sources = {}
    for relative, info in source["files"].items():
        if relative in ("Cargo.toml", "Cargo.lock"):
            # The core-only workspace rewrites membership and prunes the lock.
            continue
        snapshot = base / "snapshot" / relative
        if sha(snapshot) != info["sha256"]:
            raise AssertionError(f"Frozen source hash mismatch: {snapshot}")
        audited_sources[relative] = sha(snapshot)
    audit = {"snapshot_source_hashes": audited_sources,
             "research_script_sha256": {p.as_posix(): sha(p) for p in sorted(Path("tools/transductive_verifier").glob("*.py"))},
             "normalization": "Unicode NFKC/casefold/whitespace", "splits": {}, "negative_guards": {}}
    for split in args.splits.split(","):
        request = json.loads((base / "inputs" / f"{split}.json").read_text(encoding="utf-8"))
        forbidden = {normalize(r["text"]) for r in request["queries"]}
        query_ids = {r["id"] for r in request["queries"]}
        if any(r["id"] in query_ids or normalize(r["text"]) in forbidden for r in request["training"]):
            raise AssertionError("Outer partition leakage")
        if any(r["label"] or r["form"] or set(r) != {"id", "text", "date", "label", "form"} for r in request["queries"] + request["corpus"]):
            raise AssertionError("Hidden label/form/metadata entered the text-only request")
        feature_audit = json.loads((base / "features" / f"{split}-audit.json").read_text(encoding="utf-8"))
        if not all(r["corpus_shuffle_feature_equality"] for r in feature_audit["partition_audits"]):
            raise AssertionError("Shuffle failed")
        count = sum(r["queries"] for r in feature_audit["partition_audits"])
        audit["splits"][split] = {"query_and_duplicate_text_exclusion": True, "query_and_corpus_gold_fields_blank": True,
                                  "corpus_shuffle_comparisons": count, "request_sha256": sha(base / "inputs" / f"{split}.json")}
        previous = base.parent / "transductive-verifier-raw-json" / "models" / f"{split}-baseline.json"
        current = base / "models" / f"{split}-baseline.json"
        if previous.exists():
            original = json.loads(previous.read_text(encoding="utf-8"))
            corrected = json.loads(current.read_text(encoding="utf-8"))
            if {k: v for k, v in original.items() if k != "provenance"} != {k: v for k, v in corrected.items() if k != "provenance"}:
                raise AssertionError("The cluster key correction changed the baseline verifier")
            audit["splits"][split]["baseline_trees_unchanged_after_typed_cluster_key_correction"] = True
    docker = ["docker", "run", "--rm", "--network", "none", "--user", "0", "--cpus", "2", "--memory", "6g",
              "-v", f"{root.as_posix()}:/work", "-v", "veridyct-transductive-target:/target", "-w", "/work", "veridyct:dev",
              "/target/release/examples/transductive_features", "--score"]
    guard = base / "negative-guards"
    guard.mkdir(parents=True, exist_ok=True)
    split = args.splits.split(",")[0]
    reference = json.loads((base / "inputs" / f"{split}.json").read_text(encoding="utf-8"))
    for name, request, expected in [
        ("wrong_training_partition", dict(reference, training=reference["training"][1:]), "checkpoint does not match"),
        ("query_gold_label", dict(reference, queries=[dict(reference["queries"][0], label="true")] + reference["queries"][1:]), "must be blank"),
        ("corpus_gold_form", dict(reference, corpus=[dict(reference["corpus"][0], form=[{"subject":"SENTINEL","attribute":"forbidden","value":{"kind":"number","value":123456789}}])] + reference["corpus"][1:]), "must be blank"),
    ]:
        path = guard / f"{name}.json"
        output = guard / f"{name}-must-not-exist.jsonl"
        if output.exists():
            raise AssertionError(f"A prior rejected request produced output: {output}")
        path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(docker + [path.as_posix(), f"{base.as_posix()}/features/{split}-test.jsonl", f"{base.as_posix()}/model-manifests/{split}.json", output.as_posix()],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        message = result.stdout.decode("utf-8", errors="replace").strip()
        if result.returncode != 2 or expected not in message or output.exists():
            raise AssertionError(f"Guard {name}: {result.returncode}: {message}")
        audit["negative_guards"][name] = {"exit_code": result.returncode, "message": message, "no_output_created": True}
    (base / "verification.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/transductive-verifier"))
    parser.add_argument("--splits", default="random,bundle_group,template_group,forward_time,every_fifth")
    run(parser.parse_args())
