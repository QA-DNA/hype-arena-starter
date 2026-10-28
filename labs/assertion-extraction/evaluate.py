#!/usr/bin/env python3
"""Development diagnostic only: compare canonical pair multisets, never truth/value accuracy.

Python standard library. Practice forms enter only this evaluator, not the Rust parser.
Codex-authored evaluation code; no generated training evidence.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--practice", type=Path, required=True)
    parser.add_argument("--assertions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    practice = read_csv(args.practice)
    assertions = read_csv(args.assertions)
    grouped = collections.defaultdict(list)
    for assertion in assertions:
        grouped[assertion["id"]].append(assertion)
    ids = [r["id"] for r in practice]
    if len(set(ids)) != len(ids) or set(grouped) != set(ids):
        raise ValueError("Practice and output must cover exactly the same unique row IDs")
    totals = collections.Counter()
    statuses = collections.Counter()
    reasons = collections.Counter()
    errors = []
    slices = collections.defaultdict(collections.Counter)
    for row in practice:
        gold = collections.Counter((a["subject"], a["attribute"]) for a in json.loads(row["form"]))
        predicted = collections.Counter((a["subject"], a["attribute"]) for a in grouped[row["id"]] if a["status"] == "paired")
        correct = sum((gold & predicted).values())
        counts = dict(matched=correct, predicted=sum(predicted.values()), reference=sum(gold.values()), rows=1, exact_pair_rows=int(gold == predicted))
        totals.update(counts)
        status = grouped[row["id"]][0]["row_status"]
        statuses[status] += 1
        totals["split_but_pair_mismatch"] += int(status == "split" and gold != predicted)
        kinds = ["single_assertion" if sum(gold.values()) == 1 else "multiple_assertions", "single_subject" if len({s for s, _ in gold}) == 1 else "multiple_subjects"]
        for kind in kinds:
            slices[kind].update(counts)
        for a in grouped[row["id"]]:
            if a["reason"]:
                reasons[a["reason"]] += 1
        if gold != predicted:
            errors.append({"id": row["id"], "row_status": status, "missing_pairs": list((gold - predicted).elements()), "extra_pairs": list((predicted - gold).elements())})

    def metrics(counts):
        p = counts["matched"] / counts["predicted"] if counts["predicted"] else 0
        r = counts["matched"] / counts["reference"] if counts["reference"] else 0
        return dict(counts, pair_precision=p, pair_recall=r, pair_f1=2*p*r/(p+r) if p+r else 0, exact_pair_row_rate=counts["exact_pair_rows"] / counts["rows"])

    report = {
        "scope": "Development diagnostic on full practice; NOT held-out generalization or assertion-text/value/truth accuracy. Rules include development-reviewed examples. Extra pairs may include annotation-scope differences.",
        "practice_sha256": hashlib.sha256(args.practice.read_bytes()).hexdigest(),
        "assertions_sha256": hashlib.sha256(args.assertions.read_bytes()).hexdigest(),
        "metrics": metrics(totals), "row_statuses": dict(statuses),
        "unresolved_reasons": dict(reasons), "slices": {k: metrics(v) for k, v in slices.items()},
        "pair_mismatches": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"metrics": report["metrics"], "row_statuses": report["row_statuses"]}, indent=2))


if __name__ == "__main__":
    main()
