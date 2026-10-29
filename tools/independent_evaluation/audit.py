"""Audit public evidence; recompute DEVELOPMENT gold from public anchors only.

Sealed audit is always structural/public-only. It never opens sealed gold/world.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .factory import (SCOPE_END, SCOPE_START, SPECS, assert_ignored_artifact,
                      money_descriptor, sha256, write_json)
from .grammar import parse_value
from .oracle import (OracleError, World, alias_map, channel, compare,
                     resolve_public_context)
from .score import read_csv, verify_public


def association_audit(gold: list[dict]) -> dict:
    """Development-only nuisance/class contingency and shortcut diagnostics."""
    result = {}
    total = len(gold)
    label_totals = Counter(row["label"] for row in gold)
    for feature in ("style", "context", "distractor", "arity", "primary_fact"):
        counts = defaultdict(Counter)
        for row in gold:
            if feature == "primary_fact":
                first = row["assertions"][0]
                group = f"{first['subject']}/{first['attribute']}/{channel(first['value'])}"
            else:
                group = str(row[feature])
            counts[group][row["label"]] += 1
        mi = 0.
        for labels in counts.values():
            subtotal = sum(labels.values())
            for label, n in labels.items():
                mi += n / total * math.log2(n * total / (subtotal * label_totals[label]))
        result[feature] = {"categories": len(counts),
                           "categories_missing_any_label": sum(len(labels) < 3 for labels in counts.values()),
                           "category_majority_shortcut_accuracy": sum(max(labels.values()) for labels in counts.values()) / total,
                           "mutual_information_bits": mi,
                           "contingency": {name: dict(labels) for name, labels in sorted(counts.items())}}
    return result


def declared_facts() -> list[tuple[str, str, str, str]]:
    facts = []
    for subject, attribute, kind, unit in SPECS:
        if kind == "money":
            periods = [("EUR", unit), ("EUR", "year" if unit != "year" else "month"), ("USD", unit)]
            facts.extend((subject, attribute, f"money:{currency}:{period}", kind) for currency, period in periods)
        else:
            prototype = {"kind": kind, "unit": unit}
            facts.append((subject, attribute, channel(prototype), kind))
    return facts


def public_world(rows: list[dict], lexicon: dict) -> tuple[World, dict]:
    aliases = alias_map(lexicon)
    intervals = {}
    duplicate_evidence = 0
    for row in rows:
        if not row["label"]:
            continue
        if row["label"] != "true":
            raise OracleError("synthetic evidence anchors must be true")
        match = re.fullmatch(r"From (\d{4}-\d{2}-\d{2}) through (\d{4}-\d{2}-\d{2}), (.+)\.", row["text"])
        if not match:
            raise OracleError("anchor has no explicit full-date validity interval")
        start, end, body = match.groups()
        if date.fromisoformat(start) > date.fromisoformat(end):
            raise OracleError("reversed interval")
        matches = []
        for subject, attribute, slot, kind in declared_facts():
            words = attribute.replace("_", " ") + money_descriptor(slot)
            patterns = [f"{re.escape(subject)}'s {re.escape(words)} is (.+)",
                        f"the {re.escape(words)} of {re.escape(subject)} is (.+)",
                        f"{re.escape(subject)} records (.+) for {re.escape(words)}"]
            for pattern in patterns:
                value_match = re.fullmatch(pattern, body)
                if not value_match:
                    continue
                text = value_match.group(1)
                value = None if text == "explicitly unrecorded (unknown)" else parse_value(text, kind, aliases)
                if value is not None and channel(value) != slot:
                    raise OracleError("anchor value and declared channel disagree")
                matches.append(((subject, attribute, slot), value))
        if len(matches) != 1:
            raise OracleError(f"anchor must identify exactly one declared fact; got {len(matches)}")
        key, value = matches[0]
        identity = (*key, start, end)
        if identity in intervals:
            previous = intervals[identity]
            if (previous is None) != (value is None) or previous is not None and compare(previous, value, "eq", aliases) != "true":
                raise OracleError("inconsistent repeated evidence anchor")
            duplicate_evidence += 1
        intervals[identity] = value
    timelines = defaultdict(list)
    for (subject, attribute, slot, start, end), value in intervals.items():
        timelines[(subject, attribute, slot)].append({"start": start, "end": end, "value": value,
                                                      "reason": "explicit_gap" if value is None else ""})
    expected_keys = {(s, a, slot) for s, a, slot, _ in declared_facts()}
    if set(timelines) != expected_keys:
        raise OracleError("public anchors do not cover every declared channel")
    raw = []
    for key, segments in timelines.items():
        segments.sort(key=lambda segment: segment["start"])
        if segments[0]["start"] != str(SCOPE_START) or segments[-1]["end"] != str(SCOPE_END):
            raise OracleError("public intervals do not cover the full published scope")
        raw.append({"subject": key[0], "attribute": key[1], "channel": key[2], "segments": segments})
    world = World(raw, lexicon)
    return world, {"channels": len(timelines), "unique_intervals": len(intervals),
                   "known_intervals": sum(value is not None for value in intervals.values()),
                   "explicit_unknown_intervals": sum(value is None for value in intervals.values()),
                   "repeated_consistent_evidence": duplicate_evidence}


def audit_bundle(bundle: Path) -> dict:
    bundle = bundle.resolve()
    manifest = verify_public(bundle)
    expected_files = {"universe.csv", "lexicon.json", "context.json", "POLICY.md", "manifest.json"}
    if {path.name for path in (bundle / "public").iterdir()} != expected_files:
        raise OracleError("unexpected public file; keep all gold, seeds, outputs and reports outside public")
    rows = read_csv(bundle / "public" / "universe.csv")
    if any(set(row) != {"id", "text", "date", "label"} for row in rows):
        raise OracleError("public CSV must contain only id,text,date,label")
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise OracleError("duplicate public ids")
    for row in rows:
        date.fromisoformat(row["date"])
    targets = [row for row in rows if not row["label"]]
    if len(targets) != manifest["targets"] or len(rows) - len(targets) != manifest["anchors"]:
        raise OracleError("public row counts differ from manifest")
    lexicon = json.loads((bundle / "public" / "lexicon.json").read_text(encoding="utf-8"))
    world, evidence = public_world(rows, lexicon)
    contexts = json.loads((bundle / "public" / "context.json").read_text(encoding="utf-8"))["contexts"]
    documents, context_ids = set(), set()
    for context in contexts:
        target = by_id[context["row_id"]]
        if target["label"] or context["scope"] != "same_row_only" or context["row_ids"] != [target["id"]]:
            raise OracleError("context does not identify an actual same-row target boundary")
        if context["document_id"] in documents or context["row_id"] in context_ids:
            raise OracleError("context crosses or duplicates document boundaries")
        documents.add(context["document_id"])
        context_ids.add(context["row_id"])
        lo, hi = context["claim_span"]
        if context["declaration_span"][0] != 0 or not context["declaration_span"][1] == lo < hi <= len(target["text"]):
            raise OracleError("context spans are inconsistent with public text")
        resolve_public_context(target["text"], context, lexicon)
    result = {"schema": manifest["schema"], "sealed": manifest["sealed"], "targets": len(targets),
              "anchors": len(rows) - len(targets), "public_sha256": manifest["public_sha256"],
              "evidence": evidence, "public_pronoun_contexts": len(contexts),
              "duplicate_target_texts": sum(count - 1 for count in Counter(row["text"] for row in targets).values()),
              "max_target_characters": max(len(row["text"]) for row in targets),
              "gold_opened": False, "human_semantic_review": "pending; no human truth judgments recorded"}
    if not manifest["sealed"]:
        # Recompute from reconstructed PUBLIC evidence, not private world.json.
        gold_path = bundle / "private" / "gold.jsonl"
        metadata = json.loads((bundle / "private" / "metadata.json").read_text(encoding="utf-8"))
        if sha256(gold_path) != metadata["gold_sha256"]:
            raise OracleError("development gold hash changed")
        gold = [json.loads(line) for line in gold_path.read_text(encoding="utf-8").splitlines() if line]
        if {row["id"] for row in gold} != {row["id"] for row in targets}:
            raise OracleError("development gold and public target identities disagree")
        for row in gold:
            label, components = world.evaluate_all(row["assertions"], row["date"])
            if label != row["label"] or components != row["components"]:
                raise OracleError("development gold is not justified by public evidence")
            if row["context"] == "public_same_row_pronoun":
                context = next(context for context in contexts if context["row_id"] == row["id"])
                subject = resolve_public_context(by_id[row["id"]]["text"], context, lexicon)
                if subject != row["assertions"][0]["subject"]:
                    raise OracleError("gold antecedent is not the actual public context subject")
        result.update(gold_opened=True, development_gold_recomputed_from_public_anchors=len(gold),
                      labels=dict(Counter(row["label"] for row in gold)),
                      development_nuisance_class_associations=association_audit(gold))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    assert_ignored_artifact(args.report)
    result = audit_bundle(args.bundle)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.report, result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
