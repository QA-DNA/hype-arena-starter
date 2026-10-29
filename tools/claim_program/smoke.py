"""Development-authored adapter checks; no dataset, truth, or evidence lookup."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(out: Path, repeats: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    attrs = ["secure", "price", "version", "released", "power", "description"]
    lexicon = {"subjects": [
        {"name": "Atlas", "aliases": ["Atlas Inc."], "attributes": attrs},
        {"name": "Boreal", "aliases": [], "attributes": attrs},
    ]}
    money = {"kind": "money", "value": 12.75, "currency": "EUR", "per": "month"}
    nominal = "end-to-end research and support"
    cases = [
        ("Atlas secure is true and Boreal secure is false", [], "all", True, True, 2),
        ("Atlas secure is true or Boreal secure is unknown", [], "any", False, True, None),
        ("not all of the following: Atlas secure is true and Boreal secure is true", [], "not", True, True, None),
        ("neither Atlas secure is false nor Boreal secure is true", [], "not", True, True, None),
        ("Atlas price is not less than 12.75 EUR/month", [("12.75 EUR/month", money)], "atom", True, False, 1),
        ("Atlas price on 2026-03 >= Boreal price on 2025-12-31", [], "compare", True, True, None),
        ("If Atlas secure is true then Boreal secure is false", [], "unsupported", False, True, None),
        ("(" * 33 + "Atlas secure is true" + ")" * 33, [], "unsupported", False, True, None),
        ("Atlas price > its price", [], "unsupported", False, True, None),
        (f'Atlas description is "{nominal}" or Boreal secure is true', [(nominal, {"kind": "name", "value": nominal})], "any", True, True, None),
    ]
    rows, expected = [], []
    for repeat in range(repeats):
        for index, (text, raw, kind, complete, structured, count) in enumerate(cases):
            candidates = [{"start": text.index(s), "end": text.index(s) + len(s), "value": value} for s, value in raw]
            row = {"id": f"development-{repeat}-{index}", "text": text, "candidates": candidates, "neural": []}
            # These are deliberately contradictory, irrelevant metadata. The
            # adapter must discard them before constructing parser arguments.
            changed = dict(row, label="false", date="1900-01-01", gold={"form": "do not use", "label": "true"}, world_path="/never-open-this", document_id="irrelevant")
            rows.extend([row, changed])
            expected.extend([{"kind": kind, "complete": complete, "structured": structured, "legacy_count": count}] * 2)
    write(out / "lexicon.json", lexicon)
    write(out / "input.json", rows)
    write(out / "expected.json", expected)
    print(json.dumps({"rows": len(rows), "input_sha256": digest(out / "input.json"), "lexicon_sha256": digest(out / "lexicon.json")}))


def validate(out: Path) -> None:
    rows = json.loads((out / "output.json").read_text(encoding="utf-8"))
    expected = json.loads((out / "expected.json").read_text(encoding="utf-8"))
    assert len(rows) == len(expected)
    for index, (row, target) in enumerate(zip(rows, expected, strict=True)):
        program = row["program"]
        actual = {"kind": program["expression"]["kind"], "complete": program["complete"], "structured": program["structured"], "legacy_count": None if row["legacy_facts"] is None else len(row["legacy_facts"])}
        assert actual == target, (index, actual, target)
    for index in range(0, len(rows), 2):
        assert rows[index] == rows[index + 1], ("metadata changed parse", index)
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    report = {"rows": len(rows), "metadata_pairs": len(rows) // 2, "structural_checks_passed": len(rows), "input_sha256": digest(out / "input.json"), "lexicon_sha256": digest(out / "lexicon.json"), "output_sha256": digest(out / "output.json"), "source_sha256": digest(Path(__file__).resolve().parents[2] / "crates/core/src/claim_program.rs"), "metrics": metrics, "provenance": "development-authored syntax and metadata-isolation fixtures; no independent accuracy estimate"}
    write(out / "receipt.json", report)
    print(json.dumps(report, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "validate"])
    parser.add_argument("--out", type=Path, default=Path("artifacts/parser-v3-program/smoke"))
    parser.add_argument("--repeats", type=int, default=100)
    args = parser.parse_args()
    if args.action == "prepare":
        if not 1 <= args.repeats <= 1000:
            parser.error("repeats must be between 1 and 1000")
        prepare(args.out, args.repeats)
    else:
        validate(args.out)


if __name__ == "__main__":
    main()
