"""Independent end-to-end CSV scorer; sealed scoring requires a freeze receipt.

The correctness-confidence Brier score is conditional on valid reported
confidences for definitive predictions. It is not a multiclass-probability
Brier score, and it is reported separately from classification accuracy.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .factory import (SCHEMA, assert_ignored_artifact, digest_hashes, public_hashes,
                      sha256, write_json)
from .oracle import LABELS, OracleError


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        first = handle.readline()
        delimiter = ";" if first.count(";") > first.count(",") else ","
        handle.seek(0)
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames or not {"id", "label"}.issubset(reader.fieldnames):
            raise OracleError("CSV must have id and label columns")
        return list(reader)


def metrics(expected: dict[str, str], predictions: list[dict]) -> dict:
    if not expected or any(label not in LABELS for label in expected.values()):
        raise OracleError("metrics require nonempty valid target gold")
    first: dict[str, dict] = {}
    counts: Counter = Counter()
    for prediction in predictions:
        if prediction.get("type", "").strip():
            counts["generated_claims_ignored"] += 1
            continue
        row_id = prediction.get("id", "").strip()
        if row_id not in expected:
            counts["non_target_rows_ignored"] += 1
            continue
        if row_id in first:
            counts["duplicate_target_rows_ignored"] += 1
            continue
        first[row_id] = prediction
    confusion = {truth: {predicted: 0 for predicted in LABELS} for truth in LABELS}
    calibration, class_brier, bins = [], [], defaultdict(list)
    for row_id, truth in expected.items():
        record = first.get(row_id)
        if record is None:
            counts["missing_targets"] += 1
            record = {}
        predicted = (record.get("label") or "").strip().casefold()
        if predicted not in LABELS:
            if predicted:
                counts["invalid_labels"] += 1
            else:
                counts["empty_labels"] += 1
            predicted = "unsure"
        confusion[truth][predicted] += 1
        confidence = (record.get("confidence") or "").strip()
        if predicted == "unsure":
            if confidence:
                counts["unsure_confidence_should_be_empty"] += 1
            continue
        counts["covered"] += 1
        correct = int(truth == predicted)
        counts["covered_correct"] += correct
        if not confidence:
            counts["missing_definitive_confidence"] += 1
            continue
        try:
            value = float(confidence.replace(",", "."))
        except ValueError:
            value = float("nan")
        if not math.isfinite(value) or not .5 <= value <= 1:
            counts["invalid_definitive_confidence"] += 1
            continue
        calibration.append((value - correct) ** 2)
        bins[min(9, int(value * 10))].append((value, correct))
        if truth != "unsure":
            p_true = value if predicted == "true" else 1 - value
            class_brier.append((p_true - int(truth == "true")) ** 2)
    total = len(expected)
    per_label, f1s = {}, []
    for label in LABELS:
        tp = confusion[label][label]
        support = sum(confusion[label].values())
        predicted = sum(confusion[other][label] for other in LABELS)
        precision = tp / predicted if predicted else 0.
        recall = tp / support if support else 0.
        f1 = 2 * tp / (support + predicted) if support + predicted else 0.
        per_label[label] = {"support": support, "predicted": predicted,
                            "precision": precision, "recall": recall, "f1": f1}
        f1s.append(f1)
    calibration_bins = [{"lower": index / 10, "upper": (index + 1) / 10,
                         "n": len(entries), "mean_confidence": sum(x[0] for x in entries) / len(entries),
                         "accuracy": sum(x[1] for x in entries) / len(entries)}
                        for index, entries in sorted(bins.items())]
    ece = (sum(abs(item["mean_confidence"] - item["accuracy"]) * item["n"] for item in calibration_bins)
           / len(calibration) if calibration else None)
    return {
        "targets": total,
        "target_accuracy": sum(confusion[label][label] for label in LABELS) / total,
        "macro_f1": sum(f1s) / len(LABELS),
        "confusion": {"row_order": list(LABELS), "column_order": list(LABELS),
                      "rows_are": "gold", "columns_are": "prediction", "counts": confusion},
        "per_label": per_label,
        "coverage": counts["covered"] / total,
        "covered_accuracy": counts["covered_correct"] / counts["covered"] if counts["covered"] else None,
        "confidence_brier_correctness": {
            "score": sum(calibration) / len(calibration) if calibration else None,
            "n": len(calibration), "definition": "mean((reported_confidence - is_selected_label_correct)^2)",
            "population": "definitive predictions with valid confidence, including wrong predictions on unsure gold",
            "missing": counts["missing_definitive_confidence"],
            "invalid": counts["invalid_definitive_confidence"],
        },
        "binary_label_brier_on_answered_known_gold": {
            "score": sum(class_brier) / len(class_brier) if class_brier else None,
            "n": len(class_brier),
            "definition": "p(true)=confidence for true prediction, 1-confidence for false prediction; gold true/false only",
        },
        "confidence_ece": ece, "confidence_bins": calibration_bins,
        "diagnostics": dict(counts),
        "majority_label_baseline_accuracy": max(item["support"] for item in per_label.values()) / total,
    }


def verify_public(bundle: Path) -> dict:
    if (bundle.parent / "RETIRED.json").exists() or (bundle / "RETIRED.json").exists():
        raise OracleError("evaluation bundle retired after audit; use the replacement independent-evaluation-v3 world")
    manifest = json.loads((bundle / "public" / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise OracleError("unsupported public bundle schema")
    actual = public_hashes(bundle / "public")
    if actual != manifest["hashes"] or digest_hashes(actual) != manifest["public_sha256"]:
        raise OracleError("public input hashes do not match the frozen manifest")
    return manifest


def validate_freeze(receipt_path: Path | None, manifest: dict, predictions: Path) -> dict:
    if receipt_path is None:
        raise OracleError("sealed evaluation requires the coordinator's explicit source/model freeze receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    required = ("freeze_id", "confirmed_at_utc", "source_commit", "source_tree_sha256")
    if (receipt.get("confirmed_by") != "coordinator" or
            receipt.get("training_and_selection_finished") is not True or
            any(not receipt.get(key) for key in required)):
        raise OracleError("freeze must explicitly attest coordinator confirmation and completed model selection")
    if not re.fullmatch(r"[0-9a-f]{64}", receipt["source_tree_sha256"]):
        raise OracleError("freeze must identify the complete source tree by SHA-256")
    try:
        instant = datetime.fromisoformat(receipt["confirmed_at_utc"].replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("timezone missing")
    except ValueError as exc:
        raise OracleError("freeze confirmation requires an ISO UTC/offset timestamp") from exc
    if instant.timestamp() > min(datetime.now(timezone.utc).timestamp(), predictions.stat().st_mtime + 2):
        raise OracleError("prediction file must be produced after the confirmed freeze")
    if manifest["public_sha256"] not in receipt.get("evaluation_public_sha256", []):
        raise OracleError("freeze receipt does not authorize this exact public world")
    artifacts = receipt.get("solver_artifacts", [])
    if not artifacts or not any(item.get("role") == "solver" for item in artifacts):
        raise OracleError("freeze must identify the solver artifact and any separately loaded model files")
    for artifact in artifacts:
        path = Path(artifact["path"])
        if not path.is_file() or sha256(path) != artifact["sha256"]:
            raise OracleError("a frozen solver/model artifact is missing or changed")
    return receipt


def evaluate_bundle(bundle: Path, predictions: Path, report: Path,
                    freeze_receipt: Path | None = None) -> dict:
    bundle, predictions, report = bundle.resolve(), predictions.resolve(), report.resolve()
    assert_ignored_artifact(report)
    manifest = verify_public(bundle)
    metadata = json.loads((bundle / "private" / "metadata.json").read_text(encoding="utf-8"))
    # Read only metadata before the gate. Never open sealed gold on a failed gate.
    if (metadata["sealed"] != manifest["sealed"] or
            metadata["public_sha256"] != manifest["public_sha256"]):
        raise OracleError("private/public metadata mismatch")
    receipt = validate_freeze(freeze_receipt, manifest, predictions) if manifest["sealed"] else None
    evaluation_id = None
    if receipt:
        evaluation_id = receipt["freeze_id"]
        marker = bundle / "private" / "one-shot-evaluation.json"
        # Exclusive create precedes gold access. A crash consumes the attempt and
        # leaves an auditable marker; there is intentionally no force/reset flag.
        try:
            with marker.open("x", encoding="utf-8") as handle:
                json.dump({"status": "started", "freeze_id": evaluation_id,
                           "freeze_receipt_sha256": sha256(freeze_receipt),
                           "predictions_sha256": sha256(predictions),
                           "public_sha256": manifest["public_sha256"]}, handle, indent=2)
        except FileExistsError as exc:
            raise OracleError("sealed world already has a scoring attempt; no repeat/tuning evaluation is allowed") from exc
    gold_path = bundle / "private" / "gold.jsonl"
    if sha256(gold_path) != metadata["gold_sha256"]:
        raise OracleError("gold integrity hash mismatch")
    gold_rows = [json.loads(line) for line in gold_path.read_text(encoding="utf-8").splitlines() if line]
    expected = {row["id"]: row["label"] for row in gold_rows}
    public_rows = read_csv(bundle / "public" / "universe.csv")
    target_ids = {row["id"] for row in public_rows if not row["label"]}
    if len(expected) != len(gold_rows) or set(expected) != target_ids or len(expected) != manifest["targets"]:
        raise OracleError("gold and public target identities disagree")
    output_rows = read_csv(predictions)
    result = metrics(expected, output_rows)
    # Strata are useful for development and aggregate, once-only frozen analysis.
    strata = defaultdict(dict)
    for row in gold_rows:
        memberships = [("surface_style", str(row["style"])), ("context", row["context"]),
                       ("arity", str(row["arity"])), ("distractor", str(row["distractor"]))]
        memberships += [("kind", kind) for kind in {a["value"]["kind"] for a in row["assertions"]}]
        memberships += [("operator", op) for op in {a["op"] for a in row["assertions"]}]
        for category, member in memberships:
            strata[(category, member)][row["id"]] = row["label"]
    by_stratum = defaultdict(dict)
    for (category, member), subset in strata.items():
        selected = [row for row in output_rows if row.get("id") in subset]
        scores = metrics(subset, selected)
        by_stratum[category][member] = {key: scores[key] for key in
                                      ("targets", "target_accuracy", "macro_f1", "coverage")}
    result.update(schema=SCHEMA, sealed=manifest["sealed"], freeze_id=evaluation_id,
                  public_sha256=manifest["public_sha256"], predictions_sha256=sha256(predictions),
                  confidence_is_separate_from_accuracy=True, by_stratum=dict(by_stratum),
                  scope="synthetic declared language families; input-target classification only; not official Hooly truth or generated-claim judging")
    report.parent.mkdir(parents=True, exist_ok=True)
    write_json(report, result)
    if receipt:
        marker_value = json.loads(marker.read_text(encoding="utf-8"))
        write_json(marker, {**marker_value, "status": "completed", "report": str(report),
                            "report_sha256": sha256(report)})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--freeze-receipt", type=Path)
    args = parser.parse_args()
    try:
        result = evaluate_bundle(args.bundle, args.predictions, args.report, args.freeze_receipt)
    except (OracleError, OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"evaluation refused: {exc}\n")
    print(json.dumps({key: result[key] for key in
                      ("targets", "target_accuracy", "macro_f1", "coverage", "covered_accuracy",
                       "confidence_brier_correctness", "sealed", "freeze_id")}, sort_keys=True))


if __name__ == "__main__":
    main()
