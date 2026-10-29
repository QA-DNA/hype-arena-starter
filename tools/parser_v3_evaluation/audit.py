"""Audit bundle integrity; final CLI audits are strictly public-only."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from .io import digest, load_json, load_jsonl, require_artifacts, verify_public, write_json
from .oracle import assertions, canonical_ast, canonical_fact, channel, evaluate, label, typed, validate_ast


def audit_cases(rows, gold, lexicon):
    if len(rows) != len(gold): raise ValueError("input/gold length mismatch")
    public_by_id = {row["id"]: row for row in rows}
    if len(public_by_id) != len(rows): raise ValueError("duplicate public ID")
    if set(public_by_id) != {item["id"] for item in gold}: raise ValueError("gold IDs mismatch")
    groups = defaultdict(list)
    for row in rows:
        if set(row) != {"id", "document_id", "text", "context"}: raise ValueError("unexpected public parser feature")
        if not row["text"] or not isinstance(row["text"], str): raise ValueError("invalid public text")
        context = row["context"]
        if set(context) != {"enabled", "document_id", "prior_texts"}: raise ValueError("unexpected context feature")
        if type(context["enabled"]) is not bool or not all(isinstance(x, str) for x in context["prior_texts"]): raise ValueError("invalid context")
    for item in gold:
        ast = item["ast"]
        validate_ast(ast, lexicon)
        expected_facts = {canonical_fact(fact) for fact in assertions(ast)}
        if expected_facts != {canonical_fact(fact) for fact in item["assertions"]}: raise ValueError("assertion labels disagree with AST")
        if item["semantic_truth"] is not None and item["semantic_truth"] != label(evaluate(ast, item["world"])):
            raise ValueError("semantic label disagrees with independent oracle")
        channels = set()
        for fact in item["world"]:
            key = fact["subject"], fact["attribute"], channel(fact["channel"])
            if key in channels: raise ValueError("duplicate world channel")
            channels.add(key)
            if fact["value"] is not None:
                typed(fact["value"])
                if channel(fact["value"]) != channel(fact["channel"]): raise ValueError("changed world channel")
        if item["metamorphic_group"]: groups[item["metamorphic_group"]].append(item)
        if item["acceptable_statuses"] == ["parsed"] and ast is None: raise ValueError("parsed case has no AST")
        if item["family"] == "document_bounds" and ast is not None: raise ValueError("cross-document pronoun was resolved")
    for pair in groups.values():
        if len(pair) != 2: raise ValueError("metamorphic group is not paired")
        a, b = pair
        if public_by_id[a["id"]]["text"] != public_by_id[b["id"]]["text"]: raise ValueError("truth pair changed public text")
        if canonical_ast(a["ast"]) != canonical_ast(b["ast"]): raise ValueError("truth values changed parsing gold")
        if a["semantic_truth"] == b["semantic_truth"]: raise ValueError("truth pair did not change truth")
    kinds = Counter()
    for item in gold:
        for fact in item["assertions"]: kinds[fact["value"]["kind"]] += 1
    return {
        "rows": len(rows), "family_counts": dict(Counter(item["family"] for item in gold)),
        "typed_assertion_counts": dict(kinds), "semantic_classes": dict(Counter(item["semantic_truth"] or "not_applicable" for item in gold)),
        "truth_only_metamorphic_pairs": len(groups),
    }


def audit_bundle(bundle, include_gold=False):
    bundle = Path(bundle)
    manifest = verify_public(bundle)
    rows = load_jsonl(bundle / "public/input.jsonl")
    ids = [row["id"] for row in rows]
    if len(rows) != manifest["rows"] or len(set(ids)) != len(ids): raise ValueError("public row counts/IDs invalid")
    if any(set(row) != {"id", "document_id", "text", "context"} for row in rows): raise ValueError("unexpected public input features")
    report = {"public_hashes_verified": True, "public_bundle_sha256": manifest["public_bundle_sha256"], "rows": len(rows), "gold_opened": False}
    if include_gold:
        if manifest["split"] != "development": raise ValueError("final audit may not open private gold")
        if digest(bundle / "private/gold.jsonl") != manifest["gold_sha256"]: raise ValueError("gold hash mismatch")
        report.update(audit_cases(rows, load_jsonl(bundle / "private/gold.jsonl"), load_json(bundle / "public/lexicon.json")))
        report["gold_opened"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--include-gold", action="store_true", help="development only")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    output = require_artifacts(args.report)
    if output.exists(): raise ValueError("refusing to overwrite audit report")
    report = audit_bundle(args.bundle, args.include_gold)
    write_json(output, report)
    print(f"{report['rows']} rows; hashes verified; gold opened: {report['gold_opened']}")


if __name__ == "__main__": main()
