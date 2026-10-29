"""Require structural encoding and row-by-row decoded parity; never reads gold."""
import argparse
import collections
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.dir
    read = lambda name: json.loads((root / name).read_text(encoding="utf-8"))
    requests = read("requests.json")
    pe, ne = read("python-encoded.json"), read("native-encoded.json")
    pp, np = read("python-predictions.json"), read("native-predictions.json")
    if any(len(a) != len(requests) for a in (pe, ne, pp, np)):
        raise ValueError("Output row count differs")
    groups, mismatches = collections.defaultdict(collections.Counter), []
    max_score_error = 0.0
    frozen = {r["id"]: r["prediction"] for r in read("frozen-predictions.json")}
    for i, (req, p_enc, n_enc, p_pred, n_pred) in enumerate(zip(requests, pe, ne, pp, np)):
        c = groups[req["group"]]
        c["rows"] += 1
        same_enc = p_enc == n_enc
        same_form = p_pred["form"] == n_pred["form"]
        def without_scores(a):
            return [{k: v for k, v in x.items() if k != "model_score"} for x in a]
        same_assertions = without_scores(p_pred["assertions"]) == without_scores(n_pred["assertions"])
        c["encoding_exact"] += same_enc
        c["form_exact"] += same_form
        c["assertions_and_spans_exact"] += same_assertions
        if same_assertions:
            for p, n in zip(p_pred["assertions"], n_pred["assertions"]):
                max_score_error = max(max_score_error, abs(p["model_score"] - n["model_score"]))
        if req["group"].startswith("frozen_"):
            expected = without_scores(frozen[req["id"]])
            c["frozen_prediction_exact"] += expected == without_scores(n_pred["assertions"])
        if not (same_enc and same_form and same_assertions) and len(mismatches) < 20:
            mismatches.append(dict(index=i, id=req["id"], text=req["text"], encoding_exact=same_enc,
                                   python_encoding=p_enc if not same_enc else None,
                                   native_encoding=n_enc if not same_enc else None,
                                   python_prediction=p_pred if not same_assertions else None,
                                   native_prediction=n_pred if not same_assertions else None))
    passed = all(c["encoding_exact"] == c["form_exact"] == c["assertions_and_spans_exact"] == c["rows"] and
                 c.get("frozen_prediction_exact", c["rows"]) == c["rows"] for c in groups.values())
    report = dict(passed=passed, groups=dict(groups), max_abs_score_error=max_score_error,
                  scope="Port parity only; no independent accuracy claim; no sealed gold read", mismatches=mismatches,
                  sources=read("sources.json"))
    (root / "parity-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "mismatches"}, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
