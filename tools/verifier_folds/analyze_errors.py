"""Post-prediction parser and routing diagnostics; never refits or selects a model."""
import argparse
import csv
import json
from pathlib import Path

from run import ROOT, SPLITS, lines, load, write


def forms_equal(left, right):
    # Set equality of typed JSON records; order/duplicates ignored, JSON numeric
    # 1 and 1.0 equal. String identifiers, units and predicates remain distinct.
    return all(f in right for f in left) and all(f in left for f in right)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/verifier-folds")
    args = parser.parse_args()
    base = args.output.resolve()
    base.relative_to(ROOT)
    summary = load(base / "results.json")  # Requires completed predictions/parity first.
    with (ROOT / "data/practice.csv").open(encoding="utf-8-sig", newline="") as f:
        annotated = {r["id"] for r in csv.DictReader(f) if r["form"].strip()}
    result = dict(form_comparison="typed JSON set equality; numeric 1 == 1.0; strings/operators/units preserved", splits={})
    for split in SPLITS:
        targets = load(base / "targets" / f"{split}.json")
        current = lines(base / "predictions" / f"{split}-currentRF.jsonl")
        boosted = lines(base / "predictions" / f"{split}-newGBT.jsonl")
        counters = dict(scored_rows=0, exact_parse_rows=0, errors_on_exact_parse=0, errors_on_inexact_parse=0,
                        empty_parse_rows=0, errors_on_empty_parse=0, graph_routed_rows=0, graph_routed_errors=0,
                        fixed_currentRF_errors=0, introduced_currentRF_errors=0)
        changed = []
        examples = []
        for gold, rf, gbt in zip(targets, current, boosted):
            prediction = gbt["prediction"]
            error = gold["label"] != prediction["label"]
            exact = None
            if gold["id"] in annotated:
                exact = forms_equal(gold["form"], prediction["facts"])
                counters["scored_rows"] += 1
                counters["exact_parse_rows"] += exact
                counters["errors_on_exact_parse"] += exact and error
                counters["errors_on_inexact_parse"] += not exact and error
            empty = not prediction["facts"]
            counters["empty_parse_rows"] += empty
            counters["errors_on_empty_parse"] += empty and error
            graph = prediction["reason"].startswith(("The compiled evidence graph", "Conflicting labelled evidence"))
            counters["graph_routed_rows"] += graph
            counters["graph_routed_errors"] += graph and error
            rf_error = rf["prediction"]["label"] != gold["label"]
            counters["fixed_currentRF_errors"] += rf_error and not error
            counters["introduced_currentRF_errors"] += not rf_error and error
            record = dict(id=gold["id"], text=gold["text"], date=gold["date"], gold_label=gold["label"],
                          currentRF=rf["prediction"]["label"], newGBT=prediction["label"],
                          gold_form=gold["form"] if gold["id"] in annotated else None,
                          inferred_form=prediction["facts"], exact_parse=exact, reason=prediction["reason"])
            if rf_error != error:
                changed.append(record)
            if error and len(examples) < 15:
                examples.append(record)
        counters["exact_parse_accuracy"] = counters["exact_parse_rows"] / counters["scored_rows"]
        counters["verdict_accuracy_given_exact_parse"] = 1 - counters["errors_on_exact_parse"] / max(1, counters["exact_parse_rows"])
        result["splits"][split] = dict(counts=counters, changed_outcomes=changed, first_errors=examples)
        print(split, json.dumps(counters))
        if summary["splits"][split]["newGBT"]["correct"] - summary["splits"][split]["currentRF"]["correct"] != counters["fixed_currentRF_errors"] - counters["introduced_currentRF_errors"]:
            raise AssertionError("Paired outcome audit disagrees with measured results")
    write(base / "error-audit.json", result)


if __name__ == "__main__":
    main()
