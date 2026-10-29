"""Stage audited, partitioned verifier research inputs; never opens reserved gold."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import unicodedata
import zipfile

ARCHIVE_SHA256 = "300623a5080ffb69eeb471e7069b88878f010059f73f002afee1995e00d99bc3"
DEVELOPMENT_RELEASES = (
    "realistic-v1/development-20000", "realistic-v1/diagnostic-6000",
    "realistic-synthetic-20000", "realistic-v1/external-development",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def csv_rows(text: str) -> list[dict]:
    result = []
    for row in csv.DictReader(io.StringIO(text)):
        row["form"] = json.loads(row.get("form") or "[]")
        result.append(row)
    return result


def request(training: list[dict], queries: list[dict], forms: dict, mode: str) -> dict:
    forbidden = {normalize(row["text"]) for row in queries}
    query_ids = {row["id"] for row in queries}
    filtered = [row for row in training if row["id"] not in query_ids and normalize(row["text"]) not in forbidden]
    inputs = []
    for row in queries:
        form = row["form"] if mode == "oracle" else forms.get(row["id"], []) if mode == "inferred" else []
        inputs.append({"id": row["id"], "text": row["text"], "date": row["date"], "label": "", "form": form})
    return {"training": filtered, "queries": inputs, "mode": mode,
            "excluded_duplicates": len(training) - len(filtered)}


def stage(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    baseline = output / "baseline" / "src"
    baseline.mkdir(parents=True, exist_ok=True)
    snapshot = {}
    for name in ("engine.rs", "forest.rs", "knowledge.rs", "model.rs", "temporal.rs"):
        source = args.integration / "crates" / "core" / "src" / name
        if source.exists():
            target = baseline / name
            if not target.exists() or args.refresh_baseline:
                shutil.copyfile(source, target)
            snapshot[name] = {"source": str(source), "sha256": digest(target)}
    write_json(output / "baseline-source.json", snapshot)
    practice = csv_rows((args.root / "data" / "practice.csv").read_text(encoding="utf-8-sig"))
    ids = set(json.loads(args.test_ids.read_text(encoding="utf-8")))
    test = [row for row in practice if row["id"] in ids]
    forbidden = {normalize(row["text"]) for row in test}
    train = [row for row in practice if row["id"] not in ids and normalize(row["text"]) not in forbidden]
    write_json(output / "practice-parser-input.json", [dict(row, label="", form=[]) for row in practice])
    forms = {}
    if args.predictions:
        predictions = json.loads(args.predictions.read_text(encoding="utf-8"))
        forms = {row["id"]: row.get("form", []) for row in predictions}
    for mode in ("template", "inferred", "oracle"):
        write_json(output / "inputs" / f"practice390-{mode}.json", request(train, test, forms, mode))
    write_json(output / "targets" / "practice390.json", test)
    inner_validation = [row for row in train if int(hashlib.sha256(normalize(row["text"]).encode()).hexdigest(), 16) % 5 == 0]
    val_ids = {row["id"] for row in inner_validation}
    inner_fit = [row for row in train if row["id"] not in val_ids]
    for name, known, query, allow_self in [("fit", inner_fit, inner_fit, True), ("validation", inner_fit, inner_validation, False), ("refit", train, train, True)]:
        for mode in ("inferred", "oracle"):
            data = request(known, query, forms, mode)
            if allow_self:
                data["training"] = known
                data["self_evidence_exclusion_required"] = True
                data["purpose"] = "supervised_feature_training; baseline memory predictions unusable"
            write_json(output / "inputs" / f"{name}-{mode}.json", data)
        write_json(output / "targets" / f"{name}.json", query)
    production = request(practice, practice, forms, "inferred")
    production["training"] = practice
    production["self_evidence_exclusion_required"] = True
    production["purpose"] = "production fit only; must never be scored as heldout practice"
    write_json(output / "inputs/production-inferred.json", production)
    # Inner cross-fitting cannot see any of the 390 outer diagnostics.
    for fold in range(5):
        select = lambda row: int(hashlib.sha256(normalize(row["text"]).encode()).hexdigest(), 16) % 5
        queries = [row for row in train if select(row) == fold]
        training = [row for row in train if select(row) != fold]
        for mode in ("template", "inferred", "oracle"):
            write_json(output / "inputs" / f"inner{fold}-{mode}.json", request(training, queries, forms, mode))
        write_json(output / "targets" / f"inner{fold}.json", queries)
    audit_path = output / "partition-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
    audit.update({"practice_sha256": digest(args.root / "data" / "practice.csv"),
             "test_ids_sha256": digest(args.test_ids), "outer_rows": len(test), "training_rows": len(train),
             "gold_target_labels_in_requests": False, "oracle_inputs_diagnostic_only": True,
             "outer_test_normalized_texts_excluded": True, "modes": ["template", "inferred", "oracle"]})
    if args.archive:
        if digest(args.archive) != ARCHIVE_SHA256:
            raise ValueError("Archive SHA256 mismatch")
        with zipfile.ZipFile(args.archive) as archive:
            # GUIDE.md is the archive's README. Reserved worlds are never opened.
            guide = archive.read("evaluation-data/GUIDE.md").decode()
            (output / "dataset-GUIDE.md").write_text(guide, encoding="utf-8")
            releases = []
            for release in DEVELOPMENT_RELEASES:
                prefix = "evaluation-data/" + release + "/"
                public = csv_rows(archive.read(prefix + "public/universe.csv").decode("utf-8-sig"))
                gold = csv_rows(archive.read(prefix + "gold/labeled.csv").decode("utf-8-sig"))
                by_id = {row["id"]: row for row in gold}
                anchors = [dict(row, form=by_id[row["id"]]["form"]) for row in public if row["label"]]
                queries = [by_id[row["id"]] for row in public if not row["label"]]
                name = release.rsplit("/", 1)[-1]
                write_json(output / "worlds" / f"{name}-public.json", [dict(row, form=[]) for row in public])
                write_json(output / "worlds" / f"{name}-oracle.json", request(anchors, queries, {}, "oracle"))
                write_json(output / "targets" / f"{name}.json", queries)
                releases.append({"name": name, "anchors": len(anchors), "targets": len(queries),
                                 "public_sha256": hashlib.sha256(archive.read(prefix + "public/universe.csv")).hexdigest()})
            audit["archive_sha256"] = ARCHIVE_SHA256
            audit["development_releases"] = releases
            audit["reserved_gold_opened"] = []
            audit["retrieval_uses_selected_gold_proof_ids"] = False
    write_json(output / "partition-audit.json", audit)
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--integration", type=Path, required=True)
    parser.add_argument("--test-ids", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--refresh-baseline", action="store_true", help="Explicitly replace the frozen integration snapshot")
    parser.add_argument("--output", type=Path, default=Path("artifacts/verifier-lab"))
    stage(parser.parse_args())
