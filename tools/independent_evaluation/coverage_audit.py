"""Compare a preserved development claim report against current bounded checks.

Only public anchors, lexicon and actual predictions supply facts to the scorer.
The historical report supplies comparison results, never world values or labels.
This command does not open gold, private worlds, or sealed claim data.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .audit import public_world
from .claims import score_claim_rows
from .factory import ROOT, sha256, source_hashes, write_json
from .oracle import OracleError
from .score import read_csv, verify_public


def compare_reports(before: dict, after: dict, predictions: list[dict]) -> dict:
    """List every changed row and enforce the scope of a coverage-only revision."""
    old = {record["id"]: record for record in before["records"]}
    new = {record["id"]: record for record in after["records"]}
    if (len(old) != len(before["records"]) or len(new) != len(after["records"]) or
            list(old) != list(new)):
        raise OracleError("coverage audit requires the same unique judged claim IDs in order")
    texts = {row["id"]: row for row in predictions if row.get("type")}
    changes, world_changes, text_changes = [], [], []
    for row_id, previous in old.items():
        current = new[row_id]
        for field in ("type", "schema", "lexicon", "newness"):
            if previous.get(field) != current.get(field):
                raise OracleError(f"coverage revision changed {field} for {row_id}")
        if previous["world_truth"] != current["world_truth"]:
            if previous["world_truth"]["status"] != "unsupported":
                raise OracleError(f"coverage revision changed an existing world verdict for {row_id}")
            world_changes.append(row_id)
        if previous["text_grammar"] != current["text_grammar"]:
            text_changes.append(row_id)
        if previous != current:
            changes.append({"id": row_id, "type": current["type"],
                            "text": texts[row_id]["text"], "form_json": texts[row_id]["form"],
                            "before": previous, "after": current})
    return {
        "before": {key: value for key, value in before.items() if key != "records"},
        "after": {key: value for key, value in after.items() if key != "records"},
        "world_changed_ids": world_changes, "text_changed_ids": text_changes,
        "changed_rows": changes, "unchanged_rows": len(old) - len(changes),
        "existing_world_verdicts_preserved": True,
    }


def audit_coverage(bundle: Path, predictions: Path, baseline: Path, output: Path) -> dict:
    manifest = verify_public(bundle)
    if manifest["sealed"]:
        raise OracleError("coverage auditing is development-only; sealed data is forbidden")
    output = output.resolve()
    cache = Path(__file__).resolve().parent / ".cache"
    if not output.is_relative_to(cache) or output == cache:
        raise OracleError("coverage reports must stay in this evaluator's ignored .cache directory")
    if subprocess.run(["git", "check-ignore", "-q", str(output)], cwd=ROOT, check=False).returncode:
        raise OracleError("coverage output must be ignored by Git")
    if output.exists():
        raise OracleError("refusing to overwrite an existing coverage audit")
    inputs = {"predictions": predictions, "baseline_report": baseline,
              **{name: bundle / "public" / name for name in (*manifest["hashes"], "manifest.json")}}
    hashes = {name: sha256(path) for name, path in inputs.items()}
    before = json.loads(baseline.read_text(encoding="utf-8"))
    if before.get("sealed") is not False or before.get("public_sha256") != manifest["public_sha256"]:
        raise OracleError("baseline must be a released development report for this exact public bundle")
    rows = read_csv(bundle / "public" / "universe.csv")
    lexicon = json.loads((bundle / "public" / "lexicon.json").read_text(encoding="utf-8"))
    world, public_audit = public_world(rows, lexicon)
    predicted = read_csv(predictions)
    after = score_claim_rows(predicted, rows, world, limit=before["requested_claims"])
    after.update(public_sha256=manifest["public_sha256"], sealed=False)
    result = compare_reports(before, after, predicted)
    result.update(public_anchor_audit=public_audit, source_files_sha256=source_hashes(),
                  input_files={name: {"path": str(path.resolve()), "sha256": hashes[name]}
                               for name, path in inputs.items()},
                  provenance="development-time OpenAI Codex assistance; public anchors only; no production/gold imports",
                  limitations="bounded fact text only; mixed-precision date ordering unchanged and unsupported; not the official referee")
    if hashes != {name: sha256(path) for name, path in inputs.items()}:
        raise OracleError("audit input bytes changed during scoring")
    output.mkdir(parents=True, exist_ok=False)
    # Exclusive writes and fresh output directory preserve historical reports.
    (output / "before.json").write_bytes(baseline.read_bytes())
    write_json(output / "after.json", after)
    write_json(output / "coverage.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--baseline-report", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = audit_coverage(args.bundle, args.predictions, args.baseline_report, args.output_directory)
    except (OracleError, OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"coverage audit refused: {exc}\n")
    print(json.dumps({"world_changed_ids": result["world_changed_ids"],
                      "text_changed_rows": len(result["text_changed_ids"]),
                      "unchanged_rows": result["unchanged_rows"],
                      "before_world_truth": result["before"]["world_truth"],
                      "after_world_truth": result["after"]["world_truth"],
                      "certified_by_bounded_checks": result["after"]["certified_by_bounded_checks"]}, sort_keys=True))


if __name__ == "__main__":
    main()
