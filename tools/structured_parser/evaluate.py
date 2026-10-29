"""Development-only extraction A/B; gold never enters the Rust parser.

Reads only an explicitly named released development directory, public native
extraction output, and parser output. Does not load world/context/seed files.
No truth-accuracy score is produced: root owns end-to-end solver evaluation.
"""
import argparse
import collections
import csv
from decimal import Decimal
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


FACTORS = {
    "quantity": {
        "B": ("data", 1), "KB": ("data", 1000), "kB": ("data", 1000),
        "MB": ("data", 10**6), "GB": ("data", 10**9), "TB": ("data", 10**12),
        "mm": ("length", Fraction(1, 1000)), "cm": ("length", Fraction(1, 100)),
        "m": ("length", 1), "km": ("length", 1000),
        "in": ("length", Fraction(127, 5000)), "inch": ("length", Fraction(127, 5000)),
        "g": ("mass", 1), "kg": ("mass", 1000), "mAh": ("charge", 1),
        "mW": ("power", Fraction(1, 1000)), "W": ("power", 1),
        "kW": ("power", 1000), "MW": ("power", 10**6),
        "Hz": ("frequency", 1), "kHz": ("frequency", 1000),
        "MHz": ("frequency", 10**6), "GHz": ("frequency", 10**9),
    },
    "duration": {
        "ms": ("fixed-time", Fraction(1, 1000)), "s": ("fixed-time", 1),
        "min": ("fixed-time", 60), "h": ("fixed-time", 3600),
        "day": ("fixed-time", 86400), "week": ("fixed-time", 604800),
        "month": ("calendar-time", 1), "year": ("calendar-time", 12),
    },
}


def aliases(lexicon):
    return {"".join(c.lower() for c in a if c.isalnum()): s["name"]
            for s in lexicon["subjects"] for a in [s["name"], *s.get("aliases", [])]}


def canonical_name(name, names):
    return names.get("".join(c.lower() for c in name if c.isalnum()), name)


def normalize(fact, names, convert_units=True):
    """Top-level gold op and decimal *strings* normalize only in this evaluator."""
    value = fact["value"]
    kind = value.get("kind")
    op = fact.get("op", value.get("op", "eq"))
    subject = canonical_name(fact["subject"], names)
    channel = ()
    raw = value.get("value")
    if kind in {"money", "percent", "quantity", "duration"}:
        try:
            amount = Fraction(Decimal(str(raw)))
        except Exception:
            amount = str(raw)
        if kind == "money":
            channel = (value.get("currency"), value.get("per"))
        elif kind in FACTORS:
            unit = value.get("unit", "")
            dim, factor = FACTORS[kind].get(unit, ("count:" + unit, 1)) if convert_units else ("literal-unit:" + unit, 1)
            channel = (dim,)
            if isinstance(amount, Fraction):
                amount *= factor
        raw = str(amount)
    elif kind == "name":
        raw = canonical_name(str(raw), names)
    else:
        # Date precision, written version identity and literal booleans survive.
        raw = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    return (subject, fact["attribute"], kind, channel, op, raw)


def summary(records):
    n = len(records)
    exact = sum(r["exact"] for r in records)
    tp = sum(r["tp"] for r in records)
    fp = sum(r["fp"] for r in records)
    fn = sum(r["fn"] for r in records)
    return {"rows": n, "exact_rows": exact, "exact_rate": exact / n if n else None,
            "tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}


def score(args):
    development = Path(args.development).resolve()
    if development.name != "development":
        raise ValueError("Only a released development directory is accepted")
    public = development / "public"
    gold_path = development / "private/gold.jsonl"
    rows_path, lexicon_path = public / "universe.csv", public / "lexicon.json"
    with rows_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = {r["id"]: r for r in csv.DictReader(stream)}
    gold = [json.loads(s, parse_float=Decimal) for s in gold_path.read_text(encoding="utf-8").splitlines()]
    native = {r["id"]: r for r in json.loads(Path(args.native).read_text(encoding="utf-8"), parse_float=Decimal)}
    bound = {r["id"]: r["parsed"] for r in json.loads(Path(args.structured).read_text(encoding="utf-8"), parse_float=Decimal)}
    names = aliases(json.loads(lexicon_path.read_text(encoding="utf-8")))
    results = {name: [] for name in ("native", "structured")}
    literal_exact = collections.Counter()
    buckets = {name: collections.defaultdict(list) for name in results}
    examples, baseline_examples, delta = [], [], collections.Counter()
    fallback_rows = [i for i, p in bound.items() if any(n.startswith("neural_fallback:") for n in p["notes"])]
    fallback_changed = [i for i in fallback_rows if bound[i]["facts"] != native[i]["form"]]
    for g in gold:
        row_id = g["id"]
        expected = {normalize(a, names) for a in g["assertions"]}
        pair = {}
        for name, facts in (("native", native[row_id]["form"]), ("structured", bound[row_id]["facts"])):
            actual = {normalize(a, names) for a in facts}
            literal_exact[name] += {normalize(a, names, False) for a in facts} == {normalize(a, names, False) for a in g["assertions"]}
            record = {"exact": actual == expected, "tp": len(actual & expected), "fp": len(actual - expected), "fn": len(expected - actual)}
            results[name].append(record)
            pair[name] = record
            for bucket in (f"style:{g['style']}", f"context:{g['context']}", f"arity:{g['arity']}"):
                buckets[name][bucket].append(record)
            if name == "structured" and actual != expected:
                examples.append({"id": row_id, "text": rows[row_id]["text"], "expected": g["assertions"],
                                 "native": native[row_id]["form"], "structured": facts,
                                 "complete": bound[row_id]["complete"], "notes": bound[row_id]["notes"],
                                 "missing": sorted(expected - actual, key=str), "extra": sorted(actual - expected, key=str)})
            if name == "native" and actual != expected:
                baseline_examples.append({"id": row_id, "text": rows[row_id]["text"], "expected": g["assertions"],
                                          "native": facts, "structured": bound[row_id]["facts"],
                                          "missing": sorted(expected - actual, key=str), "extra": sorted(actual - expected, key=str)})
        key = "both_exact" if pair["native"]["exact"] and pair["structured"]["exact"] else "improved" if pair["structured"]["exact"] else "regressed" if pair["native"]["exact"] else "both_inexact"
        delta[key] += 1
    unknown_ids = [i for i, r in rows.items() if "explicitly unrecorded (unknown)" in r["text"]]
    anchor_ids = [i for i, r in rows.items() if r["label"]]
    report = {"scope": "released development extraction A/B; no truth score or held-out claim",
              "metrics": {name: summary(rs) for name, rs in results.items()}, "literal_unit_exact_rows": dict(literal_exact), "delta": dict(delta),
              "buckets": {name: {k: summary(v) for k, v in sorted(bs.items())} for name, bs in buckets.items()},
              "fallback": {"rows": len(fallback_rows), "facts_changed": len(fallback_changed)},
              "anchors": {"rows": len(anchor_ids), "complete": sum(bound[i]["complete"] for i in anchor_ids),
                          "unknown_rows": len(unknown_ids), "unknown_with_facts": sum(bool(bound[i]["facts"]) for i in unknown_ids)},
              "targets": {"rows": len(gold), "complete": sum(bound[g["id"]]["complete"] for g in gold)},
              "error_examples": len(examples),
              "hashes": {str(p): sha(p) for p in [rows_path, lexicon_path, gold_path, Path(args.native), Path(args.structured), Path(__file__), Path(__file__).parents[2] / "crates/core/src/structured.rs"]}}
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    def encode(obj):
        if isinstance(obj, Decimal): return str(obj)
        raise TypeError(type(obj).__name__)
    (output / "scores.json").write_text(json.dumps(report, indent=2, default=encode) + "\n", encoding="utf-8")
    (output / "errors.json").write_text(json.dumps(examples, indent=2, ensure_ascii=False, default=encode) + "\n", encoding="utf-8")
    (output / "baseline-errors.json").write_text(json.dumps(baseline_examples, indent=2, ensure_ascii=False, default=encode) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("metrics", "delta", "fallback", "anchors", "targets", "error_examples")}, indent=2))


def prepare(args):
    public = Path(args.public)
    with (public / "universe.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = [{k: row[k] for k in ("id", "text", "date", "label")} for row in csv.DictReader(stream)]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "csv_sha256": sha(public / "universe.csv"),
                      "lexicon_sha256": sha(public / "lexicon.json"), "output_sha256": sha(output)}))


def prepare_practice(args):
    """Use existing label-free frozen predictions and text-only candidates."""
    ids = json.loads(Path(args.ids).read_text(encoding="utf-8"))
    with Path(args.practice).open(encoding="utf-8-sig", newline="") as stream:
        rows = {r["id"]: {k: r[k] for k in ("id", "text", "date")} for r in csv.DictReader(stream)}
    predictions = {r["id"]: r["prediction"] for r in (json.loads(s) for s in Path(args.frozen_predictions).read_text(encoding="utf-8").splitlines())}
    spec = importlib.util.spec_from_file_location("frozen_structured_candidates", args.grammar)
    grammar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grammar)
    bundle = Path(args.bundle)
    lexicon = json.loads((bundle / "lexicon.json").read_text(encoding="utf-8"))
    meta = json.loads((bundle / "meta.json").read_text(encoding="utf-8"))
    grammar = grammar.Grammar(lexicon, meta["extra_names"])
    public = [{**rows[i], "candidates": grammar.candidates(rows[i]["text"]),
               "neural": [p["atom"] for p in predictions[i]]} for i in ids]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(public, ensure_ascii=False), encoding="utf-8")
    hashes = {str(p): sha(p) for p in [args.practice, args.ids, args.frozen_predictions, args.grammar, bundle / "lexicon.json", bundle / "meta.json", output]}
    output.with_suffix(".provenance.json").write_text(json.dumps({"rows": len(public), "protocol": "existing frozen neural output; text-only candidates; no gold or labels passed to parser", "hashes": hashes}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(public), "output_sha256": sha(output)}))


def score_practice(args):
    with Path(args.practice).open(encoding="utf-8-sig", newline="") as stream:
        gold = {r["id"]: r for r in csv.DictReader(stream)}
    inputs = json.loads(Path(args.input).read_text(encoding="utf-8"), parse_float=Decimal)
    bound = {r["id"]: r["parsed"] for r in json.loads(Path(args.structured).read_text(encoding="utf-8"), parse_float=Decimal)}
    names = aliases(json.loads(Path(args.lexicon).read_text(encoding="utf-8-sig")))
    records = {name: [] for name in ("native", "structured")}
    strict = {name: 0 for name in records}
    changes, regressions, improvements, fallback = [], [], [], []
    for r in inputs:
        i = r["id"]
        expected = json.loads(gold[i]["form"], parse_float=Decimal)
        desired = {normalize(a, names) for a in expected}
        pair = {}
        for name, facts in (("native", r["neural"]), ("structured", bound[i]["facts"])):
            actual = {normalize(a, names) for a in facts}
            record = {"exact": actual == desired, "tp": len(actual & desired), "fp": len(actual - desired), "fn": len(desired - actual)}
            records[name].append(record)
            pair[name] = record
            # Strict metric uses JSON objects with exact Decimal arithmetic,
            # without the physical-unit equivalence of the main metric.
            encode = lambda f: json.dumps(f, sort_keys=True, default=str)
            strict[name] += {encode(f) for f in facts} == {encode(f) for f in expected}
        if any(n.startswith("neural_fallback:") for n in bound[i]["notes"]):
            fallback.append(i)
            assert r["neural"] == bound[i]["facts"], i
        if r["neural"] != bound[i]["facts"]:
            change = {"id": i, "text": r["text"], "expected": expected,
                      "native": r["neural"], "structured": bound[i]["facts"],
                      "complete": bound[i]["complete"], "notes": bound[i]["notes"], "metrics": pair}
            changes.append(change)
            if pair["native"]["exact"] and not pair["structured"]["exact"]:
                regressions.append(change)
            if not pair["native"]["exact"] and pair["structured"]["exact"]:
                improvements.append(change)
    report = {"scope": "official practice parser-development paired390; frozen neural predictions reused, no new training",
              "metrics": {name: summary(rs) for name, rs in records.items()},
              "strict_json_exact_rows": strict, "changes": len(changes), "regressed_exact": len(regressions),
              "improved_exact": len(improvements), "fallback_rows": len(fallback), "fallback_facts_changed": 0,
              "complete": sum(p["complete"] for p in bound.values()),
              "hashes": {str(p): sha(p) for p in [args.practice, args.lexicon, args.input, args.structured]},
              "regressions": regressions, "improvements": improvements, "changed_examples": changes}
    if args.baseline:
        baseline = {r["id"]: r["parsed"] for r in json.loads(Path(args.baseline).read_text(encoding="utf-8"), parse_float=Decimal)}
        paired, changed, fallback_changes = [], [], []
        for r in inputs:
            i = r["id"]
            old, new = baseline[i], bound[i]
            expected = json.loads(gold[i]["form"], parse_float=Decimal)
            desired = {normalize(a, names) for a in expected}
            old_exact = {normalize(a, names) for a in old["facts"]} == desired
            new_exact = {normalize(a, names) for a in new["facts"]} == desired
            row = {"id": i, "text": r["text"], "expected": expected, "baseline": old,
                   "structured": new, "baseline_exact": old_exact, "structured_exact": new_exact}
            paired.append(row)
            if old != new:
                changed.append(row)
            old_fallback = [n for n in old["notes"] if n.startswith("neural_fallback:") or n.startswith("neural_clause_fallback:")]
            new_fallback = [n for n in new["notes"] if n.startswith("neural_fallback:") or n.startswith("neural_clause_fallback:")]
            if old_fallback != new_fallback or (old_fallback and old["facts"] != new["facts"]):
                fallback_changes.append(row)
        report["baseline_comparison"] = {
            "baseline_exact": sum(r["baseline_exact"] for r in paired),
            "structured_exact": sum(r["structured_exact"] for r in paired),
            "improved_ids": [r["id"] for r in paired if not r["baseline_exact"] and r["structured_exact"]],
            "regressed_ids": [r["id"] for r in paired if r["baseline_exact"] and not r["structured_exact"]],
            "changed_rows": len(changed), "fallback_changes": len(fallback_changes),
            "changed_examples": changed, "fallback_changed_examples": fallback_changes,
        }
        report["hashes"][str(args.baseline)] = sha(args.baseline)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    compact = {k: v for k, v in report.items() if k not in {"regressions", "improvements", "changed_examples", "hashes", "baseline_comparison"}}
    if "baseline_comparison" in report:
        compact["baseline_comparison"] = {k: v for k, v in report["baseline_comparison"].items() if not k.endswith("examples")}
    print(json.dumps(compact, indent=2))


def main():
    parser = argparse.ArgumentParser(__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--public", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(run=prepare)
    p = commands.add_parser("score")
    for option in ("development", "native", "structured", "out"):
        p.add_argument("--" + option, required=True)
    p.set_defaults(run=score)
    p = commands.add_parser("prepare-practice")
    for option in ("practice", "ids", "frozen-predictions", "grammar", "bundle", "output"):
        p.add_argument("--" + option, required=True)
    p.set_defaults(run=prepare_practice)
    p = commands.add_parser("score-practice")
    for option in ("practice", "lexicon", "input", "structured", "output"):
        p.add_argument("--" + option, required=True)
    p.add_argument("--baseline", help="Frozen schema-parser output for row/fallback A/B; never passed to parsing")
    p.set_defaults(run=score_practice)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
