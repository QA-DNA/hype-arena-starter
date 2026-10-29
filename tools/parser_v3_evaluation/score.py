"""Score AST, assertion sets, diagnostics, semantic truth and metamorphic runs.

Final scoring requires a real coordinator freeze and creates an exclusive marker
before opening final gold. There is no overwrite/reset/force option.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import re

from .io import digest, load_json, load_jsonl, require_artifacts, verify_public, write_json
from .oracle import canonical_ast, canonical_fact, evaluate, label, validate_ast

STATUSES = {"parsed", "partial", "unresolved", "ambiguous"}
NOTE_ALIASES = {
    "subject": ("subject", "antecedent", "pronoun", "context", "document"),
    "ambigu": ("ambigu", "antecedent", "unresolved_subject", "missing_subject"),
    "unknown": ("unknown", "not_recorded", "not recorded", "missing_value", "unrecorded", "explicit_unknown"),
    "approx": ("approx", "nonexact", "non_exact", "unsupported_value", "unsupported value"),
}


def predictions_by_id(path, rows):
    result = {}
    public_ids = {row["id"] for row in rows}
    for prediction in load_jsonl(path):
        identity = prediction.get("id")
        if identity not in public_ids: raise ValueError("prediction has unknown ID")
        if identity in result: raise ValueError("duplicate prediction ID")
        result[identity] = prediction
    return result


def fact_set(facts):
    if not isinstance(facts, list): raise ValueError("assertions must be an array")
    return {canonical_fact(fact) for fact in facts}


def ownership(facts):
    return {(fact["subject"], fact["attribute"]) for fact in facts}


def fraction(numerator, denominator):
    return numerator / denominator if denominator else None


def prf(tp, fp, fn):
    precision, recall = fraction(tp, tp + fp), fraction(tp, tp + fn)
    f1 = fraction(2 * tp, 2 * tp + fp + fn)
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn, "precision": precision, "recall": recall, "f1": f1}


def validate_prediction(prediction, lexicon):
    if prediction.get("status") not in STATUSES: raise ValueError("invalid/missing prediction status")
    if "ast" not in prediction: raise ValueError("prediction must provide ast, including null for abstention")
    validate_ast(prediction["ast"], lexicon)
    canonical_ast(prediction["ast"])
    fact_set(prediction.get("assertions"))
    if not isinstance(prediction.get("notes"), list) or not all(isinstance(note, str) for note in prediction["notes"]):
        raise ValueError("notes must be an array of strings")


def score_cases(rows, gold, predictions, lexicon, variants=None):
    per_family = defaultdict(Counter)
    totals = Counter()
    errors = []
    semantic_confusion = defaultdict(Counter)
    status_confusion = defaultdict(Counter)
    truth_pairs = defaultdict(list)
    for expected in gold:
        identity, family = expected["id"], expected["family"]
        prediction = predictions.get(identity)
        error = None
        if prediction is None:
            totals["missing_predictions"] += 1
        else:
            try:
                validate_prediction(prediction, lexicon)
            except (KeyError, TypeError, ValueError) as exception:
                error = str(exception)
                totals["invalid_predictions"] += 1
                prediction = None
        predicted_ast = prediction["ast"] if prediction else None
        predicted_facts = prediction["assertions"] if prediction else []
        expected_set = fact_set(expected["assertions"])
        predicted_set = fact_set(predicted_facts)
        expected_owners, predicted_owners = ownership(expected["assertions"]), ownership(predicted_facts)
        status_ok = prediction is not None and prediction["status"] in expected["acceptable_statuses"]
        ast_ok = prediction is not None and canonical_ast(predicted_ast) == canonical_ast(expected["ast"])
        facts_ok = prediction is not None and predicted_set == expected_set
        note_text = " ".join(prediction["notes"]).casefold() if prediction else ""
        notes_ok = all(any(alias in note_text for alias in NOTE_ALIASES.get(category, (category,))) for category in expected["note_categories"])
        checks = {"status_exact": status_ok, "ast_exact": ast_ok, "assertions_exact": facts_ok,
                  "parse_exact": status_ok and ast_ok, "full_contract_exact": status_ok and ast_ok and facts_ok and notes_ok,
                  "notes_exact": notes_ok}
        totals["rows"] += 1
        per_family[family]["rows"] += 1
        for check, passed in checks.items():
            totals[check] += passed
            per_family[family][check] += passed
        totals["assertion_tp"] += len(predicted_set & expected_set)
        totals["assertion_fp"] += len(predicted_set - expected_set)
        totals["assertion_fn"] += len(expected_set - predicted_set)
        totals["owner_tp"] += len(predicted_owners & expected_owners)
        totals["owner_fp"] += len(predicted_owners - expected_owners)
        totals["owner_fn"] += len(expected_owners - predicted_owners)
        totals["ast_returned"] += predicted_ast is not None
        if expected["note_categories"]:
            totals["diagnostic_cases"] += 1
            totals["diagnostic_correct"] += bool(prediction and note_text and notes_ok)
        status_confusion["|".join(expected["acceptable_statuses"])][prediction["status"] if prediction else "missing_or_invalid"] += 1
        semantic_ok = None
        if expected["semantic_truth"] is not None:
            totals["semantic_cases"] += 1
            observed = label(evaluate(predicted_ast, expected["world"])) if predicted_ast is not None else "unsure"
            semantic_ok = observed == expected["semantic_truth"]
            totals["semantic_correct"] += semantic_ok
            totals["semantic_with_ast"] += predicted_ast is not None
            totals["semantic_with_ast_correct"] += semantic_ok and predicted_ast is not None
            semantic_confusion[expected["semantic_truth"]][observed] += 1
        if not all(checks.values()):
            errors.append({"id": identity, "family": family, "failed": [name for name, passed in checks.items() if not passed],
                           "validation_error": error, "semantic_correct": semantic_ok})
        if expected["metamorphic_group"]:
            truth_pairs[expected["metamorphic_group"]].append((identity, prediction))
    morph_counts = Counter()
    for pair in truth_pairs.values():
        morph_counts["truth_only_pairs"] += 1
        a, b = [item[1] for item in pair]
        if a is not None and b is not None:
            morph_counts["truth_only_status_and_ast_stable"] += a["status"] == b["status"] and canonical_ast(a["ast"]) == canonical_ast(b["ast"])
            morph_counts["truth_only_ownership_stable"] += ownership(a["assertions"]) == ownership(b["assertions"])
    variant_scores = {}
    for name, mapping in (variants or {}).items():
        valid, same_ast, same_owners = 0, 0, 0
        for identity, baseline in predictions.items():
            other = mapping.get(identity)
            if other is None: continue
            try:
                validate_prediction(baseline, lexicon)
                validate_prediction(other, lexicon)
            except (KeyError, TypeError, ValueError): continue
            valid += 1
            same_ast += baseline["status"] == other["status"] and canonical_ast(baseline["ast"]) == canonical_ast(other["ast"])
            same_owners += ownership(baseline["assertions"]) == ownership(other["assertions"])
        variant_scores[name] = {"comparable_rows": valid, "all_input_rows": len(rows), "status_and_ast_stable": same_ast,
                                "ownership_stable": same_owners, "missing_or_invalid_comparisons": len(rows) - valid}
    count = totals["rows"]
    return {
        "format": "parser-v3-score-1", "rows": count,
        "parse_exact_accuracy": fraction(totals["parse_exact"], count),
        "ast_scope_exact_accuracy": fraction(totals["ast_exact"], count),
        "assertion_set_exact_accuracy": fraction(totals["assertions_exact"], count),
        "status_accuracy": fraction(totals["status_exact"], count),
        "full_contract_accuracy": fraction(totals["full_contract_exact"], count),
        "diagnostic_accuracy": fraction(totals["diagnostic_correct"], totals["diagnostic_cases"]),
        "ast_coverage": fraction(totals["ast_returned"], count),
        "assertion_micro": prf(totals["assertion_tp"], totals["assertion_fp"], totals["assertion_fn"]),
        "subject_attribute_micro": prf(totals["owner_tp"], totals["owner_fp"], totals["owner_fn"]),
        "semantic_truth_accuracy": fraction(totals["semantic_correct"], totals["semantic_cases"]),
        "semantic_with_ast_accuracy": fraction(totals["semantic_with_ast_correct"], totals["semantic_with_ast"]),
        "semantic_cases": totals["semantic_cases"], "semantic_ast_coverage": fraction(totals["semantic_with_ast"], totals["semantic_cases"]),
        "counts": dict(totals), "per_family": {name: dict(values) for name, values in sorted(per_family.items())},
        "status_confusion": {name: dict(values) for name, values in status_confusion.items()},
        "semantic_confusion": {name: dict(values) for name, values in semantic_confusion.items()},
        "metamorphic": {**dict(morph_counts), "adapter_variants": variant_scores}, "errors": errors,
        "limitations": "Controlled synthetic language; not competition accuracy. Semantic unsure can be guessed by abstention, so AST coverage and semantic_with_ast_accuracy are reported separately. Candidate transform execution is the adapter's responsibility; scorer compares supplied runs only.",
    }


def validate_freeze(bundle, receipt_path, prediction_paths):
    if receipt_path is None: raise ValueError("final scoring requires a coordinator freeze receipt")
    receipt = load_json(receipt_path)
    if receipt.get("confirmed_by") != "coordinator" or receipt.get("training_and_selection_finished") is not True:
        raise ValueError("coordinator freeze attestation missing")
    if not receipt.get("freeze_id") or not receipt.get("source_commit"):
        raise ValueError("freeze ID/source commit missing")
    tree_hash = receipt.get("source_tree_sha256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", tree_hash): raise ValueError("source tree hash missing")
    confirmed = datetime.fromisoformat(receipt["confirmed_at_utc"].replace("Z", "+00:00"))
    if confirmed.tzinfo is None: raise ValueError("freeze timestamp needs UTC/offset")
    if any(confirmed.timestamp() > Path(path).stat().st_mtime for path in prediction_paths):
        raise ValueError("predictions predate freeze confirmation")
    manifest = verify_public(bundle)
    if manifest["public_bundle_sha256"] not in receipt.get("evaluation_public_sha256", []):
        raise ValueError("freeze receipt does not include this public bundle")
    artifacts = receipt.get("solver_artifacts", [])
    if not any(item.get("role") == "solver" for item in artifacts): raise ValueError("frozen solver artifact missing")
    for item in artifacts:
        if digest(item["path"]) != item["sha256"]: raise ValueError("frozen artifact hash mismatch")
    snapshots = [item for item in artifacts if item.get("role") == "source_snapshot"]
    if not snapshots or not any(item["sha256"] == tree_hash for item in snapshots):
        raise ValueError("source_tree_sha256 must identify a listed source_snapshot artifact")
    return receipt


def score_bundle(bundle, prediction_path, report_path, freeze_receipt=None, variant_paths=None):
    bundle, prediction_path = Path(bundle), Path(prediction_path)
    report_path = require_artifacts(report_path)
    if report_path.exists(): raise ValueError("refusing to overwrite score report")
    manifest = verify_public(bundle)
    rows = load_jsonl(bundle / "public/input.jsonl")
    predictions = predictions_by_id(prediction_path, rows)
    variants = {name: predictions_by_id(path, rows) for name, path in (variant_paths or {}).items()}
    if manifest["split"] == "final":
        receipt = validate_freeze(bundle, freeze_receipt, [prediction_path, *(variant_paths or {}).values()])
        marker = bundle / "private/one-shot-evaluation.json"
        with marker.open("x", encoding="utf-8") as output:
            import json
            json.dump({"freeze_id": receipt["freeze_id"], "freeze_receipt_sha256": digest(freeze_receipt),
                       "predictions_sha256": digest(prediction_path), "variant_sha256": {name: digest(path) for name, path in (variant_paths or {}).items()},
                       "started_utc": datetime.now(timezone.utc).isoformat()}, output, sort_keys=True, indent=2)
    if digest(bundle / "private/gold.jsonl") != manifest["gold_sha256"]: raise ValueError("gold hash mismatch")
    gold = load_jsonl(bundle / "private/gold.jsonl")
    report = score_cases(rows, gold, predictions, load_json(bundle / "public/lexicon.json"), variants)
    report.update(public_bundle_sha256=manifest["public_bundle_sha256"], predictions_sha256=digest(prediction_path),
                  split=manifest["split"], freeze_receipt_sha256=digest(freeze_receipt) if freeze_receipt else None)
    write_json(report_path, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--freeze-receipt", type=Path)
    parser.add_argument("--variant-predictions", action="append", default=[], metavar="NAME=JSONL")
    args = parser.parse_args()
    variants = {}
    for argument in args.variant_predictions:
        name, path = argument.split("=", 1)
        if name in variants: raise ValueError("duplicate variant name")
        variants[name] = Path(path)
    report = score_bundle(args.bundle, args.predictions, args.report, args.freeze_receipt, variants)
    print(f"{report['rows']} cases; parse exact {report['parse_exact_accuracy']:.4%}; assertions exact {report['assertion_set_exact_accuracy']:.4%}")


if __name__ == "__main__": main()
