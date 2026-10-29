"""Scoring-only error analysis after all predeclared models have been frozen."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from train import numeric_spelling_set

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--directory", type=Path, default=Path("artifacts/transductive-verifier"))
args = parser.parse_args()
base = args.directory
report_path = base / "report.json"
report = json.loads(report_path.read_text(encoding="utf-8"))
analysis = {"report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            "policy": "Post-prediction public practice error analysis; no selection, tuning or model updates", "splits": {}}


def example(row):
    return {k: row[k] for k in ("id", "text", "date", "gold", "gold_form", "inferred_form", "parser_exact", "parser_numeric_spelling_equivalent", "predictions", "probabilities", "cluster")}


for split, measurement in report["splits"].items():
    rows = json.loads((base / "predictions" / f"{split}.json").read_text(encoding="utf-8"))
    for row in rows:
        row["parser_numeric_spelling_equivalent"] = numeric_spelling_set(row["gold_form"]) == numeric_spelling_set(row["inferred_form"])
    improved = [r for r in rows if r["predictions"]["baseline"] != r["gold"] and r["predictions"]["temporal"] == r["gold"]]
    regressed = [r for r in rows if r["predictions"]["baseline"] == r["gold"] and r["predictions"]["temporal"] != r["gold"]]
    # Descriptive high-agreement slice only. This is never a verdict rule.
    supported = [r for r in rows if r["cluster"].get("stat.atom.mean.global.support", 0) >= 0.8
                 and math.expm1(r["cluster"].get("stat.atom.mean.global.families", 0)) >= 2 - 1e-12]
    contradicted = [r for r in rows if r["cluster"].get("stat.atom.mean.global.contradict", 0) >= 0.8
                    and math.expm1(r["cluster"].get("stat.atom.mean.global.families", 0)) >= 2 - 1e-12]
    classes = {}
    for label in ("true", "false", "unsure"):
        selected = [r for r in rows if r["gold"] == label]
        classes[label] = {"rows": len(selected), "nonempty_parse": sum(bool(r["inferred_form"]) for r in selected),
                          "literal_json_exact_parse": sum(r["parser_exact"] for r in selected), "numeric_spelling_equivalent_parse": sum(r["parser_numeric_spelling_equivalent"] for r in selected),
                          "eligible_votes": sum(r["eligible_votes"] for r in selected),
                          "temporal_improved": sum(r["gold"] == label for r in improved), "temporal_regressed": sum(r["gold"] == label for r in regressed),
                          "high_unlabelled_agreement": sum(r["gold"] == label for r in supported),
                          "high_unlabelled_contradiction": sum(r["gold"] == label for r in contradicted)}
    result = {"class_slices": classes, "improved": len(improved), "regressed": len(regressed),
              "numeric_spelling_equivalent_parse_rows": sum(r["parser_numeric_spelling_equivalent"] for r in rows),
              "improved_parser_exact": sum(r["parser_exact"] for r in improved), "regressed_parser_exact": sum(r["parser_exact"] for r in regressed),
              "improvements": [example(r) for r in improved], "regressions": [example(r) for r in regressed],
              "false_despite_high_unlabelled_agreement": [example(r) for r in supported if r["gold"] == "false"],
              "true_despite_high_unlabelled_contradiction": [example(r) for r in contradicted if r["gold"] == "true"],
              "statistical_feature_importance_top20_only": [p for p in measurement["ablations"]["temporal"]["top_features"] if p[0].startswith("stat.")]}
    analysis["splits"][split] = result
    print(json.dumps({"split": split, "extraction": measurement["extraction"], "improved": result["improved"], "regressed": result["regressed"],
                      "class_slices": classes, "first_regression": {k: regressed[0][k] for k in ("id", "text", "gold", "predictions", "parser_numeric_spelling_equivalent")} if regressed else None}, ensure_ascii=False))
analysis["mean_log_loss"] = {a: sum(r["ablations"][a]["log_loss"] for r in report["splits"].values()) / len(report["splits"]) for a in ("baseline", "global", "temporal", "statistics_only")}
(base / "error-analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"mean_log_loss": analysis["mean_log_loss"]}))
